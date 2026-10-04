"""Annual values for the financial items the XBRL extract did not cover, 2022 onward.

Fills the "not built" items in checklist section 2 and section 3: G&A, advertising,
non-current deferred revenue, debt balances, convertible notes, and restructuring charges.

Reads companyfacts.json for each company (already on disk) and keeps annual 10-K values
(form 10-K, fiscal period FY) that end on or after 2022-01-01. For each metric, the first
tag that the company reports is used, in the order listed in METRICS. The tag that
supplied each value is kept, so a fallback (for example SG&A used in place of G&A) is
visible rather than silently mixed in.

Writes output/financial_gaps_annual.csv, one row per (company, metric, fiscal year end).
Standard library only.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = HERE / "output" / "financial_gaps_annual.csv"
START = "2022-01-01"

# metric -> tags in preference order. Only the first tag a company reports is used.
METRICS = {
    "general_and_administrative": ["GeneralAndAdministrativeExpense", "SellingGeneralAndAdministrativeExpense"],
    "advertising_expense": ["AdvertisingExpense"],
    "deferred_revenue_noncurrent": ["DeferredRevenueNoncurrent", "ContractWithCustomerLiabilityNoncurrent"],
    "long_term_debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "long_term_debt_current": ["LongTermDebtCurrent"],
    "convertible_notes_noncurrent": ["ConvertibleNotesPayable"],
    "convertible_notes_current": ["ConvertibleNotesPayableCurrent"],
    "restructuring_charges": ["RestructuringCharges", "RestructuringAndRelatedCostIncurredCost", "BusinessExitCosts1"],
}
FIELDS = ["cik", "ticker", "name", "metric", "source_tag", "fiscal_year_end", "value", "unit", "accession", "filed"]


def annual_values(facts: dict, tag: str) -> list[dict]:
    """Annual 10-K values for one tag, one per fiscal year end, latest filing wins."""
    node = facts.get("us-gaap", {}).get(tag)
    if not node:
        return []
    unit_key = "USD" if "USD" in node.get("units", {}) else next(iter(node.get("units", {})), None)
    if unit_key is None:
        return []
    by_end: dict[str, dict] = {}
    for e in node["units"][unit_key]:
        if e.get("form") != "10-K" or e.get("fp") != "FY":
            continue
        end = e.get("end", "")
        if end < START:
            continue
        # Keep the most recently filed value for each period end
        if end not in by_end or e.get("filed", "") > by_end[end].get("filed", ""):
            by_end[end] = {**e, "unit": unit_key}
    return list(by_end.values())


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    rows = []
    coverage = {m: 0 for m in METRICS}
    for c in companies:
        ticker = (c["ticker"] or "").strip()
        cf = SEC / ticker / "companyfacts.json" if ticker else None
        if cf is None or not cf.exists():
            cf = SEC / c["cik"].zfill(10) / "companyfacts.json"
        if not cf.exists():
            continue
        facts = json.loads(cf.read_text(encoding="utf-8")).get("facts", {})
        for metric, tags in METRICS.items():
            for tag in tags:
                values = annual_values(facts, tag)
                if not values:
                    continue
                coverage[metric] += 1
                for v in values:
                    rows.append({
                        "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                        "metric": metric, "source_tag": tag,
                        "fiscal_year_end": v["end"], "value": v["val"], "unit": v["unit"],
                        "accession": v.get("accn", ""), "filed": v.get("filed", ""),
                    })
                break  # first tag the company reports wins

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["ticker"], r["metric"], r["fiscal_year_end"])))

    print(f"Wrote {len(rows)} annual values to {OUT}")
    print("Companies with a value, by metric:")
    for m in METRICS:
        print(f"  {m}: {len({r['cik'] for r in rows if r['metric'] == m})}")
    fallbacks = sorted({r['metric'] + ' <- ' + r['source_tag'] for r in rows
                        if r['source_tag'] != METRICS[r['metric']][0]})
    print("Fallback tags used:", fallbacks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
