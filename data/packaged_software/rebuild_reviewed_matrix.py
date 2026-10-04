"""Rebuild a diagnostic matrix from reviewed producer inputs; no trading qualification.

No network requests and no changes to the shared SQLite database. Original final
matrix and documentation are archived before replacement. All dates are daily
historical replay assumptions, not actual receipt times or the central 15:30 clock.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
FINAL = ROOT / "final"
FINANCIAL = ROOT / "extracts/financial_quality"
INFRA = ROOT / "extracts/infrastructure_evidence"
VERSION = "reviewed-diagnostic-v2-financial-density"
FINANCIAL_MAX_AGE_DAYS = 400
RAW_METRICS = {
    "revenue", "rd_expense", "software_rd_expense_excluding_acquired_in_process",
    "sales_marketing", "stock_comp", "operating_income", "operating_cash_flow",
    "physical_asset_purchases", "acquisitions", "general_and_administrative",
    "software_development_cash_payments",
}
INSTANTS = {
    "total_assets", "goodwill", "deferred_revenue_current", "rpo", "ppe_net",
    "land_balance", "machinery_equipment_gross", "purchase_obligations",
    "purchase_obligations_next_12_months", "long_term_debt_current",
    "long_term_debt_noncurrent",
}
RATIOS = {
    "rd_pct_rev", "software_rd_pct_rev", "sm_pct_rev", "sbc_pct_rev",
    "physical_capex_pct_rev", "gross_margin", "fcf_physical_capex_margin",
    "goodwill_to_assets", "purchase_obligations_pct_ttm_rev", "rev_growth_yoy_q",
}


def read(path):
    return pd.read_csv(path, dtype={"cik": str}, keep_default_na=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tie_ranks(values):
    """Equal values receive equal average ranks. Constant groups carry no signal."""
    v = pd.to_numeric(values, errors="coerce")
    result = pd.Series(np.nan, index=v.index)
    n = v.notna().sum()
    if n >= 5:
        result.loc[v.notna()] = 2 * (v.dropna().rank(method="average") - 1) / (n - 1) - 1
    return result


def return_label(prices, factors, quarter_end, horizon=63):
    """Next market-session close to exactly horizon sessions later; paired dates.

    Factor dates are a proxy market-session calendar, not an exchange-calendar
    certification. Require all intervening stock bars and strict provider identity.
    """
    calendar = sorted(factors)
    i = bisect.bisect_right(calendar, quarter_end)
    if i + horizon >= len(calendar):
        return {"status": "outcome_not_mature_or_factor_calendar_unavailable"}
    window = calendar[i:i + horizon + 1]
    if any(d not in prices for d in window):
        return {"status": "missing_price_in_matched_session_window"}
    if any(prices[d][1] != "provider_issuer_and_share_identity_match" for d in window):
        return {"status": "dated_price_identity_requires_review"}
    if any(not np.isfinite(prices[d][0]) or prices[d][0] <= 0 for d in window):
        return {"status": "invalid_close"}
    benchmark = np.prod([1 + factors[d] for d in window[1:]]) - 1
    stock = prices[window[-1]][0] / prices[window[0]][0] - 1
    return {"status": "diagnostic_price_return_not_executable_or_total_return_certified",
            "entry_date": window[0], "exit_date": window[-1],
            "stock_price_return": stock, "market_return": benchmark,
            "excess_return": stock - benchmark}


def duration_bucket(start, end):
    days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
    if 80 <= days <= 100:
        return "quarter"
    if 170 <= days <= 200:
        return "six_month"
    if 260 <= days <= 290:
        return "nine_month"
    if 350 <= days <= 380:
        return "annual"
    return "other_duration"


def choose(candidates, cutoff, disclosure_only=False):
    available = [o for o in candidates if o["available_date"] <= cutoff]
    if disclosure_only:
        month = (int(cutoff[5:7]) - 1) // 3 * 3 + 1
        quarter_start = cutoff[:4] + f"-{month:02d}-01"
        available = [o for o in available if o["available_date"] >= quarter_start]
    else:
        oldest = (date.fromisoformat(cutoff) - timedelta(days=FINANCIAL_MAX_AGE_DAYS)).isoformat()
        available = [o for o in available if oldest <= o["period_end"] <= cutoff]
    if not available:
        return None, "no_eligible_disclosure_in_quarter" if disclosure_only else "no_reviewed_asof_value_within_400_days"
    # Select newest economic period, then newest available version of that period.
    latest = max((o["period_end"], o["available_date"]) for o in available)
    matches = [o for o in available if (o["period_end"], o["available_date"]) == latest]
    if len({o["value"] for o in matches}) > 1:
        return None, "conflicting_values_same_period_and_availability"
    return sorted(matches, key=lambda o: o["evidence_ref"])[0], ""


def main():
    inputs = [FINAL / "dataset.sqlite", FINAL / "companies_universe.csv",
              FINANCIAL / "metric_validation.csv", FINANCIAL / "ratio_dependency_validation.csv",
              FINANCIAL / "audit.json", ROOT / "extracts/company_coverage/daily_bars_reviewed.csv",
              ROOT / "output/factor_returns_daily.csv",
              INFRA / "reviewed_cloud_contract_observations.csv",
              INFRA / "infrastructure_observations_with_scope_review.csv",
              INFRA / "reported_cloud_agreement_spending_first_filed.csv"]
    density = ROOT / "extracts/financial_density"
    if (density / "recovered_observations.csv").exists():
        inputs += [density / "recovered_observations.csv", density / "audit.json"]
    if (INFRA / "additional_reviewed_cloud_observations.csv").exists():
        inputs += [INFRA / "additional_reviewed_cloud_observations.csv", INFRA / "additional_cloud_review_audit.json"]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
    universe = read(FINAL / "companies_universe.csv")
    observations = []
    definitions = {}

    def add(cik, feature, value, available, end, source, evidence, status, start="", scope="", url="", source_hash="", disclosure=False, unit="USD"):
        if not available or not end:
            raise ValueError(f"Missing clock or economic date: {feature}")
        pd.Timestamp(available)
        pd.Timestamp(end)
        observations.append(dict(cik=str(cik).zfill(10), feature=feature, value=float(value),
                                 available_date=available, period_start=start, period_end=end,
                                 source_file=source, evidence_ref=evidence, quality_status=status,
                                 scope=scope, source_url=url, source_sha256=source_hash))
        definitions[feature] = dict(disclosure_only=disclosure, unit=unit, source=source)

    f = read(FINANCIAL / "metric_validation.csv")
    for r in f.to_dict("records"):
        if str(r["eligible_for_conservative_layer"]).lower() != "true":
            continue
        basis, metric = r["basis"], r["metric"]
        if basis in ("quarter", "ttm") and metric in RAW_METRICS:
            feature = ("q_" if basis == "quarter" else "ttm_") + metric
        elif basis == "ratio" and metric == "rev_growth_yoy_q":
            feature = metric
        elif basis == "instant" and metric in INSTANTS:
            feature = metric
        else:
            continue
        add(r["cik"], feature, r["value"], r["available_date_conservative"], r["period_end"],
            "extracts/financial_quality/metric_validation.csv", r["source_fact_ids"],
            r["review_reason"], r["validated_period_start"], unit="fraction" if basis == "ratio" else "USD")
    ratios = read(FINANCIAL / "ratio_dependency_validation.csv")
    for r in ratios.to_dict("records"):
        if str(r["eligible_for_conservative_layer"]).lower() == "true" and r["metric"] in RATIOS:
            add(r["cik"], r["metric"], r["value"], r["available_date_conservative"], r["period_end"],
                "extracts/financial_quality/ratio_dependency_validation.csv", r["dependencies"], r["status"], unit="fraction")

    if (density / "recovered_observations.csv").exists():
        recovery_audit = json.loads((density / "audit.json").read_text())
        if digest(density / "recovered_observations.csv") != recovery_audit["output_sha256"]["recovered_observations.csv"]:
            raise ValueError("Financial recovery publication hash mismatch")
        for r in read(density / "recovered_observations.csv").to_dict("records"):
            add(r["cik"], r["feature"], r["value"], r["available_date"], r["period_end"],
                r["source_file"], r["evidence_ref"], r["quality_status"], r["period_start"],
                r["scope"], r["source_url"], r["source_sha256"], unit=r["unit"])

    # Preserve legacy nonfinancial observations as explicitly unqualified diagnostics.
    con = sqlite3.connect("file:" + str(FINAL / "dataset.sqlite") + "?mode=ro", uri=True)
    panel = pd.read_sql_query("SELECT * FROM fact_panel WHERE value != ''", con)
    membership = pd.read_sql_query("SELECT cik,membership_status,exit_date FROM dim_company", con)
    con.close()
    legacy_quarter_only = []
    for r in panel.to_dict("records"):
        if r["source_file"] in {"extracts/company_metrics/fundamentals_quarterly.csv", "output/rule_of_40.csv", "output/contract_awards.csv"}:
            continue
        q = pd.Period(r["period_end"], freq="Q")
        end = q.end_time.date().isoformat()
        try:
            if len(r["as_of"]) == 6 and r["as_of"][4] == "Q":
                raise ValueError("Quarter-only clock; use conservative quarter end")
            available = pd.Timestamp(r["as_of"]).date().isoformat()
        except (ValueError, TypeError):
            available = end
            legacy_quarter_only.append((r["cik"], r["feature"], r["period_end"]))
        add(r["cik"], r["feature"], r["value"], available, end, r["source_file"],
            r["evidence_ref"] or f"legacy:{r['cik']}:{r['period_end']}:{r['feature']}",
            "legacy_source_clock_and_scan_completeness_not_independently_verified",
            disclosure=True, unit=r["unit"])

    verified_paths = {}

    def verify_source(r):
        path = Path(r["local_path"])
        if path not in verified_paths:
            verified_paths[path] = digest(path)
        if verified_paths[path] != r["source_sha256"]:
            raise ValueError(f"Changed cloud evidence source: {path}")

    for r in read(INFRA / "reviewed_cloud_contract_observations.csv").to_dict("records"):
        verify_source(r)
        # Associated-services totals retain a different definition from cloud-only.
        mixed = "associated_services" in r["measure_type"]
        feature = r["metric"] + ("_and_associated_services" if mixed else "") + "_disclosed_usd"
        add(r["cik"], feature, r["amount_usd"], r["available_date_conservative"], r["filed_date"],
            "extracts/infrastructure_evidence/reviewed_cloud_contract_observations.csv", r["record_id"],
            r["status"], scope=r["measure_type"] + ";" + r["scope_note"], url=r["source_url"],
            source_hash=r["source_sha256"], disclosure=True)
    infra = read(INFRA / "infrastructure_observations_with_scope_review.csv")
    for r in infra.to_dict("records"):
        if r["metric"] not in {"reported_hosting_and_infrastructure_expense", "reported_cloud_and_server_hosting_expense"}:
            continue
        verify_source(r)
        bucket = duration_bucket(r["period_start"], r["period_end"])
        add(r["cik"], r["metric"] + "_" + bucket + "_disclosed_usd", r["value"],
            r["available_date_conservative"], r["period_end"],
            "extracts/infrastructure_evidence/infrastructure_observations_with_scope_review.csv",
            r["observation_id"], r["semantic_status"], r["period_start"],
            scope=r["dimensions"], url=r["source_url"], source_hash=r["source_sha256"], disclosure=True)
    for r in read(INFRA / "reported_cloud_agreement_spending_first_filed.csv").to_dict("records"):
        verify_source(r)
        feature = "reported_AWS_agreement_spending_" + duration_bucket(r["period_start"], r["period_end"]) + "_disclosed_usd"
        add(r["cik"], feature, r["amount_usd"], r["available_date_conservative"], r["period_end"],
            "extracts/infrastructure_evidence/reported_cloud_agreement_spending_first_filed.csv",
            r["source_clause"], r["status"], r["period_start"], r["measure_type"],
            r["source_url"], r["source_sha256"], disclosure=True)
    if (INFRA / "additional_reviewed_cloud_observations.csv").exists():
        extra_audit = json.loads((INFRA / "additional_cloud_review_audit.json").read_text())
        if digest(INFRA / "additional_reviewed_cloud_observations.csv") != extra_audit["output_sha256"]:
            raise ValueError("Additional cloud publication hash mismatch")
        for r in read(INFRA / "additional_reviewed_cloud_observations.csv").to_dict("records"):
            verify_source(r)
            add(r["cik"], r["feature"], r["value"], r["available_date"], r["period_end"],
                r["source_file"], r["evidence_ref"], r["quality_status"], r["period_start"],
                r["scope"], r["source_url"], r["source_sha256"], disclosure=True, unit=r["unit"])

    obs = pd.DataFrame(observations).drop_duplicates()
    groups = {(c, f): g.to_dict("records") for (c, f), g in obs.groupby(["cik", "feature"])}
    # Award start dates/current totals cannot be reconstructed as historical predictors.
    for feature in ["federal_awards_count_started_exact", "federal_award_value_started_exact",
                    "federal_award_amount_started", "federal_awards_started_count"]:
        definitions[feature] = dict(disclosure_only=True, unit="unqualified", source="legacy_awards_withheld")
    definitions["rule_of_40"] = dict(disclosure_only=False, unit="percentage_points", source="derived_matching_financial_periods")

    prices = read(ROOT / "extracts/company_coverage/daily_bars_reviewed.csv")
    if prices.duplicated(["cik", "date"]).any():
        raise ValueError("Duplicate reviewed price keys")
    price_groups = {c: {r["date"]: (float(r["close"]), r["price_identity_status"]) for r in g.to_dict("records")}
                    for c, g in prices.groupby("cik")}
    factor_df = read(ROOT / "output/factor_returns_daily.csv")
    if factor_df.date.duplicated().any():
        raise ValueError("Duplicate factor dates")
    factors = {r["date"]: (float(r["mkt_rf"]) + float(r["rf"])) / 100 for r in factor_df.to_dict("records")}
    last_price = max(prices.date)
    quarters = [q for q in pd.period_range("2022Q1", pd.Timestamp(last_price).to_period("Q"), freq="Q")
                if q.end_time.date().isoformat() <= last_price]
    members = membership.set_index("cik").to_dict("index")
    rows, ledger, label_rows = [], [], []
    for company in universe.to_dict("records"):
        cik = company["cik"].zfill(10)
        for quarter in quarters:
            cutoff = quarter.end_time.date().isoformat()
            row = dict(cik=cik, ticker=company["ticker"], name=company["name"], quarter=str(quarter),
                       quarter_end=cutoff, in_evaluation_window="yes" if str(quarter) >= "2024Q1" else "warm_up",
                       **members.get(cik, {"membership_status": "no_membership_record", "exit_date": ""}),
                       survivorship_flag=1, matrix_status="diagnostic_only_dated_membership_and_execution_unqualified")
            selected = {}
            for feature, definition in sorted(definitions.items()):
                if feature == "rule_of_40":
                    continue
                if definition["source"] == "legacy_awards_withheld":
                    choice, reason = None, "historical_award_availability_and_amount_vintage_not_verified"
                else:
                    choice, reason = choose(groups.get((cik, feature), []), cutoff, definition["disclosure_only"])
                row[feature] = choice["value"] if choice else np.nan
                if choice:
                    selected[feature] = choice
                ledger.append({**(choice or {}), "cik": cik, "quarter": str(quarter),
                               "feature": feature, "decision_date": cutoff, "missing_reason": reason})
            a, b = selected.get("rev_growth_yoy_q"), selected.get("fcf_physical_capex_margin")
            if a and b and a["period_end"] == b["period_end"]:
                row["rule_of_40"] = 100 * (a["value"] + b["value"])
                ledger.append(dict(cik=cik, quarter=str(quarter), feature="rule_of_40", value=row["rule_of_40"],
                                   decision_date=cutoff, available_date=max(a["available_date"], b["available_date"]),
                                   period_end=a["period_end"], evidence_ref="rev_growth_yoy_q;fcf_physical_capex_margin",
                                   source_file="derived_matching_financial_periods", missing_reason=""))
            else:
                row["rule_of_40"] = np.nan
                ledger.append(dict(cik=cik, quarter=str(quarter), feature="rule_of_40", decision_date=cutoff,
                                   missing_reason="missing_or_different_period_growth_and_FCF"))
            label = return_label(price_groups.get(cik, {}), factors, cutoff)
            row["label_excess_return_63d"] = label.get("excess_return", np.nan)
            row["label_status"] = label["status"]
            row["label_entry_date"] = label.get("entry_date", "")
            row["label_exit_date"] = label.get("exit_date", "")
            label_rows.append(dict(cik=cik, quarter=str(quarter), **label))
            rows.append(row)
    matrix = pd.DataFrame(rows)
    derived = {}
    for feature in sorted(definitions):
        derived[feature + "__present"] = matrix[feature].notna().astype(int)
        derived[feature + "__rank"] = matrix.groupby("quarter")[feature].transform(tie_ranks)
    matrix = pd.concat([matrix, pd.DataFrame(derived)], axis=1)
    coverage = pd.DataFrame([dict(feature=f, rows_present=int(matrix[f].notna().sum()),
                                 percent_rows_present=round(100 * matrix[f].notna().mean(), 2),
                                 companies_with_values=int((matrix.groupby("cik")[f].count() > 0).sum()),
                                 **definitions[f]) for f in sorted(definitions)])
    if any(digest(ROOT / name) != value for name, value in hashes.items()):
        raise ValueError("Producer inputs changed during rebuild")
    archive = FINAL / "archive_before_reviewed_v1"
    archive.mkdir(exist_ok=True)
    old = read(FINAL / "feature_matrix_backtest.csv") if (FINAL / "feature_matrix_backtest.csv").exists() else pd.DataFrame()
    for name in ["feature_matrix_backtest.csv", "FEATURE_MATRIX_DICTIONARY.csv", "FEATURE_MATRIX_README.md", "feature_matrix_summary.txt"]:
        src = FINAL / name
        if src.exists() and not (archive / name).exists():
            shutil.copy2(src, archive / name)
    # Use archived original for reproducible before/after on repeated builds.
    old = read(archive / "feature_matrix_backtest.csv")
    coverage["old_rows_present"] = [int((old[f] != "").sum()) if f in old else 0 for f in coverage.feature]
    coverage["old_percent_rows_present"] = [round(100 * (old[f] != "").mean(), 2) if f in old else np.nan for f in coverage.feature]
    matrix.to_csv(FINAL / "feature_matrix_backtest.csv", index=False)
    pd.DataFrame(ledger).to_csv(FINAL / "feature_matrix_provenance.csv", index=False)
    pd.DataFrame(label_rows).to_csv(FINAL / "feature_matrix_label_audit.csv", index=False)
    coverage.to_csv(FINAL / "feature_matrix_coverage.csv", index=False)
    obs.to_csv(FINAL / "feature_matrix_observations.csv", index=False)
    dictionary = [{"column": c, "role": "feature" if c in definitions else "rank" if c.endswith("__rank") else "presence" if c.endswith("__present") else "label" if c.startswith("label_") else "identifier_or_diagnostic_status",
                   "description": (json.dumps(definitions[c]) if c in definitions else "Average tied quarter ranks, scaled [-1,1]; fewer than five values remain blank" if c.endswith("__rank") else "1 means populated, not validated for trading" if c.endswith("__present") else "See README and source/label ledger")}
                  for c in matrix]
    pd.DataFrame(dictionary).to_csv(FINAL / "FEATURE_MATRIX_DICTIONARY.csv", index=False)
    summary = dict(version=VERSION, rows=len(matrix), companies=matrix.cik.nunique(), quarters=len(quarters),
                   raw_features=len(definitions), populated_feature_cells=int(matrix[list(definitions)].notna().sum().sum()),
                   total_feature_cells=len(matrix) * len(definitions), labelled_rows=int(matrix.label_excess_return_63d.notna().sum()),
                   label_status_counts=matrix.label_status.value_counts().to_dict(),
                   legacy_quarter_only_clock_cells=len(legacy_quarter_only), cloud_source_files_hash_checked=len(verified_paths),
                   original_rows=len(old), original_features=len([c for c in old if c + "__present" in old]),
                   input_sha256=hashes, financial_max_age_days=FINANCIAL_MAX_AGE_DAYS,
                   command=r".\venv\Scripts\python.exe data/packaged_software/rebuild_reviewed_matrix.py")
    summary["output_sha256"] = {p.name: digest(p) for p in [FINAL / "feature_matrix_backtest.csv", FINAL / "feature_matrix_provenance.csv", FINAL / "feature_matrix_label_audit.csv", FINAL / "feature_matrix_coverage.csv", FINAL / "feature_matrix_observations.csv", FINAL / "FEATURE_MATRIX_DICTIONARY.csv"]}
    (FINAL / "feature_matrix_manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (FINAL / "feature_matrix_summary.txt").write_text(json.dumps({k: v for k, v in summary.items() if "sha256" not in k}, indent=2) + "\n", encoding="utf-8")
    (FINAL / "FEATURE_MATRIX_README.md").write_text(README, encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if "sha256" not in k}, indent=2))


README = """# Reviewed diagnostic feature matrix

