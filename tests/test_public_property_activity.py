import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'data/packaged_software'))
from collect_public_property_activity import alias, sql_quote, target_matches, TableReader


class PropertyTests(unittest.TestCase):
    def test_legal_alias_retains_distinctive_name(self):
        self.assertEqual(alias('CrowdStrike Holdings, Inc. Class A Common Stock'),'CROWDSTRIKE HOLDINGS')
        self.assertEqual(alias('Oracle Corp'),'ORACLE')

    def test_short_ambiguous_names_not_searched(self):
        self.assertEqual(alias('PAR Inc.'),'')

    def test_party_match_requires_word_boundaries(self):
        companies=[{'ticker':'TEST','search_alias':'ORACLE'}]
        self.assertEqual(target_matches('ORACLE AMERICA INC',companies),companies)
        self.assertEqual(target_matches('ORACLEX INC',companies),[])

    def test_sql_quote_handles_apostrophes(self):
        self.assertEqual(sql_quote("O'Brien"),"'O''Brien'")

    def test_permit_table_keeps_site_date_and_registration_separate(self):
        parser=TableReader(); parser.feed('<table><tr><td>Example <b>Data Center</b></td><td>123-4</td><td>01/03/2022</td><td>NSR</td><td>Loudoun</td></tr></table>')
        self.assertEqual(parser.rows,[['Example Data Center','123-4','01/03/2022','NSR','Loudoun']])


if __name__=='__main__': unittest.main()
