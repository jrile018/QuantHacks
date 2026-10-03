"""SEC-sourced financial metrics and disclosure evidence since 2022.

Uses the current 168-company CSV. Reuses downloaded SEC API/filing data and can
fetch missing API records. Disclosures are candidates, not verified AI adoption.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import re
import statistics
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from sec_common import SecClient

FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A", "8-K", "8-K/A"}
# Similar-sounding concepts are deliberately kept distinct.
FLOWS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "rd_expense": ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"],
    "sales_marketing": ["SellingAndMarketingExpense"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "stock_comp": ["ShareBasedCompensation"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "physical_asset_purchases": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "productive_asset_purchases": ["PaymentsToAcquireProductiveAssets"],
    "software_development_cash_payments": ["PaymentsToDevelopSoftware"],
    "capitalized_software_additions": ["CapitalizedComputerSoftwareAdditions"],
    "acquisitions": ["PaymentsToAcquireBusinessesNetOfCashAcquired"],
    "intangible_amortization": ["AmortizationOfIntangibleAssets"],
    "land_purchases": ["PaymentsToAcquireLand"],
    "land_held_for_use_purchases": ["PaymentsToAcquireLandHeldForUse"],
    "building_purchases": ["PaymentsToAcquireBuildings"],
    "equipment_on_lease_purchases": ["PaymentsToAcquireEquipmentOnLease"],
}
INSTANTS = {
    "total_assets": ["Assets"], "goodwill": ["Goodwill"],
    "intangibles_net": ["IntangibleAssetsNetExcludingGoodwill"],
    "ppe_net": ["PropertyPlantAndEquipmentNet"], "ppe_gross": ["PropertyPlantAndEquipmentGross"],
    "land_balance": ["Land"], "land_and_improvements_balance": ["LandAndLandImprovements"],
    "machinery_equipment_gross": ["MachineryAndEquipmentGross"],
    "buildings_improvements_gross": ["BuildingsAndImprovementsGross"],
    "operating_lease_rou": ["OperatingLeaseRightOfUseAsset"],
    "finance_lease_rou": ["FinanceLeaseRightOfUseAsset"],
    "capitalized_software_net": ["CapitalizedComputerSoftwareNet"],
    "hosting_implementation_cost_asset_net": ["HostingArrangementServiceContractImplementationCostCapitalizedAfterAccumulatedAmortization"],
    "deferred_revenue_current": ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"],
    "rpo": ["RevenueRemainingPerformanceObligation"],
    "purchase_obligations": ["PurchaseObligation"],
    "purchase_obligations_next_12_months": ["PurchaseObligationDueInNextTwelveMonths"],
    "unrecorded_unconditional_purchase_obligations": ["UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount"],
}
METRICS = {**FLOWS, **INSTANTS}
ID = ["cik", "ticker", "name"]
FACT_FIELDS = ID + ["metric", "taxonomy", "tag", "unit", "period_start", "period_end", "value", "filed_date", "available_date_conservative", "form", "accession", "source_url", "pre_2022_context"]
PROVENANCE_FIELDS = ID + ["period_end", "metric", "basis", "value", "method", "quality", "available_date_conservative", "source_fact_ids"]
RATIOS = ["rd_pct_rev", "sm_pct_rev", "sbc_pct_rev", "gross_margin", "physical_capex_pct_rev", "fcf_physical_capex_margin", "goodwill_to_assets", "purchase_obligations_pct_ttm_rev", "rev_growth_yoy_q"]
QUARTER_FIELDS = ID + ["period_start", "period_end", "available_date_conservative", "history_limitation", "derivation_quality"] + [field for m in FLOWS for field in (f"q_{m}", f"ttm_{m}")] + list(INSTANTS) + RATIOS
EVIDENCE_FIELDS = ID + ["evidence_id", "category", "classification", "review_status", "form", "accession", "filed_date", "available_date_conservative", "source_url", "local_path", "excerpt", "vendors_mentioned", "numeric_mentions_unvalidated", "amount_usd", "employee_seats", "first_seen_in_scanned_filings"]
INLINE_FIELDS = ID + ["tag", "value", "raw_value", "unit", "period_start", "period_end", "dimensions", "form", "accession", "filed_date", "available_date_conservative", "source_url", "context_id", "numeric_status", "interpretation_status"]


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def next_day(date):
    return (dt.date.fromisoformat(date[:10]) + dt.timedelta(days=1)).isoformat()


def days(start, end):
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


def source_url(cik, accession):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.html"


def collect_facts(company, data, as_of):
    out = defaultdict(list)
    for metric, tags in METRICS.items():
        for priority, tag in enumerate(tags):
            concept = data.get("facts", {}).get("us-gaap", {}).get(tag, {})
            for fact in concept.get("units", {}).get("USD", []):
                if (fact.get("form") not in FORMS or not fact.get("filed")
                        or fact["filed"] > as_of or not fact.get("accn")):
                    continue
                record = {**fact, "tag": tag, "priority": priority, "metric": metric}
                record["id"] = hashlib.sha256(json.dumps({"cik": company["cik"], **record}, sort_keys=True).encode()).hexdigest()[:24]
                out[metric].append(record)
    return out


def value_record(value, start, end, facts, method, quality):
    return {"value": value, "start": start, "end": end, "facts": facts,
            "filed": max(f["filed"] for f in facts), "method": method, "quality": quality}


def quarterly_series(facts):
    """Earliest direct quarters, or explicitly flagged cross-filing YTD differences."""
    best = {}
    for f in sorted(facts, key=lambda f: (f["filed"], f["priority"], f["accn"])):
        if f.get("start"):
            best.setdefault((f["tag"], f["start"], f["end"]), f)
    result = {}
    candidates = []
    for f in best.values():
        if 80 <= days(f["start"], f["end"]) <= 100:
            candidates.append(value_record(f["val"], f["start"], f["end"], [f], "reported_quarter", "reported"))
    groups = defaultdict(list)
    for f in best.values():
        groups[(f["tag"], f["start"])].append(f)
    for (_, start), group in groups.items():
        group.sort(key=lambda f: f["end"])
        for prev, current in zip(group, group[1:]):
            if not (80 <= days(prev["end"], current["end"]) <= 100 and 150 <= days(start, current["end"]) <= 380):
                continue
            # Use the prior cumulative period from the SAME accession if available.
            compatible = [f for f in facts if f["tag"] == current["tag"] and f.get("start") == start
                          and f["end"] == prev["end"] and f["accn"] == current["accn"]]
            prior = compatible[0] if compatible else prev
            quality = "same_filing_difference" if compatible else "cross_filing_basis_unverified"
            qstart = next_day(prev["end"])
            candidates.append(value_record(current["val"] - prior["val"], qstart, current["end"],
                                           [current, prior], "ytd_difference", quality))
    # Earliest availability first; prefer direct reporting when availability is equal.
    for q in sorted(candidates, key=lambda q: (q["filed"], q["method"] != "reported_quarter", q["facts"][0]["priority"])):
        result.setdefault(q["end"], q)
    # Q4 when annual totals and three direct or derived quarters are available.
    for f in sorted(best.values(), key=lambda f: (f["filed"], f["priority"])):
        if f["end"] in result or not 350 <= days(f["start"], f["end"]) <= 380:
            continue
        preceding = sorted((q for q in result.values() if f["start"] <= q["start"] and q["end"] < f["end"]), key=lambda q: q["end"])
        if len(preceding) != 3 or any(q["facts"][0]["tag"] != f["tag"] for q in preceding):
            continue
        boundaries = [days(f["start"], preceding[0]["end"])] + [days(a["end"], b["end"]) for a, b in zip(preceding, preceding[1:])] + [days(preceding[-1]["end"], f["end"])]
        if not all(80 <= n <= 100 for n in boundaries):
            continue
        refs = [f] + [ref for q in preceding for ref in q["facts"]]
        result[f["end"]] = value_record(f["val"] - sum(q["value"] for q in preceding), next_day(preceding[-1]["end"]), f["end"], refs,
                                         "annual_minus_three_quarters", "cross_filing_basis_unverified")
    return result


def instant_series(facts):
    result = {}
    for f in sorted(facts, key=lambda f: (f["filed"], f["priority"], f["accn"])):
        if not f.get("start"):
            result.setdefault(f["end"], value_record(f["val"], "", f["end"], [f], "reported_instant", "reported"))
    return result


def trailing(series, end, quarter):
    if end not in series or abs(days(series[end]["start"], quarter["start"])) > 3:
        return None
    values = [series[e] for e in sorted(series) if e <= end][-4:]
    if len(values) != 4 or any(not 80 <= days(a["end"], b["end"]) <= 100 or abs(days(next_day(a["end"]), b["start"])) > 3 for a, b in zip(values, values[1:])):
        return None
    refs = [f for v in values for f in v["facts"]]
    quality = "cross_filing_basis_unverified" if any(v["quality"] == "cross_filing_basis_unverified" for v in values) else "reported_or_same_filing_derived"
    return value_record(sum(v["value"] for v in values), values[0]["start"], end, refs, "four_consecutive_quarters", quality)


def ratio(a, b):
    return a / b if a is not None and b is not None and b > 0 else ""


def build_quarters(company, facts, start, end):
    flows = {m: quarterly_series(facts[m]) for m in FLOWS}
    instants = {m: instant_series(facts[m]) for m in INSTANTS}
    rows, provenance = [], []
    for period_end, revenue in sorted(flows["revenue"].items()):
        if not start <= period_end <= end:
            continue
        row = {**{k: company[k] for k in ID}, "period_start": revenue["start"], "period_end": period_end,
               "history_limitation": "current_universe_earliest_reported_facts_not_full_vintage_history"}
        used, totals, balances = [], {}, {}
        for m, series in flows.items():
            q = series.get(period_end)
            if q and abs(days(q["start"], revenue["start"])) > 3:
                q = None
            t = trailing(series, period_end, revenue)
            row[f"q_{m}"] = q["value"] if q else ""
            row[f"ttm_{m}"] = t["value"] if t else ""
            totals[m] = t["value"] if t else None
            for basis, v in (("quarter", q), ("ttm", t)):
                if v:
                    used.append(v)
                    provenance.append({**{k: company[k] for k in ID}, "period_end": period_end,
                                       "metric": m, "basis": basis, "value": v["value"],
                                       "method": v["method"], "quality": v["quality"],
                                       "available_date_conservative": next_day(v["filed"]),
                                       "source_fact_ids": ";".join(sorted({f["id"] for f in v["facts"]}))})
        for m, series in instants.items():
            v = series.get(period_end)
            row[m] = v["value"] if v else ""
            balances[m] = v["value"] if v else None
            if v:
                used.append(v)
                provenance.append({**{k: company[k] for k in ID}, "period_end": period_end,
                                   "metric": m, "basis": "instant", "value": v["value"], "method": v["method"],
                                   "quality": v["quality"], "available_date_conservative": next_day(v["filed"]),
                                   "source_fact_ids": v["facts"][0]["id"]})
        revenue_ttm = totals["revenue"]
        gross = totals["gross_profit"]
        if gross is None and revenue_ttm is not None and totals["cost_of_revenue"] is not None:
            gross = revenue_ttm - totals["cost_of_revenue"]
        ocf, physical = totals["operating_cash_flow"], totals["physical_asset_purchases"]
        fcf = ocf - physical if ocf is not None and physical is not None else None
        row.update(rd_pct_rev=ratio(totals["rd_expense"], revenue_ttm),
                   sm_pct_rev=ratio(totals["sales_marketing"], revenue_ttm),
                   sbc_pct_rev=ratio(totals["stock_comp"], revenue_ttm), gross_margin=ratio(gross, revenue_ttm),
                   physical_capex_pct_rev=ratio(physical, revenue_ttm), fcf_physical_capex_margin=ratio(fcf, revenue_ttm),
                   goodwill_to_assets=ratio(balances["goodwill"], balances["total_assets"]),
                   purchase_obligations_pct_ttm_rev=ratio(balances["purchase_obligations"], revenue_ttm),
                   rev_growth_yoy_q="")
        prior = sorted((q for q in flows["revenue"].values() if 350 <= days(q["end"], period_end) <= 380), key=lambda q: abs(days(q["end"], period_end) - 365))
        if prior and prior[0]["value"] > 0:
            row["rev_growth_yoy_q"] = revenue["value"] / prior[0]["value"] - 1
            used.append(prior[0])
            provenance.append({**{k: company[k] for k in ID}, "period_end": period_end,
                               "metric": "rev_growth_yoy_q", "basis": "ratio", "value": row["rev_growth_yoy_q"],
                               "method": "quarter_over_prior_year_quarter_minus_one", "quality": "period_match_within_350_380_days",
                               "available_date_conservative": next_day(max(revenue["filed"], prior[0]["filed"])),
                               "source_fact_ids": ";".join(sorted({f["id"] for v in (revenue, prior[0]) for f in v["facts"]}))})
        row["available_date_conservative"] = next_day(max(v["filed"] for v in used))
        row["derivation_quality"] = "contains_cross_filing_basis_unverified" if any(v["quality"] == "cross_filing_basis_unverified" for v in used) else "reported_or_same_filing_derived"
        rows.append(row)
    return rows, provenance


class FilingText(HTMLParser):
    """Ignore hidden XBRL and scripts; preserve visible text for evidence snippets."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.stack = [], []
        self.hidden = 0
        self.links = []
        self.contexts, self.units, self.inline = {}, {}, []
        self.context, self.unit, self.number, self.capture = None, None, None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "xbrli:context":
            self.context = {"id": attrs.get("id", ""), "dimensions": {}}
        elif self.context is not None and tag in ("xbrli:startdate", "xbrli:enddate", "xbrli:instant", "xbrldi:explicitmember"):
            self.capture = (tag, attrs.get("dimension", ""), [])
        elif tag == "xbrli:unit":
            self.unit = {"id": attrs.get("id", ""), "measures": []}
        elif self.unit is not None and tag == "xbrli:measure":
            self.capture = (tag, "", [])
        elif tag == "ix:nonfraction" and asset_concept(attrs.get("name", "")):
            self.number = {"attrs": attrs, "text": []}
        hidden = tag in ("script", "style", "ix:hidden", "ix:header") or "display:none" in attrs.get("style", "").replace(" ", "").lower()
        if hidden:
            self.hidden += 1
            self.stack.append(tag)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in ("p", "div", "tr", "br", "li") and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.capture and tag == self.capture[0]:
            capture_tag, dimension, parts = self.capture
            value = "".join(parts).strip()
            if capture_tag == "xbrldi:explicitmember" and self.context is not None:
                self.context["dimensions"][dimension] = value
            elif capture_tag == "xbrli:measure" and self.unit is not None:
                self.unit["measures"].append(value)
            elif self.context is not None:
                self.context[capture_tag.split(":")[1]] = value
            self.capture = None
        if tag == "xbrli:context" and self.context is not None:
            self.contexts[self.context["id"]] = self.context
            self.context = None
        elif tag == "xbrli:unit" and self.unit is not None:
            self.units[self.unit["id"]] = ";".join(self.unit["measures"])
            self.unit = None
        elif tag == "ix:nonfraction" and self.number is not None:
            self.inline.append(self.number)
            self.number = None
        if self.stack and tag == self.stack[-1]:
            self.stack.pop()
            self.hidden -= 1

    def handle_data(self, data):
        if self.capture:
            self.capture[2].append(data)
        if self.number is not None:
            self.number["text"].append(data)
        if not self.hidden:
            self.parts.append(data)

    def text(self):
        return " ".join(" ".join(self.parts).split())

    def tagged_facts(self):
        for number in self.inline:
            attrs = number["attrs"]
            context = self.contexts.get(attrs.get("contextref", ""), {})
            raw = "".join(number["text"]).strip()
            cleaned = raw.replace(",", "").replace(" ", "").replace("\u00a0", "")
            value, status = "", "unsupported_numeric_format"
            # Only validated dot-decimal transformations; do not guess comma-decimal numbers.
            fmt = attrs.get("format", "").lower().replace("-", "")
            if (not fmt or "numdotdecimal" in fmt) and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
                value = float(cleaned) * 10 ** int(attrs.get("scale", "0"))
                if attrs.get("sign") == "-":
                    value = -abs(value)
                status = "parsed_reported_inline_xbrl"
            yield {"tag": attrs.get("name", ""), "value": value, "raw_value": raw,
                   "unit": self.units.get(attrs.get("unitref", ""), attrs.get("unitref", "")),
                   "period_start": context.get("startdate", ""),
                   "period_end": context.get("enddate", context.get("instant", "")),
                   "dimensions": json.dumps(context.get("dimensions", {}), sort_keys=True),
                   "context_id": attrs.get("contextref", ""), "numeric_status": status,
                   "interpretation_status": "reported_tagged_fact_category_and_dimensions_require_review"}


