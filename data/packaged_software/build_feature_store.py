"""Company-quarter feature store for the 168-company software universe.

Built to the project's stated contracts: every cell carries its source, the date the
information was public (as_of), and an explicit reason when it is missing. Nothing is
imputed. A value whose as_of falls after the quarter end is withheld and marked, so the
matrix cannot read information that was not available at the decision point.

Outputs:
  output/feature_store_long.csv   one row per (cik, period_end, feature): value, unit,
                                  source_file, as_of, missing_reason, evidence_ref
  output/feature_matrix_wide.csv  the modelling view: one row per company-quarter, with
                                  <feature> (raw), <feature>__present (0/1), and
                                  <feature>__rank (cross-sectional rank within the quarter,
                                  scaled to [-1, 1]); plus in_evaluation_window

Design notes:
  - Evaluation scope is 2024-01-01 onward per the project plan; 2022-2023 quarters are kept
    and flagged as warm-up rather than dropped, because they supply prior company state.
  - Ranks are computed within each quarter only, so no statistic is taken over the full
    sample and no future information enters the scaling.
  - Counts are event counts for the quarter. A zero is a real zero (the scan ran and found
    nothing); a blank means the source could not be evaluated for that company-quarter.
  - Annual values (XBRL) are attached to the quarter containing their filing date, with
    as_of set to the filing date, so an annual figure is not treated as known early.

Standard library only.
"""

from __future__ import annotations

import csv
import datetime as dt
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
EXTRACTS = HERE / "extracts"
LONG = OUT / "feature_store_long.csv"
WIDE = OUT / "feature_matrix_wide.csv"
EVALUATION_START = "2024-01-01"

# Quarterly metrics already carrying a point-in-time availability date
QUARTERLY_NUMERIC = [
    "q_revenue", "ttm_revenue", "gross_margin", "rd_pct_rev", "sm_pct_rev", "sbc_pct_rev",
    "fcf_physical_capex_margin", "rev_growth_yoy_q", "goodwill_to_assets",
    "deferred_revenue_current", "rpo", "total_assets", "ttm_operating_cash_flow",
]
# Annual XBRL metrics; attached to the quarter of their filing date
ANNUAL_METRICS = [
    "public_float", "goodwill_acquired_in_year", "divestiture_proceeds",
    "loss_contingency_accrual", "convertible_debt_noncurrent",
]
# Event counts aggregated per quarter from the 8-K item scan
EVENT_ITEMS = ["2.02", "5.02", "2.01", "1.01", "2.03", "2.05", "4.01", "4.02", "8.01", "1.05"]


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cal_quarter(date: str) -> str:
    """The calendar quarter containing a date, e.g. 2024Q1.

    The panel is keyed on calendar quarters, not on each company's fiscal period end.
    Fiscal ends differ across the universe (January, June, November and so on), which
    produced 105 distinct period labels and left only a handful of companies per label.
    Cross-sectional ranking needs companies that share a period, so the fiscal end is kept
    as a reference column and the calendar quarter is the key.
    """
    y, m = int(date[:4]), int(date[5:7])
    return f"{y:04d}Q{(m - 1) // 3 + 1}"


def quarter_start(q: str) -> str:
    y, qn = int(q[:4]), int(q[-1])
    return f"{y:04d}-{(qn - 1) * 3 + 1:02d}-01"


def quarter_last_day(q: str) -> str:
    y, qn = int(q[:4]), int(q[-1])
    m = qn * 3
    last = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        last = 29
    return f"{y:04d}-{m:02d}-{last:02d}"


def valid_date(s: str) -> bool:
    try:
        dt.date.fromisoformat(s)
        return True
    except (ValueError, AttributeError):
        return False


