import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

SPEC=importlib.util.spec_from_file_location('company_research',
    Path(__file__).resolve().parents[1]/'data/packaged_software/analyze_company_signals.py')
research=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


class ResearchChecks(unittest.TestCase):
    def test_rank_correlation_handles_ties_and_missing(self):
        self.assertAlmostEqual(research.spearman([1,1,2,np.nan],[4,4,8,9]),1)
        self.assertTrue(np.isnan(research.spearman([1,1,1],[1,2,3])))

    def test_multiple_testing_adjustment(self):
        actual=research.bh_adjust([.01,.04,.03,np.nan])
        np.testing.assert_allclose(actual[:3],[.03,.04,.04])
        self.assertTrue(np.isnan(actual[3]))

    def test_binary_groups_and_purged_boundary(self):
        rows=[]
        for month in pd.to_datetime(['2024-11-29','2024-12-31','2025-01-31']):
            for i in range(30):
                flag=float(i>=15)
                rows.append(dict(month=month,feature=flag,forward_cohort_excess_1m=flag*.1,
                                 forward_cohort_excess_3m=flag*.2,forward_21d_volatility=flag*.3,
                                 outcome_end_1m=month+pd.DateOffset(months=1),
                                 outcome_end_3m=month+pd.DateOffset(months=3),
                                 volatility_outcome_end=month+pd.DateOffset(months=1)))
        with tempfile.TemporaryDirectory() as tmp:
            _,d=research.signal_tests(pd.DataFrame(rows),['feature'],Path(tmp))
        one=d[d.target=='forward_cohort_excess_1m']
        self.assertEqual(one['sample'].tolist(),['train','purged','test'])
        np.testing.assert_allclose(one.high_minus_low,.1)

    def test_block_randomization_is_reproducible(self):
        data=np.linspace(-.1,.2,20)
        self.assertEqual(research.uncertainty(data),research.uncertainty(data))

    def test_sign_randomization_counts_equal_extreme_endpoints(self):
        # With six positive blocks, the all-plus/all-minus draws both tie the observed statistic.
        values=np.linspace(.11,.19,90).reshape(18,5)[:,2]
        p=research.uncertainty(values)[2]
        self.assertGreater(p,.02)
        self.assertLess(p,.05)


if __name__=='__main__':unittest.main()