def asset_concept(tag):
    # Issuer prefixes are names, not concept semantics (e.g. cloud:StockIssued...).
    return bool(re.search(r"Land|Building|Equipment|Hardware|Hosting|Cloud|Software", tag.split(":")[-1]))


AI = re.compile(r"\b(?:artificial intelligence|generative AI|GenAI|ChatGPT|Copilot|large language models?|LLMs?|Claude|OpenAI|Anthropic)\b", re.I)
EMPLOYEE = re.compile(r"\b(?:our employees|our workforce|our developers|our engineers|internal (?:use|operations|tools|productivity)|employee productivity)\b", re.I)
DEPLOY = re.compile(r"\b(?:deploy\w*|roll\w* out|adopt\w*|implement\w*|purchas\w*|licens\w*|pilot\w*|using|use|access|enable\w*)\b", re.I)
PARTNER = re.compile(r"\b(?:partner\w*|agreement|contract|collaborat\w*)\b", re.I)
RISK = re.compile(r"\b(?:risk|may adversely|could adversely|unauthorized|prohibit\w*|do not permit|not allowed)\b", re.I)
CLOUD = re.compile(r"\b(?:cloud hosting|cloud infrastructure|hosting costs|hosting expenses|cloud service|Amazon Web Services|Microsoft Azure|Google Cloud)\b", re.I)
SPEND = re.compile(r"\b(?:costs?|expenses?|spend\w*|payments?|purchas\w*|commitments?|obligations?|agreements?|contracts?)\b", re.I)
HARDWARE = re.compile(r"\b(?:computer equipment|server hardware|hardware purchases|data center equipment|land purchases|purchase of land)\b", re.I)
NUMBER = re.compile(r"(?:\$\s*[\d,.]+(?:\s*(?:million|billion|thousand))?|\b[\d,]+\s+(?:employees|seats|users)\b)", re.I)
VENDORS = re.compile(r"\b(?:OpenAI|Anthropic|Microsoft|Google|Amazon|AWS|Azure|NVIDIA|Mistral|IBM)\b", re.I)
INLINE_BLOCK = re.compile(r'<ix:nonfraction\b[^>]*\bname\s*=\s*[\"\'][^\"\']*(?:land|building|equipment|hardware|hosting|cloud|software)[^\"\']*[\"\'][^>]*>.*?</ix:nonfraction\s*>', re.I | re.S)
RESOURCE_BLOCK = re.compile(r'<(xbrli:context|xbrli:unit)\b[^>]*>.*?</\1\s*>', re.I | re.S)
HIDDEN_BLOCK = re.compile(r'<(ix:header|ix:hidden|script|style)\b[^>]*>.*?</\1\s*>', re.I | re.S)
HTML_TAG = re.compile(r'<[^>]+>')


