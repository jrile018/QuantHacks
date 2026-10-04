"""Source-linked, standard XBRL cash movement facts from SEC Company Facts.

These are reported facts, not inferred transactions or loan-level records.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
import json
import math
import re


TAGS = {
    "NetCashProvidedByUsedInOperatingActivities": "operating",
    "NetCashProvidedByUsedInInvestingActivities": "investing",
    "NetCashProvidedByUsedInFinancingActivities": "financing",
    "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "fx",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": "cash_change",
    "ProceedsFromIssuanceOfLongTermDebt": "debt_proceeds",
    "RepaymentsOfLongTermDebt": "debt_repayments",
    "ProceedsFromBorrowings": "borrowing_proceeds",
    "RepaymentsOfBorrowings": "borrowing_repayments",
    "PaymentsOfDividends": "dividends_paid",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capital_expenditure",
    "PaymentsToAcquireRealEstate": "real_estate_acquisitions",
    "ProceedsFromSaleOfRealEstate": "real_estate_sale_proceeds",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect": "cash_change_excluding_fx",
    "CashAndCashEquivalentsPeriodIncreaseDecrease": "cash_change",
    "CashAndCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect": "cash_change_excluding_fx",
    "EffectOfExchangeRateOnCashAndCashEquivalents": "fx",
    "ProceedsFromIssuanceOfDebt": "debt_issuance_proceeds",
    "RepaymentsOfDebt": "debt_payments",
    "ProceedsFromIssuanceOfSecuredDebt": "secured_debt_proceeds",
    "RepaymentsOfSecuredDebt": "secured_debt_payments",
    "ProceedsFromIssuanceOfUnsecuredDebt": "unsecured_debt_proceeds",
    "RepaymentsOfUnsecuredDebt": "unsecured_debt_payments",
    "ProceedsFromRepaymentsOfShortTermDebt": "short_term_debt_net_flow",
    "ProceedsFromIssuanceOfCommonStock": "common_equity_proceeds",
    "ProceedsFromIssuanceOfPreferredStockAndPreferenceStock": "preferred_equity_proceeds",
    "PaymentsForRepurchaseOfCommonStock": "common_share_repurchases",
    "PaymentsToAcquireBusinessesNetOfCashAcquired": "business_acquisitions_net_cash",
    "PaymentsToAcquireLoansReceivable": "loans_purchased",
    "PaymentsForLoans": "payments_for_loans",
    "ProceedsFromCollectionOfLoansReceivable": "loan_collections",
    "ProceedsFromSaleOfLoansReceivable": "loan_sale_proceeds",
    "ProceedsFromSaleAndCollectionOfLoansReceivable": "loan_sales_and_collections",
    "PaymentsToDevelopRealEstateAssets": "real_estate_development",
    "ProceedsFromDistributionsReceivedFromRealEstatePartnerships": "real_estate_partnership_distributions",
}
BALANCE_TAGS = {
    "DebtCurrent": "current_debt_reported",
    "LongTermDebtCurrent": "long_term_debt_current",
    "LongTermDebtNoncurrent": "long_term_debt_noncurrent",
    "LongTermDebt": "long_term_debt_reported",
    "CashAndCashEquivalentsAtCarryingValue": "cash_balance",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "cash_and_restricted_cash_balance",
}
CASH_BASIS = {
    tag: "cash_and_equivalents" if tag in {
        "CashAndCashEquivalentsPeriodIncreaseDecrease",
        "CashAndCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
        "EffectOfExchangeRateOnCashAndCashEquivalents",
    } else "cash_and_restricted_cash"
    for tag, metric in TAGS.items() if metric in {"fx", "cash_change", "cash_change_excluding_fx"}
}
BRIDGE = ("operating", "investing", "financing", "fx", "cash_change", "cash_change_excluding_fx")
CORE_COMPONENTS = ("operating", "investing", "financing")


def _rounding_bound(decimals) -> Decimal | None:
    if str(decimals).upper() == "INF":
        return Decimal(0)
    if not re.fullmatch(r"[+-]?\d+", str(decimals)):
        return None
    precision = int(decimals)
    if not -20 <= precision <= 20:
        return None
    return Decimal("0.5") * Decimal(10) ** (-precision)


def cash_flow_rows(cik: str, companyfacts: dict) -> list[dict]:
    """Return selected monetary flows and balance snapshots separately.

    Detail concepts overlap: never sum all rows into a debt or cash total.
    CompanyFacts ordinarily omits XBRL decimals and custom/dimensional facts.
    """
    cik = str(cik).strip()
    if not re.fullmatch(r"\d{1,10}", cik) or int(cik) == 0:
        raise ValueError("Invalid issuer CIK")
    cik = cik.zfill(10)
    rows = []
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    for tag, metric in {**TAGS, **BALANCE_TAGS}.items():
        for unit, items in us_gaap.get(tag, {}).get("units", {}).items():
            if not re.fullmatch(r"[A-Z]{3}", unit):
                continue
            for item in items:
                accession = item.get("accn", "")
                value = item.get("val")
                start, end = item.get("start", ""), item.get("end", "")
                is_balance = tag in BALANCE_TAGS
                if (not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession)
                        or not isinstance(value, (int, float)) or isinstance(value, bool)
                        or not math.isfinite(value) or not end or (not is_balance and not start)):
                    continue
                try:
                    date.fromisoformat(end)
                    if start and date.fromisoformat(start) > date.fromisoformat(end):
                        continue
                except (TypeError, ValueError):
                    continue
                if is_balance and start:
                    continue
                direction = "balance" if is_balance else "signed_net" if metric in BRIDGE or "FromRepaymentsOf" in tag else (
                    "outflow" if tag.startswith(("Payments", "Repayments")) else "inflow")
                rows.append({
                    "cik": cik, "metric": metric, "tag": tag, "value": value,
                    "unit": unit, "accession": accession, "form": item.get("form", ""),
                    "filed": item.get("filed", ""), "period_start": start,
                    "period_end": end, "fiscal_year": item.get("fy", ""),
                    "fiscal_period": item.get("fp", ""),
                    "amount_kind": "balance" if is_balance else "flow",
                    "cash_direction": direction, "cash_basis": CASH_BASIS.get(tag, ""),
                    "decimals": item.get("decimals", ""),
                    "precision_status": "reported" if _rounding_bound(item.get("decimals")) is not None else "unknown",
                    "filing_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.html",
                    "data_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                    "source_method": "sec_companyfacts_xbrl",
                })
    return sorted(rows, key=lambda row: (row["accession"], row["period_start"], row["period_end"], row["metric"]))


def cash_bridge_checks(rows: list[dict]) -> list[dict]:
    """Check reported cash change against the four cash flow components.

    A complete bridge is arithmetic evidence only; it does not validate OCR,
    XBRL tagging, loan terms, or the company's financial statements.
    """
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        if row["metric"] in BRIDGE:
            key = (row["cik"], row["accession"], row["period_start"], row["period_end"], row["unit"])
            grouped[key].append(row)
    checks = []
    for (cik, accession, start, end, unit), context in sorted(grouped.items()):
        targets = sorted({(row["metric"], row.get("cash_basis", "")) for row in context
                          if row["metric"] in {"cash_change", "cash_change_excluding_fx"}})
        if not targets:
            targets = [("cash_change", "unspecified")]
        for target, basis in targets:
            include_fx = target == "cash_change"
            required = (*CORE_COMPONENTS, "fx", target) if include_fx else (*CORE_COMPONENTS, target)
            metrics: dict[str, list[dict]] = defaultdict(list)
            for row in context:
                metric = row["metric"]
                if metric in required and (metric in CORE_COMPONENTS or row.get("cash_basis", "") == basis):
                    metrics[metric].append(row)
            missing = [metric for metric in required if metric not in metrics]
            ambiguous = [f"ambiguous:{metric}" for metric in required if metric in metrics
                         and len({row["value"] for row in metrics[metric]}) > 1]
            bounds = [_rounding_bound(metrics[metric][0].get("decimals")) for metric in required if metric in metrics]
            tolerance = sum(bounds, Decimal(0)) if not missing and all(bound is not None for bound in bounds) else None
            if missing or ambiguous:
                status, calculated, difference = "incomplete", "", ""
            else:
                calculated = sum((Decimal(str(metrics[metric][0]["value"])) for metric in required[:-1]), Decimal(0))
                difference = Decimal(str(metrics[target][0]["value"])) - calculated
                status = "balanced" if abs(difference) <= (tolerance or Decimal(0)) else "unresolved"
                calculated, difference = float(calculated), float(difference)
            exemplar = context[0]
            checks.append({
                "cik": cik, "accession": accession, "period_start": start,
                "period_end": end, "unit": unit, "status": status,
                "missing": ",".join(missing + ambiguous), "calculated_cash_change": calculated,
                "reported_cash_change": metrics[target][0]["value"] if target in metrics and
                                        f"ambiguous:{target}" not in ambiguous else "",
                "difference": difference, "filing_url": exemplar["filing_url"],
                "cash_basis": basis, "fx_included": include_fx,
                "tolerance": float(tolerance) if tolerance is not None else "",
                "precision_status": "reported" if tolerance is not None else "unknown",
                "component_tags": json.dumps({metric: sorted({row["tag"] for row in values}) for metric, values in metrics.items()}, sort_keys=True),
                "duplicate_fact_count": sum(max(0, len(values) - 1) for values in metrics.values()),
            })
    return checks
