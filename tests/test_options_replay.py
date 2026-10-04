import importlib.util
from pathlib import Path
import sys
import unittest
import urllib.parse
import pandas as pd

HERE=Path(__file__).resolve().parents[1]/'data/packaged_software'
sys.path.insert(0,str(HERE))
SPEC=importlib.util.spec_from_file_location('replay',HERE/'replay_mean_reversion_options.py')
r=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(r)


class OptionsChecks(unittest.TestCase):
    def test_quote_windows_follow_new_york_daylight_savings(self):
        winter,_=r.quote_window('2025-01-06');summer,_=r.quote_window('2025-07-01')
        self.assertEqual(pd.Timestamp(winter,tz='UTC').hour,14)
        self.assertEqual(pd.Timestamp(summer,tz='UTC').hour,13)

    def test_quote_selection_rejects_crossed_and_insufficient_depth(self):
        start,_=r.quote_window('2025-01-06')
        class Client:
            def page(self,url):
                return {'results':[{'bid_price':3,'ask_price':2,'ask_size':5,'sip_timestamp':start},
                    {'bid_price':2,'ask_price':2.1,'ask_size':1,'sip_timestamp':start+100},
                    {'bid_price':2,'ask_price':2.1,'ask_size':3,'sip_timestamp':start+200}]}
        q=r.quote(Client(),'O:TEST','2025-01-06','ask',quantity=2)
        self.assertEqual(q['sip_timestamp'],start+200)

    def test_contract_selection_uses_prior_raw_close_and_listing_date(self):
        requests=[]
        class Client:
            def page(self,url):
                requests.append(url)
                if '/aggs/' in url:return {'results':[{'c':100}]}
                return {'results':[{'ticker':'O:FAR','expiration_date':'2025-04-11','strike_price':104,'shares_per_contract':100},
                    {'ticker':'O:ATM','expiration_date':'2025-04-11','strike_price':100,'shares_per_contract':100},
                    {'ticker':'O:ADJUSTED','expiration_date':'2025-04-11','strike_price':100,'shares_per_contract':10}]}
        contract,error=r.select_contract(Client(),'TEST','call','2025-01-03','2025-01-06')
        self.assertEqual(contract['ticker'],'O:ATM');self.assertEqual(error,'')
        self.assertIn('adjusted=false',requests[0])
        params=urllib.parse.parse_qs(urllib.parse.urlsplit(requests[1]).query)
        self.assertEqual(params['as_of'],['2025-01-03'])
        self.assertEqual(params['strike_price.gte'],['95.0'])


if __name__=='__main__':unittest.main()
