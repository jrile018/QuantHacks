"""Backtest feature matrix: one row per company per calendar quarter, from the unified dataset.

Built for backtesting, so the rules are strict:

  Point in time    every feature in the matrix was public by its quarter end. Values come
                   from fact_panel, which carries an as_of date per cell, and any cell whose
                   as_of falls after the quarter end is already withheld there.
  Ranks            cross-sectional ranks are computed within each quarter only, from that
                   quarter's values, so no future companies or dates enter the scaling.
  Labels           forward 63-trading-day excess return over the market, from fact_labels,
                   attached to the quarter end it starts from.
  Static facts     connectedness, 13F common ownership and subsidiary counts are computed
                   over the whole sample, so they would leak the future. They are NOT in the
                   matrix. They stay in the database for descriptive work only.
  Survivorship     the 168 companies are survivors. Every row carries survivorship_flag=1,
                   and membership_status and exit_date come from dim_company. A backtest
                   must read this as an optimistic universe until acquired companies are
                   added (see membership_universe.csv).

Writes:
  output/feature_matrix_backtest.csv   the matrix
  table fact_feature_matrix in dataset.sqlite (same content)
  output/feature_matrix_summary.txt    coverage by feature and quarter
"""

from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
DB = OUT / "dataset.sqlite"
SURVIVORSHIP_NOTE = "universe of current listings; acquired and delisted companies excluded"


def quarter_end(label: str) -> str:
    """'2024Q1' -> '2024-03-31'."""
    y, q = int(label[:4]), int(label[-1])
    last = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
    return f"{y}-{last}"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # Companies, with membership
    companies = {r["cik"]: dict(r) for r in con.execute(
        "SELECT cik, ticker, name, membership_status, exit_date FROM dim_company")}

    # Labels: forward excess return, keyed on the quarter end
    labels = {(r["cik"], r["quarter_end"]): r["excess_return"] for r in con.execute(
        "SELECT cik, quarter_end, excess_return FROM fact_labels WHERE horizon_days = 63")}

    # Point-in-time panel cells, pivoted to one value per feature per company-quarter
    panel: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    features: set[str] = set()
    for r in con.execute("SELECT cik, period_end, feature, value FROM fact_panel WHERE value != ''"):
        panel[(r["cik"], r["period_end"])][r["feature"]] = r["value"]
        features.add(r["feature"])

    # Federal awards started in the quarter (exact-name matches, the reliable subset)
    awards: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in con.execute("SELECT cik, start_date, award_amount FROM fact_contracts WHERE exact_name_match IN ('True','true','1')"):
        if r["start_date"]:
            y, m = int(r["start_date"][:4]), int(r["start_date"][5:7])
            awards[(r["cik"], f"{y}Q{(m - 1) // 3 + 1}")].append(float(r["award_amount"] or 0))
    features |= {"federal_awards_count_started_exact", "federal_award_value_started_exact"}

    # Quarters with a label, in order
    # Quarters come from the panel's labels (2024Q1 style). Labels are keyed on the date.
    # Only quarters that have ended by the last price date. A future quarter has features
    # but no outcome, and must not be presented as a backtest observation.
    last_price = con.execute("SELECT MAX(date) FROM fact_prices").fetchone()[0]
    quarters = sorted({q for (_, q) in panel if quarter_end(q) <= last_price})
    panel = {k: v for k, v in panel.items() if k[1] in set(quarters)}
    rows = []
    feature_list = sorted(features)
    by_quarter = defaultdict(list)
    for (cik, qlabel) in panel:
        by_quarter[qlabel].append(cik)

    # Within-quarter ranks, computed only from values that quarter
    ranks: dict[tuple[str, str, str], float] = {}
    for qlabel, ciks in by_quarter.items():
        for f in feature_list:
            vals = []
            for cik in ciks:
                v = panel[(cik, qlabel)].get(f)
                if v is None and f == "federal_awards_count_started_exact":
                    v = str(len(awards.get((cik, qlabel), [])))
                if f == "federal_award_value_started_exact":
                    v = str(sum(awards.get((cik, qlabel), [])))
                if f == "federal_awards_count_started_exact":
                    v = str(len(awards.get((cik, qlabel), [])))
                try:
                    vals.append((float(v), cik))
                except (TypeError, ValueError):
                    continue
            if len(vals) < 5:
                continue
            vals.sort()
            n = len(vals)
            for i, (_, cik) in enumerate(vals):
                ranks[(cik, qlabel, f)] = round(2 * (i / (n - 1)) - 1, 4) if n > 1 else 0.0

    for (cik, qlabel) in sorted(panel):
        c = companies.get(cik)
        if not c:
            continue
        qe = quarter_end(qlabel)
        row = {
            "cik": cik, "ticker": c["ticker"], "name": c["name"],
            "quarter": qlabel, "quarter_end": qe,
            "in_evaluation_window": "yes" if qlabel >= "2024Q1" else "warm_up",
            "membership_status": c["membership_status"], "exit_date": c["exit_date"],
            "survivorship_flag": 1, "survivorship_note": SURVIVORSHIP_NOTE,
            "label_excess_return_63d": labels.get((cik, qe), ""),
        }
        for f in feature_list:
            raw = panel[(cik, qlabel)].get(f, "")
            if f == "federal_awards_count_started_exact":
                raw = str(len(awards.get((cik, qlabel), [])))
            elif f == "federal_award_value_started_exact":
                raw = str(round(sum(awards.get((cik, qlabel), [])), 2))
            row[f] = raw
            row[f"{f}__present"] = 1 if raw not in ("", None) else 0
            rk = ranks.get((cik, qlabel, f))
            row[f"{f}__rank"] = rk if rk is not None else ""
        rows.append(row)

    fields = list(rows[0].keys()) if rows else []
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "feature_matrix_backtest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    con.execute("DROP TABLE IF EXISTS fact_feature_matrix")
    con.execute("CREATE TABLE fact_feature_matrix (" + ", ".join(f'"{c}"' for c in fields) + ")")
    con.executemany(f"INSERT INTO fact_feature_matrix VALUES ({','.join('?' * len(fields))})",
                    [tuple(r[c] for c in fields) for r in rows])
    con.commit()
    con.close()

    labelled = sum(1 for r in rows if r["label_excess_return_63d"] != "")
    summary = [
        "Backtest feature matrix",
        f"rows (company-quarters): {len(rows)}",
        f"companies: {len({r['cik'] for r in rows})}",
        f"quarters: {quarters[0]} to {quarters[-1]} ({len(quarters)})",
        f"rows in evaluation window (2024Q1+): {sum(1 for r in rows if r['in_evaluation_window'] == 'yes')}",
        f"rows with a forward label: {labelled}",
        f"feature columns: {len(feature_list)} (raw, __present, __rank each)",
        f"survivorship: every row flagged survivorship_flag=1 ({SURVIVORSHIP_NOTE})",
        "",
        "Coverage by feature (share of rows with a value):",
    ]
    for f in feature_list:
        have = sum(1 for r in rows if r[f"{f}__present"] == 1)
        summary.append(f"  {f:40} {have:>6} ({100 * have / len(rows):.0f}%)")
    (OUT / "feature_matrix_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