Version 2 adds strict direct/same-filing financial recoveries and separately named
quarterly ratios. These ratios are not substitutions for existing TTM features.
Evidence is in `extracts/financial_density/`; raw source facts and original gates
remain intact. Later comparative disclosures retain their later availability.
The reviewed version 1 matrix/coverage/manifest are in `archive_reviewed_v1/`.

Canonical CSV: `feature_matrix_backtest.csv`. The filename is retained for compatibility;
this is diagnostic research data, not an executable backtest or accepted central capsule.
Previous files remain in `archive_before_reviewed_v1/`. `dataset.sqlite` and the other
output/root matrix copies are unchanged legacy snapshots and are NOT synchronized.

## Definitions and clocks

One row for each of the fixed 168 issuers and each ended calendar quarter since 2022.
This full grid does not establish historical listing/trading eligibility. Current
membership status is descriptive only; it cannot gate historical trades. Evaluation
scope starts 2024; 2022–2023 are warm-up. Previously inspected dates are not a holdout.

Financials use eligible observations from the conservative financial-quality layer.
For each feature choose the latest economic period available by quarter-end, then the
latest eligible availability for that period; conflicting values at that grain are
withheld. Values older than 400 days from period-end are withheld (a registered replay
assumption). Each feature has its own dates; ratios and Rule of 40 need qualified,
matching inputs. Rule of 40 uses percentage points. Source arithmetic passing is not
independent accounting certification. Asset balances remain distinct from expenditures.

