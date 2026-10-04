import importlib.util
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

SPEC=importlib.util.spec_from_file_location('backtest',Path(__file__).resolve().parents[1]/'data/packaged_software/backtest_mean_reversion.py')
b=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(b)


class ExecutionTests(unittest.TestCase):
    def fixture(self):
        dates=pd.bdate_range('2024-01-01',periods=90)
        spread=.015*np.sin(np.arange(90)*.7);spread[65]=-.04
        close=pd.DataFrame({'A':100*np.exp(spread),'B':np.full(90,100.),'UNTRADED':np.full(90,np.nan)},index=dates)
        opens=close.shift(1);opens.iloc[0]=close.iloc[0]
        dividend=pd.DataFrame(0.,index=dates,columns=close.columns)
        models=[{'a':'A','b':'B','intercept':0.,'beta':1.}]
        return close,opens,dividend,models

    def test_next_open_dividends_short_borrow_and_ledger_reconcile(self):
        close,opens,div,models=self.fixture()
        div.iloc[66,0]=.1 # Entry-day dividend must not belong to the new position.
        div.iloc[67,0]=.1;div.iloc[67,1]=.2
        d,t=b.simulate(close,opens,div,close.index[66:75],models,2.)
        self.assertGreater(len(t),0)
        first=t.iloc[0]
        self.assertEqual(first.entry_signal_date,close.index[65])
        self.assertEqual(first.entry_date,close.index[66])
        self.assertLess(first.entry_signal_date,first.entry_date)
        expected=.5/opens.iloc[66,0]*.1-.5/opens.iloc[66,1]*.2
        self.assertAlmostEqual(first.dividend_pnl,expected)
        self.assertGreater(first.borrow_cost,0)
        self.assertGreater(first.execution_cost,0)
        self.assertAlmostEqual(t.net_pnl.sum(),d.nav.iloc[-1]-1)
        np.testing.assert_allclose(d.price_pnl,d.long_price_pnl+d.short_price_pnl,atol=1e-12)
        self.assertTrue(np.isfinite(d.nav).all()) # Missing unused ticker must not poison cost totals.

    def test_future_prices_do_not_change_earlier_execution(self):
        close,opens,div,models=self.fixture()
        before,_=b.simulate(close,opens,div,close.index[66:85],models,2.)
        changed=close.copy();changed.iloc[78:,0]*=1.1
        new_op=opens.copy();new_op.iloc[79:,0]*=1.1
        after,_=b.simulate(changed,new_op,div,close.index[66:85],models,2.)
        np.testing.assert_allclose(before.nav.iloc[:12],after.nav.iloc[:12])

    def test_missing_price_while_holding_is_not_discarded(self):
        close,opens,div,models=self.fixture();close.iloc[66,0]=np.nan
        with self.assertRaises(ValueError):b.simulate(close,opens,div,close.index[66:75],models,2.)

    def test_no_selected_pairs_means_cash(self):
        close,opens,div,_=self.fixture()
        d,t=b.simulate(close,opens,div,close.index[66:75],[],2.)
        np.testing.assert_allclose(d.nav,1);self.assertEqual(len(t),0)


if __name__=='__main__':unittest.main()