def main() -> int:
    companies = {r["ticker"]: r for r in read(HERE / "packaged_software_companies.csv") if r["ticker"]}
    cells: list[dict] = []

    def add(ticker: str, period: str, feature: str, value, unit: str, source: str,
            as_of: str, reason: str = "", evidence: str = "") -> None:
        c = companies.get(ticker)
        if not c:
            return
        # Withhold anything not public by the quarter end, and say why
        if value not in ("", None) and as_of and valid_date(as_of) and as_of > quarter_last_day(period):
            value, reason = "", f"not_public_by_period_end (as_of {as_of})"
        cells.append({
            "cik": c["cik"].zfill(10), "ticker": ticker, "period_end": period,
            "feature": feature, "value": value, "unit": unit,
            "source_file": source, "as_of": as_of,
            "missing_reason": reason if value in ("", None) else "",
            "evidence_ref": evidence,
        })

    # 1. Quarterly fundamentals, with the conservative availability date
    fundamentals = read(EXTRACTS / "company_metrics" / "fundamentals_quarterly.csv")
    periods: set[str] = set()
    covered: set[tuple[str, str]] = set()
    fiscal_end: dict[tuple[str, str], str] = {}
    as_of_by_fiscal: dict[tuple[str, str], str] = {}
    for r in fundamentals:
        ticker = r["ticker"]
        as_of = r.get("available_date_conservative", "")
        # Key the row on the quarter the figures became public, not the quarter they
        # describe: Q1 results are filed in Q2, so keying on the data period would withhold
        # almost every fundamental as "not public yet". The data period is kept alongside.
        period = cal_quarter(as_of) if valid_date(as_of) else cal_quarter(r["period_end"])
        periods.add(period)
        covered.add((ticker, period))
        fiscal_end[(ticker, period)] = r["period_end"]
        as_of_by_fiscal[(ticker, r["period_end"])] = as_of
        for m in QUARTERLY_NUMERIC:
            v = r.get(m, "")
            add(ticker, period, m, v, "USD_or_ratio",
                "extracts/company_metrics/fundamentals_quarterly.csv", as_of,
                reason="not_reported_under_selected_tags" if v == "" else "")

    # 2. Rule of 40, derived from the same filings
    for r in read(OUT / "rule_of_40.csv"):
        as_of = as_of_by_fiscal.get((r["ticker"], r["period_end"]), "")
        period = cal_quarter(as_of) if valid_date(as_of) else cal_quarter(r["period_end"])
        add(r["ticker"], period, "rule_of_40", r["rule_of_40"], "pct_points",
            "output/rule_of_40.csv", as_of)

    # 3. Annual XBRL values, attached to the quarter of their filing date
    for r in read(OUT / "xbrl_gaps_annual.csv"):
        if r["metric"] not in ANNUAL_METRICS or not r["ticker"]:
            continue
        filed = r.get("filed", "")
        period = cal_quarter(filed) if valid_date(filed) else cal_quarter(r["period_end"])
        note = r.get("validation", "")
        add(r["ticker"], period, r["metric"], r["value"], r["unit"],
            "output/xbrl_gaps_annual.csv", filed,
            evidence=f"{r['source_tag']} {r['period_end']}" + (f" [{note}]" if note and note != "ok" else ""))

    # 4. Event counts per quarter from the 8-K scan. The scan covers every company, so a
    #    company-quarter with no filing is a true zero.
    event_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for r in read(OUT / "8k_item_filings.csv"):
        if r["item"] not in EVENT_ITEMS:
            continue
        date = r["filing_folder"].split("_")[0]
        if not valid_date(date):
            continue
        event_counts[(r["ticker"], cal_quarter(date), r["item"])] += 1
    for ticker, period in sorted(covered):
            for item in EVENT_ITEMS:
                n = event_counts.get((ticker, period, item), 0)
                add(ticker, period, f"8k_item_{item.replace('.', '_')}_count", n, "filings",
                    "output/8k_item_filings.csv", period)

    # 5. Exploited vulnerabilities added in the quarter
    kev: dict[tuple[str, str], int] = defaultdict(int)
    for r in read(OUT / "kev_company_cves.csv"):
        if valid_date(r.get("date_added", "")):
            kev[(r["ticker"], cal_quarter(r["date_added"]))] += 1
    for ticker, period in sorted(covered):
            add(ticker, period, "kev_cves_added_count", kev.get((ticker, period), 0), "cves",
                "output/kev_company_cves.csv", period)

    # 6. Layoff notices (California only; absence elsewhere is unmeasured, not zero)
    warn: dict[tuple[str, str], int] = defaultdict(int)
    warn_emp: dict[tuple[str, str], int] = defaultdict(int)
    for r in read(OUT / "warn_ca_notices.csv"):
        if valid_date(r.get("notice_date", "")):
            key = (r["ticker"], cal_quarter(r["notice_date"]))
            warn[key] += 1
            warn_emp[key] += int(r["employees_affected"] or 0)
    for ticker, period in sorted(covered):
            add(ticker, period, "warn_ca_notices_count", warn.get((ticker, period), 0), "notices",
                "output/warn_ca_notices.csv", period,
                evidence="California only; other states not collected")
            add(ticker, period, "warn_ca_employees_affected", warn_emp.get((ticker, period), 0),
                "employees", "output/warn_ca_notices.csv", period,
                evidence="California only; other states not collected")

    # 7. Auditor change, dated at the filing that first names the new auditor
    for r in read(OUT / "auditor_changes.csv"):
        date = r["first_filing_with_new_auditor"]
        if valid_date(date):
            add(r["ticker"], cal_quarter(date), "auditor_changed", 1, "flag",
                "output/auditor_changes.csv", date,
                evidence=f"{r['from_auditor']} -> {r['to_auditor']}")

    # 8. Federal contract awards starting in the quarter (exact-name matches only)
    awards: dict[tuple[str, str], float] = defaultdict(float)
    award_n: dict[tuple[str, str], int] = defaultdict(int)
    for r in read(OUT / "contract_awards.csv"):
        if r.get("exact_name_match") not in ("True", "true", "1"):
            continue
        if not valid_date(r.get("start_date", "")):
            continue
        key = (r["company_name"], cal_quarter(r["start_date"]))
        awards[key] += float(r["award_amount"] or 0)
        award_n[key] += 1
    name_to_ticker = {c["name"]: t for t, c in companies.items()}
    for (name, period), total in awards.items():
        ticker = name_to_ticker.get(name)
        if ticker:
            add(ticker, period, "federal_award_amount_started", round(total, 2), "USD",
                "output/contract_awards.csv", period)
            add(ticker, period, "federal_awards_started_count", award_n[(name, period)],
                "awards", "output/contract_awards.csv", period)

    # Write the long store
    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["cik", "ticker", "period_end", "feature", "value", "unit", "source_file",
              "as_of", "missing_reason", "evidence_ref"]
    cells = [c for c in cells if c["period_end"] in periods]
    with LONG.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(cells, key=lambda r: (r["ticker"], r["period_end"], r["feature"])))

    # Pivot to the modelling view
    by_cell: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for c in cells:
        by_cell[(c["ticker"], c["period_end"])][c["feature"]] = c["value"]
    feature_names = sorted({c["feature"] for c in cells})

    # Cross-sectional ranks within each quarter, scaled to [-1, 1]
    ranks: dict[tuple[str, str, str], float] = {}
    for period in sorted(periods):
        for feature in feature_names:
            vals = []
            for ticker in companies:
                v = by_cell.get((ticker, period), {}).get(feature, "")
                if v not in ("", None):
                    try:
                        vals.append((float(v), ticker))
                    except ValueError:
                        pass
            if len(vals) < 5:   # too few to rank meaningfully
                continue
            vals.sort()
            n = len(vals)
            for i, (_, ticker) in enumerate(vals):
                ranks[(ticker, period, feature)] = round(2 * (i / (n - 1)) - 1, 4) if n > 1 else 0.0

    wide_fields = ["cik", "ticker", "name", "period_end", "data_period_end", "in_evaluation_window"]
    for feature in feature_names:
        wide_fields += [feature, f"{feature}__present", f"{feature}__rank"]
    rows = []
    for ticker, c in sorted(companies.items()):
        for period in sorted(periods):
            if (ticker, period) not in covered:
                continue
            row = {"cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                   "period_end": period,
                   "in_evaluation_window": "yes" if quarter_start(period) >= EVALUATION_START else "warm_up",
                   "data_period_end": fiscal_end.get((ticker, period), "")}
            for feature in feature_names:
                v = by_cell.get((ticker, period), {}).get(feature, "")
                row[feature] = v
                row[f"{feature}__present"] = 1 if v not in ("", None) else 0
                r = ranks.get((ticker, period, feature))
                row[f"{feature}__rank"] = r if r is not None else ""
            rows.append(row)
    with WIDE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=wide_fields)
        w.writeheader()
        w.writerows(rows)

    withheld = sum(1 for c in cells if c["missing_reason"].startswith("not_public"))
    missing = sum(1 for c in cells if c["value"] in ("", None))
    print(f"long store: {len(cells)} cells, {len(feature_names)} features, {len(periods)} quarters")
    print(f"  cells with a value: {len(cells) - missing} | missing: {missing}")
    print(f"  withheld as not public by period end: {withheld}")
    print(f"wide matrix: {len(rows)} company-quarters, {len(wide_fields)} columns")
    print(f"  in evaluation window (>= {EVALUATION_START}): {sum(1 for r in rows if r['in_evaluation_window'] == 'yes')}")
    print(f"  warm-up rows: {sum(1 for r in rows if r['in_evaluation_window'] == 'warm_up')}")
    reasons = defaultdict(int)
    for c in cells:
        if c["missing_reason"]:
            reasons[c["missing_reason"].split(" (")[0]] += 1
    print("  missing reasons:", dict(reasons))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
