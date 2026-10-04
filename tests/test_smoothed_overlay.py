import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parents[1]/'data/packaged_software'
sys.path.insert(0,str(BASE))
from smoothed_momentum_signals import causal_savgol,momentum_signals
spec=importlib.util.spec_from_file_location('smoothed_overlay',BASE/'backtest_smoothed_overlay.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


class SmoothedOverlayTests(unittest.TestCase):
    def test_future_data_never_changes_endpoint_history(self):
        series=pd.Series(np.arange(1.,321.)**1.1)
        original=causal_savgol(series)
        changed=series.copy();changed.iloc[290:]*=100
        np.testing.assert_allclose(original.iloc[:290],causal_savgol(changed).iloc[:290],equal_nan=True)
        self.assertTrue(original.iloc[:20].isna().all())

    def test_exact_sign_agreement_and_full_history(self):
        values=pd.Series(np.arange(300.,dtype=float))
        values.iloc[-1]=200 # 21/63-day negative, 168/252-day positive: neutral.
        result=momentum_signals(values)
        self.assertTrue(result.momentum_score.iloc[:252].isna().all())
        self.assertEqual(result.momentum_score.iloc[-1],0)
        values.iloc[-1]=260 # Three positives, one negative: mean .5 times .5.
        self.assertEqual(momentum_signals(values).momentum_score.iloc[-1],.25)

    def test_ties_neutral_and_sparse_ranks_missing(self):
        self.assertTrue(b.rank_signal(pd.Series([1]*6)).eq(0).all())
        self.assertTrue(b.rank_signal(pd.Series([1,2,3,4])).isna().all())

    def test_weights_obey_caps_and_use_covariance(self):
        rng=np.random.default_rng(12)
        returns=pd.DataFrame(rng.normal(0,.005,(20,20)))
        weights,predicted=b.risk_weights(pd.Series(1.,index=returns.columns),returns)
        self.assertLessEqual(weights.sum(),2.5+1e-12)
        self.assertLessEqual(weights.max(),.1+1e-12)
        self.assertLessEqual(predicted,.1+1e-12)

    def fixture(self):
        dates=pd.bdate_range('2025-01-01',periods=5)
        close=pd.DataFrame({'A':[10.,10.,11.,12.,12.]},index=dates)
        opens=close.copy()
        ids=pd.DataFrame('provider_issuer_and_share_identity_match',index=dates,columns=['A'])
        div=close*0;div.iloc[1,0]=1.;div.iloc[2,0]=.5
        rf=pd.Series(0.,index=dates)
        targets=close*0+1.
        return close,opens,ids,div,rf,dates,targets

    def test_share_cash_accounting_dividends_and_terminal_cost(self):
        close,opens,ids,div,rf,dates,targets=self.fixture()
        daily,trades,holdings,warning=b.simulate(close,opens,ids,div,rf,dates[1:],targets,10)
        self.assertIsNone(warning)
        self.assertEqual(daily.dividend_pnl.iloc[0],0.) # Ex-date entry has no entitlement.
        self.assertGreater(daily.dividend_pnl.iloc[1],0.)
        self.assertAlmostEqual(trades.execution_cost.sum(),daily.execution_cost.sum())
        self.assertAlmostEqual(np.prod(1+daily.net_return),daily.nav.iloc[-1])
        self.assertAlmostEqual(daily.cash.iloc[-1],daily.nav.iloc[-1])
        self.assertTrue((trades.iloc[:-1].date>trades.iloc[:-1].signal_date).all())

    def test_missing_held_bar_stops_without_imputing_exit(self):
        close,opens,ids,div,rf,dates,targets=self.fixture()
        close.iloc[2,0]=np.nan
        daily,_,_,warning=b.simulate(close,opens,ids,div,rf,dates[1:],targets,10)
        self.assertEqual(len(daily),1)
        self.assertEqual(warning['status'],'unresolved_held_price_or_identity')


if __name__=='__main__': unittest.main()
