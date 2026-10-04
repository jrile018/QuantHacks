"""Independent structural, as-of, rank and matched-label checks of final CSVs."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
FINAL = ROOT / "final"
# Features added after the base matrix (power/CapEx) are recorded in their own ledger.
EXTENSION_LEDGER = ROOT / "extracts" / "power_capex" / "matrix_feature_provenance.csv"


def main():
    manifest = json.loads((FINAL / "feature_matrix_manifest.json").read_text())
    checks = {}
    for group, base in [("input_sha256", ROOT), ("output_sha256", FINAL)]:
        checks[group] = all(hashlib.sha256((base.joinpath(*p.replace("\\", "/").split("/"))).read_bytes()).hexdigest() == h
                            for p, h in manifest[group].items())
    m = pd.read_csv(FINAL / "feature_matrix_backtest.csv", dtype={"cik": str})
    base_p = pd.read_csv(FINAL / "feature_matrix_provenance.csv", dtype={"cik": str}, keep_default_na=False)
    ext_p = pd.read_csv(EXTENSION_LEDGER, dtype={"cik": str}, keep_default_na=False)
    p = pd.concat([base_p, ext_p], ignore_index=True)
    raw = [c for c in m if c + "__present" in m]
    checks["full_grid_unique"] = len(m) == 168 * 19 and not m.duplicated(["cik", "quarter"]).any()
    checks["ledgers_disjoint_and_cover_matrix"] = (not set(base_p.feature) & set(ext_p.feature)
                                                   and set(base_p.feature) | set(ext_p.feature) == set(raw))
    checks["presence_flags"] = all((m[f].notna().astype(int) == m[f + "__present"]).all() for f in raw)
    checks["equal_values_equal_ranks"] = all((m.groupby(["quarter", f])[f + "__rank"].nunique() <= 1).all() for f in raw)
    checks["ranks_match_independent_average_formula"] = True
    for feature in raw:
        for _, g in m.groupby("quarter"):
            v = g[feature].dropna()
            expected = 2 * (v.rank(method="average") - 1) / (len(v) - 1) - 1 if len(v) >= 5 else pd.Series(np.nan, index=v.index)
            actual = g.loc[v.index, feature + "__rank"]
            checks["ranks_match_independent_average_formula"] &= bool(np.allclose(actual, expected, equal_nan=True))
    populated = p[p.value != ""]
    checks["no_future_availability"] = bool((populated.available_date <= populated.decision_date).all())
    checks["populated_cells_have_availability_date"] = bool((populated.available_date != "").all())
    checks["one_ledger_cell_per_feature"] = len(p) == len(m) * len(raw) and not p.duplicated(["cik", "quarter", "feature"]).any()
    checks["every_blank_has_reason"] = bool((p.loc[p.value == "", "missing_reason"] != "").all())
    checks["every_matrix_value_is_ledgered"] = int(m[raw].notna().sum().sum()) == len(populated)
    matrix_indexed = m.set_index(["cik", "quarter"])
    checks["ledger_values_match_matrix"] = True
    for feature, g in populated.groupby("feature"):
        matrix_vals = pd.to_numeric(matrix_indexed[feature].reindex(pd.MultiIndex.from_frame(g[["cik", "quarter"]]))).to_numpy()
        ledger_vals = pd.to_numeric(g.value).to_numpy()
        checks["ledger_values_match_matrix"] &= bool(np.allclose(matrix_vals, ledger_vals, rtol=1e-9, atol=1e-12))
    checks["award_predictors_withheld"] = all(m[f].isna().all() for f in raw if f.startswith("federal_award"))
    cloud = populated[populated.source_file.str.contains("infrastructure_evidence", na=False)]
    checks["cloud_disclosure_quarter_only"] = bool((pd.to_datetime(cloud.available_date).dt.to_period("Q").astype(str) == cloud.quarter).all())
    labels = pd.read_csv(FINAL / "feature_matrix_label_audit.csv", dtype={"cik": str})
    factors = pd.read_csv(ROOT / "output/factor_returns_daily.csv").set_index("date")
    calendar = factors.index.tolist()
    prices = pd.read_csv(ROOT / "extracts/company_coverage/daily_bars_reviewed.csv", dtype={"cik": str}).set_index(["cik", "date"])
    checks["labels_independently_recomputed"] = True
    checks["label_sessions_and_identity"] = True
    for row in labels[labels.excess_return.notna()].itertuples():
        start, end = calendar.index(row.entry_date), calendar.index(row.exit_date)
        dates = calendar[start:end + 1]
        checks["label_sessions_and_identity"] &= end - start == 63 and row.entry_date > str(pd.Period(row.quarter).end_time.date())
        selected = prices.loc[[(row.cik, d) for d in dates]]
        checks["label_sessions_and_identity"] &= bool((selected.price_identity_status == "provider_issuer_and_share_identity_match").all())
        market = np.prod(1 + (factors.loc[dates[1:], "mkt_rf"] + factors.loc[dates[1:], "rf"]) / 100) - 1
        stock = selected.close.iloc[-1] / selected.close.iloc[0] - 1
        checks["labels_independently_recomputed"] &= bool(np.isclose(stock - market, row.excess_return, atol=1e-12, rtol=1e-12))
    old = pd.read_csv(FINAL / "archive_before_reviewed_v1/feature_matrix_backtest.csv", dtype={"cik": str})
    old_features = [c for c in old if c + "__present" in old]
    common = sorted(set(old_features) & set(raw))
    joined = m.set_index(["cik", "quarter"]).loc[pd.MultiIndex.from_frame(old[["cik", "quarter"]])]
    comparison = dict(old_rows=len(old), new_rows=len(m), old_raw_features=len(old_features), new_raw_features=len(raw),
                      old_population_percent=round(100 * old[old_features].notna().sum().sum() / old[old_features].size, 2),
                      new_population_percent=round(100 * m[raw].notna().sum().sum() / m[raw].size, 2),
                      comparable_original_rows_and_features_population_percent=round(100 * joined[common].notna().sum().sum() / joined[common].size, 2),
                      new_labelled_rows=int(m.label_excess_return_63d.notna().sum()),
                      cloud_populated_cells=len(cloud), cloud_companies=cloud.cik.nunique())
    result = dict(checks={k: bool(v) for k, v in checks.items()}, comparison=comparison,
                  limitations="Checks do not certify accounting semantics, actual historical clocks, corporate actions, historical membership or executable returns.")
    (FINAL / "feature_matrix_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not all(checks.values()):
        raise SystemExit("Reviewed matrix validation failed")


if __name__ == "__main__":
    main()
