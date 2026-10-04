"""Fill the remaining XBRL-sourced partial items in one pass over companyfacts.

Completes these checklist items from structured data rather than text, which is both more
reliable and faster:
  1.6  public float                 dei:EntityPublicFloat
  3.5  convertible debt             the full set of convertible tags, not just two
  5.3  deal consideration, goodwill acquired, divestiture proceeds
  6.1  customer concentration %     ConcentrationRiskPercentage1
  10.1 loss contingencies           accruals, damages sought, estimated possible loss

Annual 10-K values from 2022 on, one per fiscal year end, latest filing winning.
The tag that supplied each value is recorded, so a fallback is visible.

Writes output/xbrl_gaps_annual.csv.

Caveats:
  - ConcentrationRiskPercentage1 is normally tagged per customer with a dimension. The
    companyfacts API drops dimensions, so a company with several large customers can show
    several values for one year and they cannot be attributed to a named customer here.
  - GoodwillAcquiredDuringPeriod is goodwill added in the year across all acquisitions,
    not per deal.
  - A blank means the company does not report that tag, not zero.
Standard library only.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = HERE / "output" / "xbrl_gaps_annual.csv"

_spec = importlib.util.spec_from_file_location("gaps", HERE / "extract_financial_gaps.py")
_gaps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gaps)
annual_values = _gaps.annual_values

# metric -> (namespace, tags in preference order). First tag the company reports is used.
METRICS = {
    "public_float": ("dei", ["EntityPublicFloat"]),
    "convertible_debt_noncurrent": ("us-gaap", ["ConvertibleDebtNoncurrent", "ConvertibleNotesPayable"]),
    "convertible_debt_current": ("us-gaap", ["ConvertibleDebtCurrent", "ConvertibleNotesPayableCurrent"]),
    "convertible_debt_total": ("us-gaap", ["ConvertibleDebt"]),
    "acquisition_consideration": ("us-gaap", ["BusinessCombinationConsiderationTransferred1"]),
    "acquisition_consideration_in_equity": ("us-gaap", ["BusinessCombinationConsiderationTransferredEquityInterestsIssuedAndIssuable"]),
    "acquisition_cash_paid_gross": ("us-gaap", ["PaymentsToAcquireBusinessesGross"]),
    "goodwill_acquired_in_year": ("us-gaap", ["GoodwillAcquiredDuringPeriod"]),
    "acquired_intangibles": ("us-gaap", ["BusinessCombinationRecognizedIdentifiableAssetsAcquiredAndLiabilitiesAssumedIntangibleAssetsOtherThanGoodwill"]),
    "acquisition_related_costs": ("us-gaap", ["BusinessCombinationAcquisitionRelatedCosts"]),
    "divestiture_proceeds": ("us-gaap", ["ProceedsFromDivestitureOfBusinesses", "ProceedsFromDivestitureOfInterestInConsolidatedSubsidiaries"]),
    "customer_concentration_pct": ("us-gaap", ["ConcentrationRiskPercentage1"]),
    "loss_contingency_accrual": ("us-gaap", ["LossContingencyAccrualAtCarryingValue"]),
    "loss_contingency_damages_sought": ("us-gaap", ["LossContingencyDamagesSoughtValue"]),
    "loss_contingency_possible_loss": ("us-gaap", ["LossContingencyEstimateOfPossibleLoss"]),
}
# period_end, not fiscal_year_end: for public float this is the SEC measurement date (the
# last business day of the second fiscal quarter), not the year end.
FIELDS = ["cik", "ticker", "name", "metric", "source_tag", "period_end", "value", "unit",
          "validation", "accession", "filed"]
# A float more than this multiple of current market cap is a filer tagging error, not a
# real number. HubSpot tags its float 1000x too large (13.7 trillion for 2022).
FLOAT_SANITY_MULTIPLE = 20


def market_caps() -> dict[str, float]:
    """Current market cap per ticker, used to sanity-check public float."""
    path = HERE / "output" / "ticker_details.csv"
    caps = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("market_cap"):
                    try:
                        caps[r["ticker"]] = float(r["market_cap"])
                    except ValueError:
                        pass
    return caps


def validate(metric: str, value: float, ticker: str, caps: dict[str, float]) -> str:
    if metric == "public_float":
        cap = caps.get(ticker)
        if cap and value > cap * FLOAT_SANITY_MULTIPLE:
            return (f"check: {value/cap:.0f}x current market cap. Either a filer scale error "
                    f"(HubSpot tags 1000x too large) or a large decline since the measurement date")
        if value == 0:
            return "zero float reported; normal if the company listed after the measurement date"
    if metric == "customer_concentration_pct" and value > 1:
        return "value above 1; check whether the filer tagged percent or fraction"
    return "ok"


def main() -> int:
    caps = market_caps()
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
        for metric, (namespace, tags) in METRICS.items():
            # annual_values reads the us-gaap namespace; dei tags are passed in the same shape
            scoped = facts if namespace == "us-gaap" else {"us-gaap": facts.get("dei", {})}
            for tag in tags:
                values = annual_values(scoped, tag)
                if not values:
                    continue
                for v in values:
                    rows.append({
                        "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                        "metric": metric, "source_tag": tag,
                        "period_end": v["end"], "value": v["val"], "unit": v["unit"],
                        "validation": validate(metric, float(v["val"]), ticker, caps),
                        "accession": v.get("accn", ""), "filed": v.get("filed", ""),
                    })
                break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["ticker"], r["metric"], r["period_end"])))

    print(f"Wrote {len(rows)} annual values to {OUT}")
    for m in METRICS:
        print(f"  {m}: {len({r['cik'] for r in rows if r['metric'] == m})} companies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
