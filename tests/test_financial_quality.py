import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data/packaged_software'))
from review_financial_quality import calculate


def fact(start,end,value,accn='a',filed='2023-02-01',tag='Revenues'):
    return {'period_start':start,'period_end':end,'value':value,'accession':accn,
            'filed_date':filed,'tag':tag,'unit':'USD','fact_id':start+end+accn}


class QualityTests(unittest.TestCase):
    def test_ytd_arithmetic_does_not_certify_cross_filing_basis(self):
        row={'method':'ytd_difference','period_end':'2022-06-30'}
        refs=[fact('2022-01-01','2022-03-31',100,'a'),fact('2022-01-01','2022-06-30',250,'b')]
        value,start,cross=calculate(row,refs)
        self.assertEqual((value,start,cross),(150,'2022-04-01',True))

    def test_same_filing_difference_remains_eligible_for_basis_check(self):
        refs=[fact('2022-01-01','2022-03-31',110),fact('2022-01-01','2022-06-30',250)]
        self.assertEqual(calculate({'method':'ytd_difference','period_end':'2022-06-30'},refs)[0:3:2],(140,False))

    def test_mixed_concepts_cannot_be_differenced(self):
        refs=[fact('2022-01-01','2022-03-31',100,tag='RevenueA'),fact('2022-01-01','2022-06-30',250,tag='RevenueB')]
        with self.assertRaises(ValueError): calculate({'method':'ytd_difference','period_end':'2022-06-30'},refs)

    def test_ttm_rejects_a_missing_quarter(self):
        refs=[fact('2022-01-01','2022-03-31',100),fact('2022-07-01','2022-09-30',100),fact('2022-10-01','2022-12-31',100)]
        with self.assertRaises(ValueError): calculate({'method':'four_consecutive_quarters','period_end':'2022-12-31'},refs)

    def test_ttm_reconciles_four_direct_quarters(self):
        refs=[fact(s,e,100) for s,e in [('2022-01-01','2022-03-31'),('2022-04-01','2022-06-30'),('2022-07-01','2022-09-30'),('2022-10-01','2022-12-31')]]
        self.assertEqual(calculate({'method':'four_consecutive_quarters','period_end':'2022-12-31'},refs),(400,'2022-01-01',False))


if __name__=='__main__': unittest.main()
