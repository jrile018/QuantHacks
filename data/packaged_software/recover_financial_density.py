"""Recover direct/same-filing facts and add explicitly quarterly financial ratios.

Offline only. Original financial gates remain unchanged. Later comparatives retain
their later filing availability. No cross-filing YTD or annual/YTD bridge is promoted.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd

from extract_company_metrics import METRICS
from rebuild_reviewed_matrix import RAW_METRICS

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "extracts/financial_density"
SRC = ROOT / "extracts/company_metrics_expanded"
GATES = ROOT / "extracts/financial_quality"
RATIO_DEFINITIONS = {
    "q_rd_pct_rev": ({"rd_expense": 1}, {"revenue": 1}),
    "q_software_rd_pct_rev": ({"software_rd_expense_excluding_acquired_in_process": 1}, {"revenue": 1}),
    "q_sm_pct_rev": ({"sales_marketing": 1}, {"revenue": 1}),
    "q_sbc_pct_rev": ({"stock_comp": 1}, {"revenue": 1}),
    "q_physical_capex_pct_rev": ({"physical_asset_purchases": 1}, {"revenue": 1}),
    "q_operating_margin": ({"operating_income": 1}, {"revenue": 1}),
    "q_gross_margin": ({"gross_profit": 1}, {"revenue": 1}),
    "q_fcf_physical_capex_margin": ({"operating_cash_flow": 1, "physical_asset_purchases": -1}, {"revenue": 1}),
    "q_acquisition_payments_pct_rev": ({"acquisitions": 1}, {"revenue": 1}),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def duration(start, end):
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def unique_fact(items):
    """Conflicting same-period values stay unqualified; identical duplicates collapse."""
    return min(items, key=lambda f: f["fact_id"]) if len({float(f["value"]) for f in items}) == 1 else None


def same_filing_quarters(records):
    """Direct quarters or differences within one accession, tag, unit and YTD start."""
    groups = {}
    for f in records:
        if f["unit"] != "USD" or not f["period_start"]:
            continue
        key = (f["cik"], f["metric"], f["accession"], f["tag"], f["period_start"], f["filed_date"])
        groups.setdefault(key, {}).setdefault(f["period_end"], []).append(f)
    quarters = []
    for periods in groups.values():
        facts = [unique_fact(v) for _, v in sorted(periods.items())]
        facts = [f for f in facts if f]
        for current in facts:
            if 80 <= duration(current["period_start"], current["period_end"]) <= 100:
                quarters.append((current, float(current["value"]), current["period_start"], [current], "direct_quarter"))
                continue
            priors = [f for f in facts if 80 <= duration(f["period_end"], current["period_end"]) <= 100]
            if len(priors) == 1:
                prior = priors[0]
                start = (pd.Timestamp(prior["period_end"]) + pd.Timedelta(days=1)).date().isoformat()
                quarters.append((current, float(current["value"]) - float(prior["value"]), start, [prior, current], "same_accession_YTD_difference"))
    return quarters


def main():
    OUT.mkdir(exist_ok=True)
    input_paths = [SRC / "reported_financial_facts.csv", SRC / "fundamentals_quarterly.csv",
                   GATES / "metric_validation.csv", GATES / "audit.json"]
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in input_paths}
    facts = pd.read_csv(input_paths[0], dtype=str).fillna("")
    gates = pd.read_csv(input_paths[2], dtype=str).fillna("")
    wide = pd.read_csv(input_paths[1], dtype=str).fillna("")
    audit = json.loads(input_paths[3].read_text())
    # Independently recheck all candidate facts against the original cached response.
    validated = []
    source_hashes = {}
    for ticker, group in facts.groupby("ticker"):
        path = ROOT / "extracts/sec" / ticker / "companyfacts.json"
        source_hashes[ticker] = sha(path)
        if source_hashes[ticker] != audit["source_companyfacts_sha256"][ticker]:
            raise ValueError("Source changed since financial audit: " + ticker)
        raw = json.loads(path.read_bytes())
        if int(raw["cik"]) != int(group.cik.iloc[0]):
            raise ValueError("Cached source issuer mismatch")
        keys = set()
        for taxonomy, concepts in raw["facts"].items():
            for tag, concept in concepts.items():
                for unit, observations in concept.get("units", {}).items():
                    for f in observations:
                        keys.add((taxonomy, tag, unit, f.get("start", ""), f.get("end", ""),
                                  f.get("filed", ""), f.get("accn", ""), f.get("form", ""), float(f["val"])))
        for f in group.to_dict("records"):
            key = (f["taxonomy"], f["tag"], f["unit"], f["period_start"], f["period_end"],
                   f["filed_date"], f["accession"], f["form"], float(f["value"]))
            if key not in keys:
                raise ValueError("Fact fails source match: " + f["fact_id"])
            validated.append(f)
    eligible = set(map(tuple, gates[gates.eligible_for_conservative_layer == "True"][["cik", "metric", "period_end", "basis"]].values))
    withheld = set(map(tuple, gates[gates.eligible_for_conservative_layer == "False"][["cik", "metric", "period_end", "basis"]].values))
    allowed_periods = set(map(tuple, wide[["cik", "period_end"]].values))
    facts_lookup = {f["fact_id"]: f for f in validated}
    candidates = []
    conflicts = []

    def emit(f, feature, value, start, refs, method, basis, metric):
        if (f["cik"], f["period_end"]) not in allowed_periods:
            return
        if not "2022-01-01" <= f["period_end"] <= "2026-10-04" or f["filed_date"] > "2026-10-04":
            return
        candidates.append(dict(cik=f["cik"], ticker=f["ticker"], feature=feature, value=value,
                               period_start=start, period_end=f["period_end"],
                               available_date=f["available_date_conservative"],
                               source_file="extracts/financial_density/recovered_observations.csv",
                               evidence_ref=";".join(sorted(r["fact_id"] for r in refs)),
                               quality_status="source_checked_" + method + "_not_independent_accounting_certification",
                               scope=";".join(sorted({r["tag"] for r in refs})),
                               source_url=f["source_url"], source_sha256=source_hashes[f["ticker"]],
                               accession=f["accession"], basis=basis, metric=metric,
                               recovery_reason="withheld_key_has_later_direct_or_same_filing_alternative" if (f["cik"], metric, f["period_end"], basis) in withheld else "additional_explicit_definition_or_missing_key",
                               unit="fraction" if basis == "ratio" else "USD"))

    quarters = same_filing_quarters(validated)
    # Preferred tag only within the exact accession and period, never merge dissimilar tags.
    quarter_groups = {}
    for f, value, start, refs, method in quarters:
        key = (f["cik"], f["metric"], f["accession"], start, f["period_end"], f["filed_date"])
        quarter_groups.setdefault(key, []).append((f, value, start, refs, method))
    chosen = []
    for key, items in quarter_groups.items():
        priority = min(METRICS[item[0]["metric"]].index(item[0]["tag"]) for item in items)
        items = [item for item in items if METRICS[item[0]["metric"]].index(item[0]["tag"]) == priority]
        if len({item[1] for item in items}) != 1:
            conflicts.append(dict(key=str(key), reason="conflicting_same_filing_quarter_values"))
            continue
        chosen.append(min(items, key=lambda item: item[0]["fact_id"]))
    for f, value, start, refs, method in chosen:
        key = (f["cik"], f["metric"], f["period_end"], "quarter")
        if key not in eligible and f["metric"] in RAW_METRICS:
            emit(f, "q_" + f["metric"], value, start, refs, method, "quarter", f["metric"])
    annual_groups = {}
    for f in validated:
        if f["period_start"] and f["unit"] == "USD" and 350 <= duration(f["period_start"], f["period_end"]) <= 380:
            key = (f["cik"], f["metric"], f["accession"], f["period_start"], f["period_end"], f["filed_date"])
            annual_groups.setdefault(key, []).append(f)
    for key, items in annual_groups.items():
        priority = min(METRICS[f["metric"]].index(f["tag"]) for f in items)
        f = unique_fact([f for f in items if METRICS[f["metric"]].index(f["tag"]) == priority])
        if f and (f["cik"], f["metric"], f["period_end"], "ttm") not in eligible and f["metric"] in RAW_METRICS:
            emit(f, "ttm_" + f["metric"], float(f["value"]), f["period_start"], [f], "direct_annual_TTM", "ttm", f["metric"])

    # Ratios require same accession, filed date and EXACT interval for all inputs.
    ratio_groups = {}
    for item in chosen:
        f, _, start, _, _ = item
        key = (f["cik"], f["accession"], start, f["period_end"], f["filed_date"])
        ratio_groups.setdefault(key, {})[f["metric"]] = item
    for group in ratio_groups.values():
        if "revenue" not in group or group["revenue"][1] <= 0:
            continue
        for feature, (numerator, denominator) in RATIO_DEFINITIONS.items():
            needed = set(numerator) | set(denominator)
            if feature == "q_gross_margin" and "gross_profit" not in group:
                numerator = {"revenue": 1, "cost_of_revenue": -1}
                needed = set(numerator) | set(denominator)
            if not needed <= set(group):
                continue
            n = sum(group[m][1] * sign for m, sign in numerator.items())
            d = sum(group[m][1] * sign for m, sign in denominator.items())
            refs = {r["fact_id"]: r for m in needed for r in group[m][3]}
            rev = group["revenue"]
            emit(rev[0], feature, n / d, rev[2], list(refs.values()), "same_accession_exact_interval_quarter_ratio", "ratio", feature)

    recovered = pd.DataFrame(candidates).drop_duplicates()
    # Keep the first disclosed valid candidate per value/period/definition; later
    # changed values are separate vintage observations, never backdated.
    recovered = recovered.sort_values(["cik", "feature", "period_end", "available_date", "accession"])
    recovered = recovered.drop_duplicates(["cik", "feature", "period_start", "period_end", "value"], keep="first")
    # Recompute each output independently from referenced raw source facts.
    for r in recovered.to_dict("records"):
        refs = [facts_lookup[i] for i in r["evidence_ref"].split(";")]
        if len({f["accession"] for f in refs}) != 1 or len({f["filed_date"] for f in refs}) != 1:
            raise ValueError("Cross-filing candidate slipped into strict recovery")
        expected_date = (pd.Timestamp(max(f["filed_date"] for f in refs)) + pd.Timedelta(days=1)).date().isoformat()
        if expected_date != r["available_date"]:
            raise ValueError("Backdated recovery")
        if r["basis"] == "ttm":
            recomputed = float(refs[0]["value"])
        else:
            parts = {}
            for f, value, start, _, _ in same_filing_quarters(refs):
                if start == r["period_start"] and f["period_end"] == r["period_end"]:
                    parts.setdefault(f["metric"], set()).add(value)
            if any(len(values) != 1 for values in parts.values()):
                raise ValueError("Ambiguous arithmetic inputs")
            parts = {m: next(iter(values)) for m, values in parts.items()}
            if r["basis"] == "quarter":
                recomputed = parts[r["metric"]]
            else:
                numerator, denominator = RATIO_DEFINITIONS[r["feature"]]
                if r["feature"] == "q_gross_margin" and "gross_profit" not in parts:
                    numerator = {"revenue": 1, "cost_of_revenue": -1}
                recomputed = sum(parts[m] * sign for m, sign in numerator.items()) / sum(parts[m] * sign for m, sign in denominator.items())
        if not math.isclose(recomputed, r["value"], rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError("Recovery arithmetic failed")
    recovered.to_csv(OUT / "recovered_observations.csv", index=False)
    pd.DataFrame(conflicts, columns=["key", "reason"]).to_csv(OUT / "conflicts_withheld.csv", index=False)
    summary = recovered.groupby("feature").agg(observations=("value", "size"), companies=("cik", "nunique")).reset_index()
    summary.to_csv(OUT / "recovery_coverage.csv", index=False)
    strict = recovered[recovered.basis != "ratio"]
    audit_out = dict(source_facts_rechecked=len(validated), recovered_observations=len(recovered),
                     recovered_direct_or_same_filing_metric_keys=len(strict.drop_duplicates(["cik", "metric", "period_end", "basis"])),
                     source_companies=len(source_hashes), quarterly_ratio_observations=int((recovered.basis == "ratio").sum()),
                     conflicting_groups_withheld=len(conflicts), input_sha256=inputs,
                     source_companyfacts_sha256=source_hashes,
                     limitations="Same-filing/source checks do not independently certify accounting semantics. Cross-filing uncertainty remains withheld. New quarter ratios are not TTM replacements.")
    audit_out["output_sha256"] = {p.name: sha(p) for p in OUT.glob("*.csv")}
    (OUT / "audit.json").write_text(json.dumps(audit_out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit_out.items() if "sha256" not in k}, indent=2))


if __name__ == "__main__":
    main()
