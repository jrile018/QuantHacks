"""One deal table per company-year, joining every acquisition source (checklist item 5.3).

Pulls together what the separate extracts hold:
  closing reports     8-K Item 2.01 filings, which report a completed acquisition
  agreement dates     8-K Item 1.01 filings, which report the signing
  consideration       XBRL BusinessCombinationConsiderationTransferred1 and the equity and
                      gross-cash variants
  goodwill added      XBRL GoodwillAcquiredDuringPeriod, the widest-coverage deal signal
  acquired intangibles and acquisition costs
  divestiture proceeds
  verified prices     the hand-checked per-deal prices in deal_terms_reviewed.csv

Writes output/deal_summary_by_company_year.csv, one row per company and fiscal year that
has any deal activity, so a year with an acquisition is separable from a quiet one.

Caveats:
  - XBRL figures are annual totals across all deals in the year, not per deal.
  - An 8-K 2.01 is filed on completion, so its date is the closing report date, which can
    trail the actual closing by up to four business days.
  - A company can show goodwill added with no 2.01 filing when the deal was too small to
    be material enough to report.
Standard library only.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output"
OUT = OUT_DIR / "deal_summary_by_company_year.csv"
XBRL_METRICS = {
    "acquisition_consideration": "consideration_transferred",
    "acquisition_consideration_in_equity": "consideration_in_equity",
    "acquisition_cash_paid_gross": "cash_paid_gross",
    "goodwill_acquired_in_year": "goodwill_added",
    "acquired_intangibles": "intangibles_acquired",
    "acquisition_related_costs": "acquisition_costs",
    "divestiture_proceeds": "divestiture_proceeds",
}


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    companies = {r["ticker"]: r for r in read(HERE / "packaged_software_companies.csv") if r["ticker"]}

    # Deal activity by (ticker, year)
    cell: dict[tuple[str, str], dict] = defaultdict(dict)

    for r in read(OUT_DIR / "xbrl_gaps_annual.csv"):
        metric = XBRL_METRICS.get(r["metric"])
        if not metric or not r["ticker"]:
            continue
        year = r["period_end"][:4]
        cell[(r["ticker"], year)][metric] = r["value"]
        cell[(r["ticker"], year)].setdefault("fiscal_year_end", r["period_end"])

    for r in read(OUT_DIR / "8k_item_filings.csv"):
        if r["item"] not in ("2.01", "1.01") or not r["ticker"]:
            continue
        date = r["filing_folder"].split("_")[0]
        key = (r["ticker"], date[:4])
        field = "closing_reports_8k_2_01" if r["item"] == "2.01" else "agreement_reports_8k_1_01"
        cell[key][field] = str(int(cell[key].get(field, 0) or 0) + 1)
        if r["item"] == "2.01":
            dates = cell[key].get("closing_report_dates", "")
            cell[key]["closing_report_dates"] = f"{dates}; {date}".strip("; ")

    # Verified per-deal prices are deliberately not joined here. deal_terms_reviewed.csv has
    # no deal date, so attaching a price to a fiscal year would be a guess. A flag records
    # that the company has at least one hand-verified price, and the price itself stays in
    # that file, keyed by deal.
    verified_tickers = {r["ticker"] for r in read(OUT_DIR / "deal_terms_reviewed.csv")
                        if r.get("decision", "").startswith("confirmed")}

    fields = (["cik", "ticker", "name", "year", "fiscal_year_end",
               "closing_reports_8k_2_01", "agreement_reports_8k_1_01", "closing_report_dates"]
              + list(XBRL_METRICS.values()) + ["has_verified_price_in_review_file"])
    rows = []
    for (ticker, year), data in sorted(cell.items()):
        c = companies.get(ticker)
        if not c:
            continue
        row = {f: "" for f in fields}
        row.update({"cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"], "year": year})
        row.update({k: v for k, v in data.items() if k in row})
        row["has_verified_price_in_review_file"] = "yes" if ticker in verified_tickers else ""
        rows.append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    with_goodwill = sum(1 for r in rows if r["goodwill_added"])
    with_closing = sum(1 for r in rows if r["closing_reports_8k_2_01"])
    print(f"Wrote {len(rows)} company-year rows to {OUT}")
    print(f"  companies covered: {len({r['ticker'] for r in rows})}")
    print(f"  rows with goodwill added: {with_goodwill}")
    print(f"  rows with an 8-K 2.01 closing report: {with_closing}")
    print(f"  rows with divestiture proceeds: {sum(1 for r in rows if r['divestiture_proceeds'])}")
    print(f"  companies with a hand-verified deal price (in deal_terms_reviewed.csv): {len(verified_tickers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
