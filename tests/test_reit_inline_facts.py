import unittest

from src.reit_inline_facts import extract_inline_facts


def filing(facts, *, context=None, unit=None, extra=''):
    context = context or '''<x:context id="c"><x:entity><x:identifier scheme="http://www.sec.gov/CIK">0000123456</x:identifier></x:entity><x:period><x:startDate>2026-01-01</x:startDate><x:endDate>2026-06-30</x:endDate></x:period></x:context>'''
    unit = unit or '<x:unit id="u"><x:measure>iso:USD</x:measure></x:unit>'
    return f'''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:x="http://www.xbrl.org/2003/instance" xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:t="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12" xmlns:iso="http://www.xbrl.org/2003/iso4217" xmlns:g="http://fasb.org/us-gaap/2025" xmlns:d="http://xbrl.org/2006/xbrldi" xmlns:cust="https://example.test/taxonomy/2026" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><body>{context}{unit}{facts}{extra}</body></html>'''.encode()


def fact(value='1,234', attrs=''):
    return f'<ix:nonFraction id="f" name="g:ProceedsFromBorrowings" contextRef="c" unitRef="u" format="t:num-dot-decimal" decimals="-3" {attrs}>{value}</ix:nonFraction>'


class InlineFactsTests(unittest.TestCase):
    def test_scale_sign_precision_and_context_are_independent(self):
        result = extract_inline_facts(filing(fact(attrs='scale="3" sign="-"')))
        row = result['facts'][0]
        self.assertEqual(row['value'], '-1234000')
        self.assertEqual(row['decimals'], '-3')
        self.assertEqual(row['period_type'], 'duration')
        self.assertEqual((row['period_start'], row['period_end']), ('2026-01-01', '2026-06-30'))
        self.assertEqual(row['entity_identifier'], '0000123456')
        self.assertEqual(row['unit_measure'], '{http://www.xbrl.org/2003/iso4217}USD')
        self.assertEqual(row['concept_namespace'], 'http://fasb.org/us-gaap/2025')
        self.assertEqual(row['evidence']['element_id'], 'f')

    def test_namespace_aliases_resolve_by_uri(self):
        raw = filing(fact()).replace(b'xmlns:t=', b'xmlns:alias=').replace(b't:num-dot', b'alias:num-dot')
        self.assertEqual(extract_inline_facts(raw)['facts'][0]['value'], '1234')
        fake = raw.replace(b'http://www.xbrl.org/inlineXBRL/transformation/2020-02-12', b'https://fake.test/transforms')
        result = extract_inline_facts(fake)
        self.assertIsNone(result['facts'][0]['value'])
        self.assertIn('unsupported_numeric_transform', result['facts'][0]['quality_flags'])

    def test_unsupported_format_and_grouped_unformatted_value_are_not_guessed(self):
        raw = filing(fact()).replace(b't:num-dot-decimal', b't:unknown')
        self.assertIsNone(extract_inline_facts(raw)['facts'][0]['value'])
        no_format = filing(fact()).replace(b' format="t:num-dot-decimal"', b'')
        self.assertIsNone(extract_inline_facts(no_format)['facts'][0]['value'])
        negative = filing(fact('-1.5', 'sign="-"')).replace(b' format="t:num-dot-decimal"', b'')
        self.assertEqual(extract_inline_facts(negative)['facts'][0]['value'], '1.5')

    def test_nil_and_untyped_dash_stay_unknown(self):
        nil = filing(fact('', 'xsi:nil="true"'))
        row = extract_inline_facts(nil)['facts'][0]
        self.assertIsNone(row['value'])
        self.assertTrue(row['is_nil'])
        self.assertIsNone(extract_inline_facts(filing(fact('—')))['facts'][0]['value'])

    def test_explicit_fixed_zero_is_different_from_untyped_dash(self):
        raw = filing(fact('—')).replace(b't:num-dot-decimal', b't:fixed-zero')
        self.assertEqual(extract_inline_facts(raw)['facts'][0]['value'], '0')

    def test_instant_and_dimensions_preserved(self):
        context = '''<x:context id="c"><x:entity><x:identifier scheme="http://www.sec.gov/CIK">0000123457</x:identifier><x:segment><d:explicitMember dimension="cust:FacilityAxis">cust:RevolverMember</d:explicitMember></x:segment></x:entity><x:period><x:instant>2026-06-30</x:instant></x:period></x:context>'''
        row = extract_inline_facts(filing(fact(), context=context))['facts'][0]
        self.assertEqual(row['period_type'], 'instant')
        self.assertEqual(row['as_of_date'], '2026-06-30')
        self.assertEqual(row['dimensions'][0]['axis'], '{https://example.test/taxonomy/2026}FacilityAxis')
        self.assertEqual(row['dimensions'][0]['member'], '{https://example.test/taxonomy/2026}RevolverMember')

    def test_unresolved_context_invalid_period_and_divided_unit_are_flagged(self):
        for raw in (filing(fact()).replace(b'contextRef="c"', b'contextRef="missing"'),
                    filing(fact()).replace(b'2026-01-01', b'2027-01-01'),
                    filing(fact(), unit='<x:unit id="u"><x:divide><x:unitNumerator><x:measure>iso:USD</x:measure></x:unitNumerator><x:unitDenominator><x:measure>x:shares</x:measure></x:unitDenominator></x:divide></x:unit>')):
            with self.subTest(raw=raw):
                self.assertTrue(extract_inline_facts(raw)['facts'][0]['quality_flags'])

    def test_scoped_namespace_rebinding_is_resolved(self):
        raw = filing('<div xmlns:g="https://custom.test"><ix:nonFraction name="g:ProceedsFromBorrowings" contextRef="c" unitRef="u" decimals="0">12</ix:nonFraction></div>')
        row = extract_inline_facts(raw)['facts'][0]
        self.assertEqual(row['concept_namespace'], 'https://custom.test')

    def test_excludes_hidden_metadata_is_not_dropped_and_target_rejected(self):
        raw = filing('<ix:hidden>' + fact(attrs='target="other"') + '</ix:hidden>')
        row = extract_inline_facts(raw)['facts'][0]
        self.assertIn('unsupported_target', row['quality_flags'])
        self.assertTrue(row['hidden'])

    def test_malformed_and_entity_declarations_fail_closed(self):
        self.assertEqual(extract_inline_facts(b'<html><body>broken')['facts'], [])
        self.assertTrue(extract_inline_facts(b'<html><body>broken')['issues'])
        raw = b'<!DOCTYPE html [<!ENTITY foo "123">]>' + filing(fact())
        self.assertEqual(extract_inline_facts(raw)['facts'], [])

    def test_invalid_scale_and_nonfinite_value_are_unresolved(self):
        for raw in (filing(fact(attrs='scale="999999"')), filing(fact('NaN')),
                    filing(fact(attrs='sign="+"')), filing(fact()).replace(b'decimals="-3"', b'decimals="garbage"')):
            with self.subTest(raw=raw):
                row = extract_inline_facts(raw)['facts'][0]
                self.assertTrue(row['quality_flags'])

    def test_duplicate_context_ids_cannot_choose_first(self):
        extra = '<x:context id="c"><x:entity><x:identifier scheme="http://www.sec.gov/CIK">9</x:identifier></x:entity><x:period><x:instant>2025-01-01</x:instant></x:period></x:context>'
        row = extract_inline_facts(filing(fact(), extra=extra))['facts'][0]
        self.assertIn('ambiguous_context_id', row['quality_flags'])

    def test_missing_definition_ids_cannot_resolve_missing_references(self):
        raw = filing(fact()).replace(b' id="c"', b'').replace(b' id="u"', b'').replace(b' contextRef="c"', b'').replace(b' unitRef="u"', b'')
        row = extract_inline_facts(raw)['facts'][0]
        self.assertTrue(row['quality_flags'])
        self.assertIsNone(row.get('entity_identifier'))

    def test_deep_small_xml_has_explicit_limit_not_recursion_error(self):
        nested = '<b>' * 1100 + '1' + '</b>' * 1100
        result = extract_inline_facts(filing(fact(nested)))
        self.assertEqual(result['facts'], [])
        self.assertIn('xml_depth_limit', result['issues'])

    def test_truncated_numeric_text_cannot_become_a_valid_prefix(self):
        row = extract_inline_facts(filing(fact('1' + ' ' * 201 + '2')))['facts'][0]
        self.assertIsNone(row['value'])
        self.assertIn('numeric_text_limit', row['quality_flags'])


if __name__ == '__main__':
    unittest.main()
