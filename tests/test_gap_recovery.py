import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data/packaged_software'))
SPEC=importlib.util.spec_from_file_location('recovery',Path(__file__).resolve().parents[1]/'data/packaged_software/recover_dataset_gaps.py')
m=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class RecoveryTests(unittest.TestCase):
    def test_invalid_prices_excluded_without_changing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'base'
            out=Path(tmp)/'out'
            (base/'prices').mkdir(parents=True)
            out.mkdir()
            source=base/'prices/daily_bars.csv'
            pd.DataFrame([{'ticker':'A','date':'2022-01-03','open':10,'high':12,'low':9,'close':11},
                          {'ticker':'A','date':'2022-01-04','open':10,'high':12,'low':9,'close':0}]).to_csv(source,index=False)
            before=source.read_bytes()
            with patch.object(m,'BASE',base),patch.object(m,'OUT',out):
                counts=m.prepare_prices()
            self.assertEqual(counts['excluded_price_rows'],1)
            self.assertEqual(source.read_bytes(),before)
            self.assertEqual(len(pd.read_csv(out/'daily_bars_clean.csv')),1)

    def test_only_matching_common_share_identity_is_stitched(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            (out/'alias_cache').mkdir()
            pd.DataFrame([{'ticker':t,'date':'2022-01-04','open':10,'high':12,'low':9,'close':220 if t=='JUMP' else 11} for t in ['GOOD','BAD','JUMP']]).to_csv(out/'daily_bars_clean.csv',index=False)
            pd.DataFrame([{'ticker':t,'source_ticker':t+'OLD','cik':'1','date':'2022-01-03','open':10,'high':12,'low':9,'close':11} for t in ['GOOD','BAD','JUMP']]).to_csv(out/'historical_alias_price_candidates.csv',index=False)
            def reference(url,key):
                return {'results':{'cik':'0001','type':'CS','share_class_figi':'different' if '/BADOLD?' in url else 'same'}}
            with patch.object(m,'OUT',out),patch.object(m,'env_value',return_value='unused'),patch.object(m,'get_json',side_effect=reference):
                m.validate_aliases([])
            restored=pd.read_csv(out/'daily_bars_with_verified_aliases.csv')
            self.assertEqual(len(restored[restored.ticker.eq('GOOD')]),2)
            self.assertEqual(len(restored[restored.ticker.eq('BAD')]),1)
            self.assertEqual(len(restored[restored.ticker.eq('JUMP')]),1)


if __name__=='__main__':
    unittest.main()
