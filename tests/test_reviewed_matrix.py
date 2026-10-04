import importlib.util
from pathlib import Path

import pandas as pd
import math
import unittest

spec = importlib.util.spec_from_file_location("reviewed_matrix", Path(__file__).parents[1] / "data/packaged_software/rebuild_reviewed_matrix.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_equal_values_do_not_create_a_signal():
    ranks = module.tie_ranks(pd.Series([0, 0, 0, 0, 0]))
    assert (ranks == 0).all()
    ranks = module.tie_ranks(pd.Series([0, 0, 1, 2, 3]))
    assert ranks.iloc[0] == ranks.iloc[1]


def test_sparse_values_remain_unranked():
    assert module.tie_ranks(pd.Series([1, 2, 3, 4, None])).isna().all()


def test_label_uses_exact_horizon_and_compounds_matching_market_dates():
    dates = [d.date().isoformat() for d in pd.bdate_range("2024-01-02", periods=6)]
    prices = {d: (100 * (1.02 ** i), "provider_issuer_and_share_identity_match") for i, d in enumerate(dates)}
    factors = {d: .01 for d in dates}
    label = module.return_label(prices, factors, "2024-01-01", horizon=3)
    assert label["entry_date"] == dates[0]
    assert label["exit_date"] == dates[3]
    assert math.isclose(label["market_return"], 1.01 ** 3 - 1, abs_tol=1e-12)
    assert math.isclose(label["stock_price_return"], 1.02 ** 3 - 1, abs_tol=1e-12)
    assert math.isclose(label["excess_return"], 1.02 ** 3 - 1.01 ** 3, abs_tol=1e-12)
    del prices[dates[1]]
    assert "excess_return" not in module.return_label(prices, factors, "2024-01-01", horizon=3)


def test_ambiguous_identity_is_withheld():
    prices = {"2024-01-02": (100, "requires_review"), "2024-01-03": (101, "requires_review")}
    assert module.return_label(prices, {d: 0 for d in prices}, "2024-01-01", horizon=1)["status"] == "dated_price_identity_requires_review"


def test_asof_selection_rejects_future_and_conflicting_values():
    base = dict(period_end="2024-03-31", available_date="2024-05-01", value=1, evidence_ref="a")
    assert module.choose([base], "2024-03-31")[0] is None
    assert module.choose([base], "2024-06-30")[0] == base
    assert module.choose([base, dict(base, value=2)], "2024-06-30")[1] == "conflicting_values_same_period_and_availability"


def test_cloud_is_not_forward_filled_and_old_financials_expire():
    base = dict(period_end="2024-03-31", available_date="2024-05-01", value=1, evidence_ref="a")
    assert module.choose([base], "2024-09-30", disclosure_only=True)[0] is None
    assert module.choose([base], "2026-06-30")[0] is None


def test_duration_keeps_overlapping_spending_periods_separate():
    assert module.duration_bucket("2024-01-01", "2024-03-31") == "quarter"
    assert module.duration_bucket("2024-01-01", "2024-06-30") == "six_month"
    assert module.duration_bucket("2024-01-01", "2024-12-31") == "annual"


if __name__ == "__main__":
    suite = unittest.TestSuite(unittest.FunctionTestCase(v) for k, v in list(globals().items()) if k.startswith("test_"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
