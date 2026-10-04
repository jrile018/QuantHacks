import unittest

from src.reit_pdf_money import extract_pdf_money


CURRENCY = 'The U.S. Dollar ("USD") is our reporting currency. Unless otherwise indicated, all dollar amounts are expressed in USD.'
DOC = {'cik': '0000123456', 'reportDate': '2025-12-31', 'sha256': 'a' * 64,
       'url': 'https://example.test/report.pdf', 'source_path': 'report.pdf'}


def pages(text, currency=CURRENCY):
    return [{'number': 10, 'text': text}, {'number': 11, 'text': currency}]


def cash_table(rows, years='2025 2024 2023', scale='thousands'):
    return ('CONSOLIDATED STATEMENTS OF CASH FLOWS\n(in ' + scale + ')\n'
            'Years ended December 31,\n' + years + '\n' + rows)


class PdfMoneyTests(unittest.TestCase):
    def test_year_columns_units_signs_and_mixed_investments(self):
        text = cash_table('Proceeds from term loan 123,456 222,000 333,000\n'
                          'Principal payment on term loans (23,456) (22,000) (33,000)\n'
                          'Investment in loans and preferred equity (100) (200) (300)')
        result = extract_pdf_money(pages(text), DOC)
        self.assertEqual(len(result['records']), 9)
        current = [r for r in result['records'] if r['period_end'] == '2025-12-31']
        self.assertEqual({r['value'] for r in current}, {'123456000', '-23456000', '-100000'})
        self.assertTrue(all(r['currency'] == 'USD' and r['status'] == 'parsed' for r in current))
        loan_investment = next(r for r in current if r['metric'] == 'loan_preferred_equity_investments')
        self.assertEqual(loan_investment['relationship'], 'mixed_asset_investor')
        self.assertEqual(loan_investment['amount_kind'], 'flow')
        for row in current:
            amount = next(e for e in row['evidence'] if e['evidence_role'] == 'amount')
            self.assertEqual(text[amount['char_start']:amount['char_end']], amount['quoted_text'])
            self.assertEqual(amount['column_year'], '2025')

    def test_reordered_years_follow_header_not_latest_year_assumption(self):
        result = extract_pdf_money(pages(cash_table('Proceeds from term loan 100 200 300', '2023 2025 2024', 'millions')), DOC)
        current = next(r for r in result['records'] if r['period_end'] == '2025-12-31')
        self.assertEqual(current['value'], '200000000')

    def test_multiple_cash_tables_keep_their_own_years_and_units(self):
        text = (cash_table('Proceeds from term loan 100 200 300') + '\n' +
                cash_table('Proceeds from term loan 5 6 7', '2022 2021 2020', 'millions'))
        records = extract_pdf_money(pages(text), DOC)['records']
        self.assertEqual(len(records), 6)
        self.assertEqual({r['period_end'][:4]: r['value'] for r in records},
                         {'2025': '100000', '2024': '200000', '2023': '300000',
                          '2022': '5000000', '2021': '6000000', '2020': '7000000'})

    def test_next_financial_statement_stops_cash_table_binding(self):
        text = (cash_table('Proceeds from term loan 100 200 300') + '\n'
                'CONSOLIDATED STATEMENTS OF INCOME\n'
                'Proceeds from term loan 5 6 7')
        records = extract_pdf_money(pages(text), DOC)['records']
        self.assertEqual(len(records), 3)

    def test_missing_currency_does_not_promote_dollar_sign(self):
        result = extract_pdf_money(pages(cash_table('Proceeds from term loan $ 100 200 300'), ''), DOC)
        self.assertTrue(result['records'])
        self.assertTrue(all(r['status'] == 'review_required' for r in result['records']))
        self.assertTrue(all(r['currency'] is None for r in result['records']))

    def test_conflicting_reporting_currencies_are_withheld(self):
        result = extract_pdf_money(pages(cash_table('Proceeds from term loan 100 200 300'),
                                        CURRENCY + ' All dollar amounts are expressed in CAD.'), DOC)
        self.assertTrue(all(r['status'] == 'review_required' for r in result['records']))
        self.assertIn('reporting_currency_conflict', result['issues'])

    def test_missing_or_duplicate_headers_and_bad_column_counts_are_rejected(self):
        row = 'Proceeds from term loan 100 200 300'
        for text in (cash_table(row).replace('Years ended', 'Six months ended'),
                     cash_table(row).replace('(in thousands)', ''),
                     cash_table(row, '2025 2025 2023'), cash_table('Proceeds from term loan 100 200')):
            with self.subTest(text=text):
                self.assertEqual(extract_pdf_money(pages(text), DOC)['records'], [])

    def test_dashes_and_sign_conflicts_stay_under_review(self):
        result = extract_pdf_money(pages(cash_table('Principal payment on term loans 100 — (300)')), DOC)
        by_year = {r['period_end'][:4]: r for r in result['records']}
        self.assertEqual(by_year['2025']['status'], 'review_required')
        self.assertIn('cash_direction_sign_conflict', by_year['2025']['quality_flags'])
        self.assertIsNone(by_year['2024']['value'])
        self.assertEqual(by_year['2024']['status'], 'review_required')
        self.assertEqual(by_year['2023']['value'], '-300000')

    def test_same_values_different_rows_are_distinct(self):
        rows = 'Proceeds from term loan 100 200 300\nPrincipal payment on term loans (100) (200) (300)'
        result = extract_pdf_money(pages(cash_table(rows)), DOC)
        self.assertEqual(len({r['concept_local_name'] for r in result['records']}), 2)

    def test_facility_capacity_availability_balance_and_conditional_capacity(self):
        text = ('8. Credit Facilities\nA. RI Credit Facilities\n'
                'In April 2025, we entered into new $4.0 billion unsecured multicurrency revolving credit facilities.\n'
                'The aggregate capacity of the RI Credit Facilities can be increased to up to $5.0\n'
                'billion pursuant to an accordion expansion feature, which is subject to obtaining lender commitments.\n'
                'As of December 31, 2025, we had a borrowing capacity of $2.7 billion available on our RI Credit Facilities '
                '(subject to customary conditions to borrowing) and an outstanding balance of $1.3 billion.\n'
                'Borrowings bear SOFR plus 0.725%; collateral totals $6.0 billion.')
        result = extract_pdf_money(pages(text), DOC)
        records = result['records']
        self.assertEqual(len(records), 4)
        by_basis = {r['amount_basis']: r for r in records}
        self.assertEqual(by_basis['facility_commitment']['value'], '4000000000')
        self.assertEqual(by_basis['undrawn_available']['value'], '2700000000')
        self.assertEqual(by_basis['reported_debt_balance']['value'], '1300000000')
        self.assertEqual(by_basis['subject_to_lender_commitments']['amount_kind'], 'conditional_capacity')
        self.assertTrue(all(r['as_of_date'] == '2025-12-31' and r['status'] == 'parsed' for r in records))
        self.assertFalse(any(r['amount_kind'] == 'flow' for r in records))
        for row in records:
            amount = next(e for e in row['evidence'] if e['evidence_role'] == 'amount')
            self.assertEqual(text[amount['char_start']:amount['char_end']], amount['quoted_text'])

    def test_fund_scope_does_not_merge_with_issuer_or_sum_components(self):
        text = ('B. Fund Credit Facilities\n'
                'The Fund entered into a newly-established $1.38 billion unsecured credit facility, '
                'which provides for up to $1.0 billion unsecured revolving credit facility and $380.0 million delayed draw term loan.\n'
                'As of December 31, 2025, we had a borrowing capacity of $1.2 billion available on our Fund Credit Facilities '
                '(subject to customary conditions to borrowing) and an outstanding balance of $182.0 million under the unsecured revolving credit facility.')
        records = extract_pdf_money(pages(text), DOC)['records']
        self.assertEqual(len(records), 3)
        self.assertTrue(all(r['relationship'] == 'fund_borrower' for r in records))
        self.assertTrue(all(r['entity_identifier'] == 'Fund' for r in records))
        self.assertEqual({r['value'] for r in records}, {'1380000000', '1200000000', '182000000'})

    def test_capacity_without_current_date_or_conditions_is_not_verified(self):
        text = ('A. RI Credit Facilities\n'
                'In April 2025, we entered into new $4.0 billion unsecured revolving credit facilities.\n'
                'The aggregate capacity of the RI Credit Facilities can be increased to up to $5.0 billion.')
        records = extract_pdf_money(pages(text), DOC)['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['status'], 'review_required')
        self.assertIn('capacity_reporting_date_unresolved', records[0]['quality_flags'])

    def test_subsequent_reduction_does_not_make_original_capacity_current(self):
        text = ('A. RI Credit Facilities\n'
                'In April 2025, we entered into new $4.0 billion unsecured revolving credit facilities.\n'
                'In November 2025, our commitments were reduced to $2.0 billion.\n'
                'As of December 31, 2025, we had a borrowing capacity of $1.2 billion available on our RI Credit Facilities '
                'and an outstanding balance of $0.8 billion.')
        records = extract_pdf_money(pages(text), DOC)['records']
        commitment = next(r for r in records if r['amount_basis'] == 'facility_commitment')
        self.assertEqual(commitment['status'], 'review_required')
        self.assertIn('capacity_current_state_unresolved', commitment['quality_flags'])
        self.assertTrue(all(r['status'] == 'parsed' for r in records if r['amount_basis'] != 'facility_commitment'))

    def test_current_capacity_disagreement_is_withheld_regardless_of_change_wording(self):
        for change in ('the commitment decreased to $2.0 billion',
                       'capacity fell to $2.0 billion', 'the facility expired',
                       'the lenders renegotiated the aggregate amount to $2.0 billion'):
            with self.subTest(change=change):
                text = ('A. RI Credit Facilities\n'
                        'In April 2025, we entered into new $4.0 billion unsecured revolving credit facilities.\n'
                        'In November 2025, ' + change + '.\n'
                        'As of December 31, 2025, we had a borrowing capacity of $1.2 billion available on our RI Credit Facilities '
                        'and an outstanding balance of $0.8 billion.')
                records = extract_pdf_money(pages(text), DOC)['records']
                commitment = next(r for r in records if r['amount_basis'] == 'facility_commitment')
                self.assertEqual(commitment['status'], 'review_required')
                self.assertIn('capacity_current_state_unresolved', commitment['quality_flags'])
                self.assertTrue(all(r['status'] == 'parsed' for r in records if r['amount_basis'] != 'facility_commitment'))

    def test_multiple_or_subsidiary_commitments_do_not_inherit_parent_facility(self):
        original = ('In April 2025, we entered into new $4.0 billion unsecured revolving credit facilities.\n')
        other = 'We entered into a new $0.5 billion secured credit facility for a subsidiary.\n'
        dated = ('As of December 31, 2025, we had a borrowing capacity of $2.7 billion available on our RI Credit Facilities '
                 'and an outstanding balance of $1.3 billion.')
        for statements in (original + other, other):
            with self.subTest(statements=statements):
                records = extract_pdf_money(pages('A. RI Credit Facilities\n' + statements + dated), DOC)['records']
                commitments = [r for r in records if r['amount_basis'] == 'facility_commitment']
                self.assertTrue(commitments)
                self.assertTrue(all(r['status'] == 'review_required' for r in commitments))
                self.assertTrue(all('facility_association_unresolved' in r['quality_flags'] for r in commitments))

    def test_unrelated_numbers_and_forward_estimates_are_not_cash_flows(self):
        text = 'We expect $100 million of cash flow next year and have $300 million of collateral and a $50 million swap notional.'
        self.assertEqual(extract_pdf_money(pages(text), DOC)['records'], [])


if __name__ == '__main__':
    unittest.main()