def parse_relevant_filing(raw):
    """Parse only matching inline facts/resources; strip the rest in linear scans."""
    parser = FilingText()
    for match in INLINE_BLOCK.finditer(raw):
        parser.feed(match.group())
    contexts = {f["attrs"].get("contextref", "") for f in parser.inline}
    units = {f["attrs"].get("unitref", "") for f in parser.inline}
    if contexts or units:
        for match in RESOURCE_BLOCK.finditer(raw):
            start_tag = match.group().split(">", 1)[0]
            identifier = re.search(r'\bid\s*=\s*[\"\']([^\"\']+)[\"\']', start_tag, re.I)
            if identifier and identifier[1] in (contexts if match[1].lower() == "xbrli:context" else units):
                parser.feed(match.group())
    visible = HIDDEN_BLOCK.sub(" ", raw)
    text = " ".join(html.unescape(HTML_TAG.sub(" ", visible)).split())
    return parser, text


def evidence(text):
    """Extract bounded nearby evidence, never convert mentions into confirmed events."""
    candidates, seen = [], set()
    for pattern, category in ((AI, "ai"), (CLOUD, "cloud"), (HARDWARE, "physical_assets")):
        count = 0
        for match in pattern.finditer(text):
            snippet = text[max(0, match.start() - 220):match.end() + 350]
            if category == "ai":
                if EMPLOYEE.search(snippet) and DEPLOY.search(snippet):
                    classification = "employee_ai_policy_or_risk" if RISK.search(snippet) else "employee_ai_adoption_candidate"
                elif PARTNER.search(snippet):
                    classification = "ai_partnership_candidate_role_unresolved"
                else:
                    continue
            elif SPEND.search(snippet):
                classification = "cloud_cost_or_commitment_candidate" if category == "cloud" else "hardware_or_land_disclosure_candidate"
            else:
                continue
            key = (classification, snippet)
            if key in seen:
                continue
            seen.add(key)
            candidates.append((category, classification, snippet))
            count += 1
            if count >= 8:
                break
    return candidates


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(args):
    companies = csv_rows(args.companies)
    if len({c["cik"] for c in companies}) != len(companies):
        raise ValueError("Company CIKs must be unique")
    args.output.mkdir(parents=True, exist_ok=True)
    client = SecClient()
    quarterly, provenance, coverage, errors, sources = [], [], [], [], []
    fact_path = args.output / "reported_financial_facts.csv"
    with fact_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["fact_id"] + FACT_FIELDS)
        writer.writeheader()
        for i, company in enumerate(companies, 1):
            print(f"Financial API data {i}/{len(companies)}: {company['ticker']}", flush=True)
            path = args.sec / company["ticker"] / "companyfacts.json"
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company['cik'].zfill(10)}.json"
            facts = defaultdict(list)
            company_quarters = []
            status = "available"
            try:
                if not path.exists():
                    if args.offline:
                        raise FileNotFoundError("No cached companyfacts")
                    data = client.json(url)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data), encoding="utf-8")
                else:
                    data = json.loads(path.read_text(encoding="utf-8"))
                if int(data["cik"]) != int(company["cik"]):
                    raise ValueError("API response CIK differs from input company")
                facts = collect_facts(company, data, args.end)
                company_quarters, refs = build_quarters(company, facts, args.start, args.end)
                quarterly.extend(company_quarters)
                provenance.extend(refs)
                needed = {id for row in refs for id in row["source_fact_ids"].split(";")}
                for metric, records in facts.items():
                    for f in records:
                        if f["end"] < args.start and f["id"] not in needed:
                            continue
                        writer.writerow({"fact_id": f["id"], **{k: company[k] for k in ID}, "metric": metric,
                                         "taxonomy": "us-gaap", "tag": f["tag"], "unit": "USD",
                                         "period_start": f.get("start", ""), "period_end": f["end"], "value": f["val"],
                                         "filed_date": f["filed"], "available_date_conservative": next_day(f["filed"]),
                                         "form": f["form"], "accession": f["accn"], "source_url": source_url(company["cik"], f["accn"]),
                                         "pre_2022_context": f["end"] < args.start})
                sources.append({"cik": company["cik"], "url": url, "cache_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            except Exception as exc:
                status = "fetch_or_parse_failed"
                errors.append({"cik": company["cik"], "ticker": company["ticker"], "stage": "companyfacts", "error": type(exc).__name__, "http_status": getattr(exc, "code", "")})
            for metric in METRICS:
                key = f"q_{metric}" if metric in FLOWS else metric
                selected = [f for f in facts[metric] if args.start <= f["end"] <= args.end]
                coverage.append({**{k: company[k] for k in ID}, "metric": metric,
                                 "status": status if status != "available" else "reported_facts_found" if selected else "not_reported_under_selected_tags",
                                 "reported_fact_count": len(selected), "quarters_with_metric": sum(r.get(key, "") != "" for r in company_quarters),
                                 "first_period_end": min((f["end"] for f in selected), default=""),
                                 "last_period_end": max((f["end"] for f in selected), default="")})
    write_csv(args.output / "fundamentals_quarterly.csv", QUARTER_FIELDS, quarterly)
    write_csv(args.output / "quarterly_metric_sources.csv", PROVENANCE_FIELDS, provenance)
    write_csv(args.output / "financial_coverage.csv", ID + ["metric", "status", "reported_fact_count", "quarters_with_metric", "first_period_end", "last_period_end"], coverage)
    index_path = args.sec / "filings_index.csv"
    filings = csv_rows(index_path) if index_path.exists() else []
    by_cik = {int(c["cik"]): c for c in companies}
    scanned, missing, evidence_counts, exhibits_scanned = Counter(), Counter(), Counter(), Counter()
    events, seen, inline_facts, inline_seen = [], set(), [], set()
    eligible = sorted((f for f in filings if int(f["cik"]) in by_cik and f["form"] in FORMS and args.start <= f["filing_date"] <= args.end), key=lambda f: (f["filing_date"], f["accession"]))
    for i, filing in enumerate(eligible, 1):
        if i == 1 or i % 250 == 0:
            print(f"Filing evidence {i}/{len(eligible)}", flush=True)
        company = by_cik[int(filing["cik"])]
        path = (ROOT / filing["local_path"]).resolve()
        if not path.is_relative_to(args.sec.resolve()) or not path.exists():
            missing[company["cik"]] += 1
            continue
        parser = FilingText()
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            # Most routine 8-Ks have no relevant text or inline asset facts.
            if not (AI.search(raw) or CLOUD.search(raw) or HARDWARE.search(raw)
                    or re.search(r"name=[\"'][^\"']*(?:Land|Building|Equipment|Hardware|Hosting|Cloud|Software)[^\"']*[\"']", raw, re.I)):
                scanned[company["cik"]] += 1
                continue
            parser, text = parse_relevant_filing(raw)
        except Exception as exc:
            errors.append({"cik": company["cik"], "ticker": company["ticker"], "stage": "filing_text", "error": type(exc).__name__, "http_status": ""})
            missing[company["cik"]] += 1
            continue
        scanned[company["cik"]] += 1
        if filing.get("document_role") == "linked_exhibit":
            exhibits_scanned[company["cik"]] += 1
        url = f"https://www.sec.gov/Archives/edgar/data/{int(company['cik'])}/{filing['accession'].replace('-', '')}/{filing['primary_document']}"
        for tagged in parser.tagged_facts():
            if not tagged["period_end"] or not args.start <= tagged["period_end"] <= args.end:
                continue
            key = (company["cik"], filing["accession"], tagged["tag"], tagged["context_id"], str(tagged["value"]), tagged["raw_value"])
            if key in inline_seen:
                continue
            inline_seen.add(key)
            inline_facts.append({**{k: company[k] for k in ID}, **tagged, "form": filing["form"],
                                 "accession": filing["accession"], "filed_date": filing["filing_date"],
                                 "available_date_conservative": next_day(filing["filing_date"]), "source_url": url})
        for category, classification, snippet in evidence(text):
            normalized = re.sub(r"\s+", " ", snippet).strip().lower()
            eid = hashlib.sha256((company["cik"] + classification + normalized).encode()).hexdigest()[:24]
            if eid in seen:
                continue
            seen.add(eid)
            url = f"https://www.sec.gov/Archives/edgar/data/{int(company['cik'])}/{filing['accession'].replace('-', '')}/{filing['primary_document']}"
            events.append({**{k: company[k] for k in ID}, "evidence_id": eid, "category": category,
                           "classification": classification, "review_status": "unreviewed_text_candidate",
                           "form": filing["form"], "accession": filing["accession"], "filed_date": filing["filing_date"],
                           "available_date_conservative": next_day(filing["filing_date"]), "source_url": url,
                           "local_path": filing["local_path"], "excerpt": snippet,
                           "vendors_mentioned": ";".join(sorted(set(m.group(0) for m in VENDORS.finditer(snippet)))),
                           "numeric_mentions_unvalidated": ";".join(NUMBER.findall(snippet)),
                           "amount_usd": "", "employee_seats": "", "first_seen_in_scanned_filings": True})
            evidence_counts[(company["cik"], category)] += 1
    write_csv(args.output / "disclosure_evidence.csv", EVIDENCE_FIELDS, events)
    write_csv(args.output / "filing_tagged_asset_and_cloud_facts.csv", INLINE_FIELDS, inline_facts)
    write_csv(args.output / "disclosure_coverage.csv", ID + ["filings_scanned", "linked_exhibits_scanned", "filings_missing", "ai_candidates", "cloud_candidates", "physical_asset_candidates", "status", "scope"],
              [{**{k: c[k] for k in ID}, "filings_scanned": scanned[c["cik"]], "filings_missing": missing[c["cik"]],
                "linked_exhibits_scanned": exhibits_scanned[c["cik"]],
                "ai_candidates": evidence_counts[(c["cik"], "ai")], "cloud_candidates": evidence_counts[(c["cik"], "cloud")],
                "physical_asset_candidates": evidence_counts[(c["cik"], "physical_assets")],
                "status": "incomplete_scan" if missing[c["cik"]] else "scanned_no_candidate_is_not_no_adoption" if scanned[c["cik"]] else "no_filings_indexed",
                "scope": "indexed_SEC_documents_only_non_SEC_announcements_and_unindexed_exhibits_not_included"} for c in companies])
    write_csv(args.output / "unresolved.csv", ["cik", "ticker", "stage", "error", "http_status"], errors)
    manifest = {"run_at": dt.datetime.now(dt.timezone.utc).isoformat(), "start": args.start, "end": args.end,
                "company_count": len(companies), "quarterly_rows": len(quarterly), "evidence_candidates": len(events),
                "filings_scanned": sum(scanned.values()), "filings_missing": sum(missing.values()), "inline_tagged_facts": len(inline_facts),
                "errors": errors, "companyfacts_sources": sources,
                "keys_required": ["SEC_USER_AGENT (contact header, not API key)"],
                "limitations": ["current company universe is not historical membership", "cross-filing YTD derivations are flagged and not verified for restatements", "filing dates use next calendar day conservatively; no intraday trading timestamps", "narrative candidates require review; amounts and seats are not inferred", "public disclosures are not comprehensive cloud bills or AI deployment data", "USD us-gaap tags only; IFRS and non-USD facts not harmonized", "EPSS history is a separate dated extractor"]}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Done: {len(quarterly)} quarterly rows, {len(events)} disclosure candidates, {len(errors)} errors -> {args.output}", flush=True)
    return int(bool(errors or sum(missing.values())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=Path, default=HERE / "packaged_software_companies.csv")
    parser.add_argument("--sec", type=Path, default=ROOT / "data/packaged_software/extracts/sec")
    parser.add_argument("--output", type=Path, default=ROOT / "data/packaged_software/extracts/company_metrics")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    parser.add_argument("--offline", action="store_true", help="Use only previously downloaded genuine SEC data")
    parser.add_argument("--check-api", action="store_true", help="Verify your SEC contact header against the public Company Facts API, then exit")
    args = parser.parse_args()
    if args.check_api:
        company = csv_rows(args.companies)[0]
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company['cik'].zfill(10)}.json"
        data = SecClient().json(url)
        if int(data.get("cik", 0)) != int(company["cik"]) or not data.get("facts"):
            raise ValueError("Unexpected live SEC API response")
        print(f"Live SEC API verified: CIK {company['cik']}, {len(data['facts'].get('us-gaap', {}))} us-gaap concepts. No API key required.")
        return 0
    if dt.date.fromisoformat(args.end) < dt.date.fromisoformat(args.start):
        parser.error("End must not precede start")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
