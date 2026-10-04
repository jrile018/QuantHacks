import unittest
import numpy as np
import pandas as pd
from scripts.contextual_lattice.run_contextual_study import prepare, packet

class RunnerContracts(unittest.TestCase):
    def test_equity_clocks_retain_dst_and_do_not_use_next_label(self):
        rows=pd.DataFrame({'date':['2024-03-08','2024-03-11'],'ticker':['A','A'],'target':[.3,-.2],'label_available_at':['2024-03-11','2024-03-12'],'return_1d':[.01,.02]})
        out=prepare(rows)
        self.assertEqual(out.decision_at.iloc[0],pd.Timestamp('2024-03-08T21:00Z'))
        self.assertEqual(out.decision_at.iloc[1],pd.Timestamp('2024-03-11T20:00Z'))
        self.assertTrue((out.label_available_at>out.decision_at).all())
        changed=rows.copy();changed['target']=[999,-999]
        pd.testing.assert_series_equal(out.historical_abs_return_mean,prepare(changed).historical_abs_return_mean)

    def test_future_information_cutoff_precedes_fixed_entry(self):
        rows=pd.DataFrame({'date':['2025-01-06'],'ticker':['ES'],'target':[.1],'return_1d':[.2],'label_available_at':['2025-01-07T14:36Z'],'decision_at':['2025-01-06T14:30Z'],'feature_last_session':['2025-01-03']})
        out=prepare(rows,futures=True)
        self.assertEqual(out.feature_available_at.iloc[0],pd.Timestamp('2025-01-03T14:36Z'))
        self.assertLess(out.feature_available_at.iloc[0],out.decision_at.iloc[0])
        self.assertEqual(out.next_date.iloc[0],pd.Timestamp('2025-01-07'))

    @staticmethod
    def context_rows():
        return pd.DataFrame({'decision_at':pd.to_datetime(['2025-01-02T21:00Z']), 'return_1d':[.02],'beta':[1.1],'market_return':[.01],'volatility':[.03],'edge_turnover':[.2],'known_8k':pd.Series([False],dtype='boolean'),'price_context_available':[True],'filing_context_available':[True],'context_reason':['at_decision'],'peer_reaction_gap':[.4],'price_proxy_event':[True],'lagged_market_shock':[.01],'prior_peer_stability':[.8],'residual_peer_shock':[.3]})

    def test_context_only_is_not_contaminated_by_geometry(self):
        for hypothesis in ['catchup','reversal','movement']:
            source=self.context_rows();a,_,context,interaction,_=packet(source,hypothesis,equity=True)
            source['peer_reaction_gap']=99.;source['prior_peer_stability']=-.4;source['residual_peer_shock']=-99.;source['edge_turnover']=.9
            b,_,_,_,_=packet(source,hypothesis,equity=True)
            pd.testing.assert_frame_equal(a[context],b[context])
            self.assertFalse(a[interaction].equals(b[interaction]))

    def test_unknown_SEC_coverage_is_not_treated_as_no_filing(self):
        source=self.context_rows();source['known_8k']=pd.Series([pd.NA],dtype='boolean');source['filing_context_available']=False
        out,_,_,_,_=packet(source,'reversal',equity=True)
        self.assertFalse(out.context_qualified.iloc[0])
        self.assertTrue(np.isnan(out.filing_recent.iloc[0]))
        self.assertEqual(out.context_reason.iloc[0],'SEC_population_coverage_unknown')

    def test_future_excursion_uses_prior_residual_scale(self):
        source=self.context_rows()
        source['return_1d']=.08;source['beta']=0.
        source['own_prior_residual_scale']=.02
        out,_,_,_,_=packet(source,'reversal',equity=False)
        self.assertEqual(out.own_move_z.iloc[0],4.)
        self.assertEqual(out.own_excursion.iloc[0],1.)

if __name__=='__main__':unittest.main()
