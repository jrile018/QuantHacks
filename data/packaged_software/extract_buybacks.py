"""Share repurchases (buybacks) per fiscal year, 2022 onward, from XBRL on disk.

Checklist section 3. For each company, reads annual 10-K values of:
  cash_paid_for_repurchases  cash spent on buybacks, from the cash-flow statement
  value_repurchased          value of shares repurchased in the year (equity statement)
  shares_repurchased         number of shares repurchased and retired in the year

Tags are tried in the order listed in METRICS, and the first one a company reports is used.
The tag that supplied each value is kept, so a fallback is visible.

Writes output/buybacks_annual.csv, one row per (company, metric, fiscal year end).
Standard library only. Reuses the annual-value reader from extract_financial_gaps.py.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = HERE / "output" / "buybacks_annual.csv"

_spec = importlib.util.spec_from_file_location("gaps", HERE / "extract_financial_gaps.py")
_gaps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gaps)
annual_values = _gaps.annual_values

METRICS = {
    "cash_paid_for_repurchases": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
    ],
    "value_repurchased": [
        "StockRepurchasedAndRetiredDuringPeriodValue",
        "StockRepurchasedDuringPeriodValue",
        "TreasuryStockValueAcquiredCostMethod",
    ],
    "shares_repurchased": [
        "StockRepurchasedAndRetiredDuringPeriodShares",
        "TreasuryStockSharesAcquired",
    ],
}
FIELDS = ["cik", "ticker", "name", "metric", "source_tag", "fiscal_year_end", "value", "unit", "accession", "filed"]


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    rows = []
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
                for v in values:
                    rows.append({
                        "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                        "metric": metric, "source_tag": tag,
                        "fiscal_year_end": v["end"], "value": v["val"], "unit": v["unit"],
                        "accession": v.get("accn", ""), "filed": v.get("filed", ""),
                    })
                break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["ticker"], r["metric"], r["fiscal_year_end"])))

    print(f"Wrote {len(rows)} annual values to {OUT}")
    for m in METRICS:
        companies_with = {r["cik"] for r in rows if r["metric"] == m}
        print(f"  {m}: {len(companies_with)} companies")
    fallbacks = sorted({f"{r['metric']} <- {r['source_tag']}" for r in rows if r["source_tag"] != METRICS[r["metric"]][0]})
    print("Fallback tags used:", fallbacks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
