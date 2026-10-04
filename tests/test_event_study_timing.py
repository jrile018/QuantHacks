import importlib.util
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parents[1]/'data/packaged_software'
sys.path.insert(0,str(HERE))
SPEC=importlib.util.spec_from_file_location('event_study',HERE/'event_study.py')
es=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(es)

DAYS=[f'2024-01-0{i}' for i in range(2,9)]


class EventStudyChecks(unittest.TestCase):
    def test_ex_dividend_day_uses_price_plus_dividend(self):
        # Price falls 100 -> 99 on the ex date, but a 1.00 dividend goes ex that day: flat total return.
        r=es.daily_returns([('2024-01-02',100.0),('2024-01-03',99.0),('2024-01-04',99.0)],{'2024-01-03':1.0})
        self.assertAlmostEqual(r['2024-01-03'],0.0)
        self.assertAlmostEqual(r['2024-01-04'],0.0)

    def test_event_session_move_is_not_in_the_reaction_window(self):
        # A move on the filing date itself (an after-close filing could not cause it) is excluded.
        stock={d:0.0 for d in DAYS};stock['2024-01-03']=0.10
        market={d:0.0 for d in DAYS}
        self.assertAlmostEqual(es.car(stock,market,DAYS,'2024-01-03',1,2),0.0)
        stock['2024-01-04']=0.02
        self.assertAlmostEqual(es.car(stock,market,DAYS,'2024-01-03',1,2),0.02)

    def test_windows_start_the_day_after_the_event(self):
        self.assertTrue(all(lo==1 for lo,_ in es.WINDOWS.values()))


if __name__=='__main__':unittest.main()