Ranks use average ranks for ties within a quarter; fewer than five populated values
remain unranked. Presence flags mean populated, not historically trading-qualified.

Cloud features are disclosure-quarter observations, not forward-filled spending or
complete company contract inventories. Contract totals, annual minimums, remaining
obligations and mixed cloud/associated-services obligations remain separate. Expenses
retain source-specific segment scope. Quarter, six-month, nine-month and annual
durations remain separate; overlapping periods are never added. Appian agreement
spending does not imply cash paid. Source files are checked against reviewed hashes.
If multiple inconsistent disclosures share the selection grain, the feature stays
missing; all underlying observations remain in the observation ledger.

Government-award predictors are withheld: contract start dates and current award
amounts do not establish historical availability or historical amount vintages.
Legacy 8-K/KEV/WARN/annual observations are explicitly diagnostic; scan completeness,
original publication clocks and accounting definitions are not independently certified.
No property-activity events, unreviewed cloud tags or employee-AI cost estimates enter.

Dates are daily assumed replay availability, not historical actual receipt or processing
times. This is not a 15:30 New York adapter. End-of-day inputs cannot be used at 15:30
that same day. Consumer schema/definition acceptance remains a separate handoff.

## Outcome

Entry is the first factor-calendar session AFTER quarter-end, at that session's close.
Exit is exactly 63 factor-calendar sessions after entry. The market comparator compounds
the matching 63 daily (Mkt-RF + RF) returns. Require a stock bar at every date and the
provider issuer/share identity match status throughout. Factor dates are a proxy session
calendar, not exchange-calendar certification. Other identity statuses stay unlabelled.
If the outcome/calendar is unavailable it stays missing. See `feature_matrix_label_audit.csv`.

These are diagnostic price-return labels, not certified total shareholder returns or
executable fills. Dividend/action reconciliation, entry/exit costs, dated security
identity, borrow and portfolio accounting still require review. CIK is an issuer key,
not an instrument identifier. Equity price returns and the total-market factor return
also differ in dividend treatment; no alpha or portfolio-performance claim follows.

## Reproduction and coverage

Run `.\\venv\\Scripts\\python.exe data/packaged_software/rebuild_reviewed_matrix.py`.
`feature_matrix_manifest.json` pins input/output hashes and assumptions.
`feature_matrix_coverage.csv` compares feature population before/after; denominators
differ because the rebuilt grid preserves all issuer-quarter missing rows.
`feature_matrix_provenance.csv` retains selected evidence, availability, economic
period, scope and missing reason per feature/cell. `feature_matrix_observations.csv`
retains candidate reviewed observations rather than silently overwriting duplicates.
Cloud exact clauses/contexts and financial source-fact lineage remain in referenced
producer tables. Sparse new features can have values but no ranks.
"""


if __name__ == "__main__":
    main()
