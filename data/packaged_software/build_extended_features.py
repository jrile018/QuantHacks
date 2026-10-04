"""Extended feature matrix: adds as-of RPO, acquisitions, purchase-price and power-cost features.

Reads the existing backtest matrix and joins four feature groups per company-quarter.
Every value is as of the quarter end, using the same rule as build_feature_matrix.py:
a value is used only if it was available (filing date / conservative availability) on or
before the quarter end.

  rpo_*              remaining performance obligations, latest balance available by quarter end
  goodwill_asof      goodwill balance, latest available by quarter end
  acq_cash_ttm       cash paid for acquisitions over the latest 12-month period available
  power_*            text flags from 10-K/10-Q sentences that mention power or electricity
                     costs together with a dollar figure, latest filing available by quarter end

Power features are text-derived and unvalidated: a dollar figure in a power sentence may be
a capex plan, a contract value or a historical comparison. They are flags for review.

Writes:
  output/feature_matrix_extended.csv   the matrix plus the new columns (original untouched)
  output/extended_features_summary.txt coverage by new column
"""

from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
SEC_ROOT = HERE / "extracts" / "sec"
MATRIX_IN = OUT / "feature_matrix_backtest.csv"
MATRIX_OUT = OUT / "feature_matrix_extended.csv"
SUMMARY_OUT = OUT / "extended_features_summary.txt"
FACTS = HERE / "extracts" / "company_metrics_expanded" / "reported_financial_facts.csv"

csv.field_size_limit(10**9)

# Cost phrasing only. Product descriptions such as "software for electric power transmission"
# do not match, because they lack a cost noun next to the power word.
POWER_RE = re.compile(
    r"\b(?:electricity|power|energy|utilities?|utility)\s+(?:costs?|expenses?|bills?|spend(?:ing)?|prices?|purchases?)\b"
    r"|\bpower and cooling\b|\bcooling and power\b",
    re.IGNORECASE,
)
RENT_RE = re.compile(r"\brents? and utilit", re.IGNORECASE)
USD_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:million|billion|thousand)?", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def quarter_end(label: str) -> str:
    y, q = int(label[:4]), int(label[-1])
    last = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
    return f"{y}-{last}"


def days_between(a: str, b: str) -> int:
    return (datetime.strptime(b, "%Y-%m-%d").date() - datetime.strptime(a, "%Y-%m-%d").date()).days


def load_facts():
    """Instant balances (RPO, goodwill) and durations (acquisition cash), keyed by cik."""
    instant: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    duration: dict[str, list[tuple[str, int, float]]] = defaultdict(list)
    wanted_instant = {"RevenueRemainingPerformanceObligation": "rpo", "Goodwill": "goodwill"}
    wanted_flow = "PaymentsToAcquireBusinessesNetOfCashAcquired"
    with FACTS.open(encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            tag = row["tag"]
            if row["unit"] != "USD" or not row["value"]:
                continue
            avail = row["available_date_conservative"] or row["filed_date"]
            if not avail:
                continue
            try:
                value = float(row["value"])
            except ValueError:
                continue
            if tag in wanted_instant and row["period_end"]:
                instant[(row["cik"], wanted_instant[tag])].append((avail, value, row["period_end"]))
            elif tag == wanted_flow and row["period_start"] and row["period_end"]:
                days = days_between(row["period_start"], row["period_end"])
                if 350 <= days <= 380:
                    duration[row["cik"]].append((avail, days, value))
    return instant, duration


def latest_asof(rows, as_of):
    """Latest (available, value, period_end) on or before as_of."""
    best = None
    for item in rows:
        avail = item[0]
        if avail <= as_of and (best is None or (avail, item[2]) > (best[0], best[2])):
            best = item
    return best


def scan_power_filings(ciks_to_ticker):
    """Per filing: power sentences with a dollar figure. Returns {(cik, filed_date): info}."""
    results = {}
    for cik, ticker in ciks_to_ticker.items():
        base = SEC_ROOT / ticker
        if not base.is_dir():
            continue
        for form in ("10-K", "10-Q"):
            for folder in (base / form).glob("*") if (base / form).is_dir() else []:
                filed = folder.name[:10]
                htm_files = list(folder.glob("*.htm")) + list(folder.glob("*.html"))
                if not htm_files:
                    continue
                main = max(htm_files, key=lambda p: p.stat().st_size)
                text = main.read_text(encoding="utf-8", errors="replace")
                text = SCRIPT_RE.sub(" ", text)
                text = html.unescape(TAG_RE.sub(" ", text))
                text = re.sub(r"\s+", " ", text)
                hits = []
                for sent in SENT_SPLIT.split(text):
                    # "rents and utilities" is an occupancy line, not power spend
                    if RENT_RE.search(sent):
                        continue
                    if POWER_RE.search(sent) and USD_RE.search(sent):
                        hits.append(sent[:400])
                results[(cik, filed, form)] = {
                    "hits": len(hits),
                    "example": hits[0] if hits else "",
                }
    return results


def main() -> int:
    instant, duration = load_facts()

    with MATRIX_IN.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        base_fields = reader.fieldnames
        rows = list(reader)

    ciks_to_ticker = {r["cik"]: r["ticker"] for r in rows}
    power = scan_power_filings(ciks_to_ticker)
    power_by_cik = defaultdict(list)
    for (cik, filed, form), info in power.items():
        power_by_cik[cik].append((filed, form, info))

    new_fields = [
        "rpo_balance", "rpo_as_of_period_end", "rpo_days_stale",
        "goodwill_asof", "acq_cash_ttm", "acq_cash_ttm_as_of",
        "power_filing_date", "power_filing_form", "power_usd_sentences", "power_example",
    ]

    out_rows = []
    for r in rows:
        cik, qe = r["cik"], r["quarter_end"]
        new = {k: "" for k in new_fields}

        rpo = latest_asof(instant.get((cik, "rpo"), []), qe)
        if rpo:
            new["rpo_balance"] = f"{rpo[1]:.0f}"
            new["rpo_as_of_period_end"] = rpo[2]
            new["rpo_days_stale"] = days_between(rpo[2], qe)

        gw = latest_asof(instant.get((cik, "goodwill"), []), qe)
        if gw:
            new["goodwill_asof"] = f"{gw[1]:.0f}"

        acq = [item for item in duration.get(cik, []) if item[0] <= qe]
        if acq:
            latest = max(acq, key=lambda x: (x[0], x[1]))
            new["acq_cash_ttm"] = f"{latest[2]:.0f}"
            new["acq_cash_ttm_as_of"] = latest[0]

        filings = [item for item in power_by_cik.get(cik, []) if item[0] <= qe]
        if filings:
            filed, form, info = max(filings, key=lambda x: x[0])
            new["power_filing_date"] = filed
            new["power_filing_form"] = form
            new["power_usd_sentences"] = info["hits"]
            new["power_example"] = info["example"]

        out_rows.append({**r, **new})

    fields = list(base_fields) + new_fields
    with MATRIX_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    total = len(out_rows)
    lines = [f"rows: {total}", "coverage of new columns (share of rows with a value):"]
    for k in new_fields:
        n = sum(1 for r in out_rows if r[k] not in ("", None))
        lines.append(f"  {k:<26} {n:>6} ({100 * n / total:.0f}%)")
    SUMMARY_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
