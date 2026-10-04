import unittest
from unittest.mock import patch

from src.reit_tables import extract_html_tables


class HtmlTableTests(unittest.TestCase):
    def test_preserves_unicode_source_spans_caption_and_visible_context(self):
        source = ('<p>Résumé: "Loan commitments" &amp; capacity.</p>\n'
                  '<script>wrong context</script><style>wrong</style>'
                  '<table><caption>Facilities &amp; debt</caption><tr>'
                  '<th>Borrower</th><td>Über <b>Fund</b><!--wrong-->'
                  '<script>wrong cell</script><br>$1,200</td></tr></table>')
        table, = extract_html_tables(source)
        self.assertEqual(table['caption'], 'Facilities & debt')
        self.assertEqual(table['context'], 'Résumé: "Loan commitments" & capacity.')
        cell = table['rows'][0]['cells'][1]
        self.assertEqual(cell['text'], 'Über Fund $1,200')
        self.assertEqual(source[cell['char_start']:cell['char_end']],
                         '<td>Über <b>Fund</b><!--wrong--><script>wrong cell</script><br>$1,200</td>')
        self.assertEqual(source[table['char_start']:table['char_end']], source[source.index('<table>'):])
        self.assertEqual(table['quality_flags'], [])

    def test_aligns_merged_headers_and_rowspans_without_guessing_values(self):
        source = ('<table><thead><tr><th rowspan="2">Facility</th><th colspan="2">Amounts</th></tr>'
                  '<tr><th>Capacity</th><th>Outstanding</th></tr></thead><tbody>'
                  '<tr><td>Repo</td><td>100</td><td>30</td></tr></tbody></table>')
        table, = extract_html_tables(source)
        cells = [cell for row in table['rows'] for cell in row['cells']]
        a, b, c, d, e, f, g = [cell['cell_id'] for cell in cells]
        self.assertEqual(table['grid'], [[a, b, b], [a, c, d], [e, f, g]])
        self.assertEqual(cells[2]['column_index'], 1)
        self.assertEqual(cells[0]['rowspan'], 2)
        self.assertNotIn('value', cells[5])
        self.assertEqual(table['quality_flags'], [])

    def test_nested_tables_are_separate_and_outer_cell_excludes_inner_content(self):
        source = '<table><tr><td>Outer<table><tr><td>Inner</td></tr></table> tail</td></tr></table>'
        outer, inner = extract_html_tables(source)
        self.assertEqual([c['text'] for c in outer['rows'][0]['cells']], ['Outer tail'])
        self.assertEqual([c['text'] for c in inner['rows'][0]['cells']], ['Inner'])
        self.assertIn('nested_table', outer['quality_flags'])
        self.assertIn('nested_table', inner['quality_flags'])
        self.assertEqual(len(outer['rows']), 1)
        self.assertEqual(source[inner['char_start']:inner['char_end']], '<table><tr><td>Inner</td></tr></table>')

    def test_collision_is_flagged_without_overwriting_prior_rowspan(self):
        table, = extract_html_tables('<table><tr><td>A</td><td rowspan="2">B</td></tr>'
                                     '<tr><td colspan="2">C</td></tr></table>')
        a, b = table['rows'][0]['cells']
        c, = table['rows'][1]['cells']
        self.assertIn('span_collision', table['quality_flags'])
        self.assertEqual(table['grid'][1], [c['cell_id'], b['cell_id']])

    def test_malformed_unclosed_cells_keep_bounded_evidence_and_flags(self):
        source = '<table><tr><td>One<td>Two</tr>'
        table, = extract_html_tables(source)
        self.assertIn('malformed_structure', table['quality_flags'])
        self.assertEqual([c['text'] for c in table['rows'][0]['cells']], ['One', 'Two'])
        first = table['rows'][0]['cells'][0]
        self.assertEqual(source[first['char_start']:first['char_end']], '<td>One')
        self.assertEqual(table['char_end'], len(source))

    def test_invalid_spans_are_flagged_and_not_used_as_huge_allocations(self):
        table, = extract_html_tables('<table><tr><td rowspan="0" colspan="invalid">A</td>'
                                     '<td colspan="99999999999999999999999">B</td></tr></table>')
        self.assertIn('invalid_span', table['quality_flags'])
        self.assertIn('span_limit', table['quality_flags'])
        self.assertIn('column_limit', table['quality_flags'])
        self.assertLessEqual(len(table['grid'][0]), 200)

    def test_table_limit_is_visible_on_retained_results(self):
        tables = extract_html_tables('<table><tr><td>x</td></tr></table>' * 501)
        self.assertEqual(len(tables), 500)
        self.assertIn('table_limit', tables[-1]['quality_flags'])

    def test_cell_and_row_limits_keep_evidence_and_incomplete_coverage_flags(self):
        table, = extract_html_tables('<table>' + '<tr><td>x</td><td>y</td></tr>' * 5001 + '</table>')
        self.assertEqual(sum(len(row['cells']) for row in table['rows']), 10000)
        self.assertIn('cell_limit', table['quality_flags'])
        self.assertTrue(all(len(row) <= 200 for row in table['grid']))

    def test_context_is_bounded_and_preserves_nearest_visible_quote(self):
        table, = extract_html_tables('<p>' + 'x' * 1000 + ' "nearest quote"</p><table><tr><td>x</td></tr></table>')
        self.assertLessEqual(len(table['context']), 500)
        self.assertTrue(table['context'].endswith('"nearest quote"'))

    def test_blank_and_currency_cells_keep_their_source_columns(self):
        table, = extract_html_tables('<table><tr><th>Loan</th><td></td><td>$</td><td>10</td></tr></table>')
        cells = table['rows'][0]['cells']
        self.assertEqual([cell['text'] for cell in cells], ['Loan', '', '$', '10'])
        self.assertEqual([cell['column_index'] for cell in cells], [0, 1, 2, 3])
        self.assertEqual([cell['tag'] for cell in cells], ['th', 'td', 'td', 'td'])

    def test_overflowing_rows_are_flagged_and_bounded(self):
        table, = extract_html_tables('<table>' + '<tr></tr>' * 10001 + '</table>')
        self.assertEqual(len(table['rows']), 10000)
        self.assertEqual(len(table['grid']), 10000)
        self.assertIn('row_limit', table['quality_flags'])

    def test_deep_nested_tables_are_flagged_and_bounded(self):
        tables = extract_html_tables('<table><tr><td>' * 51 + 'x' + '</td></tr></table>' * 51)
        self.assertEqual(len(tables), 50)
        self.assertIn('table_depth_limit', tables[-1]['quality_flags'])

    def test_visible_text_overflow_is_flagged_with_original_span_retained(self):
        source = '<table><tr><td>' + 'x' * 1000001 + '</td></tr></table>'
        table, = extract_html_tables(source)
        cell, = table['rows'][0]['cells']
        self.assertEqual(len(cell['text']), 1000000)
        self.assertIn('text_limit', table['quality_flags'])
        self.assertEqual(source[cell['char_start']:cell['char_end']], '<td>' + 'x' * 1000001 + '</td>')

    def test_document_grid_budget_caps_span_expansion_across_tables(self):
        source = ('<table><tr><td rowspan="2" colspan="2">A</td></tr><tr></tr></table>'
                  '<table><tr><td rowspan="3" colspan="3">B</td></tr><tr></tr><tr></tr></table>')
        with patch('src.reit_tables.MAX_DOCUMENT_GRID_SLOTS', 6):
            first, second = extract_html_tables(source)
        self.assertEqual(first['grid'], [[first['rows'][0]['cells'][0]['cell_id']] * 2] * 2)
        self.assertLessEqual(sum(len(row) for table in [first, second] for row in table['grid']), 6)
        self.assertIn('grid_limit', second['quality_flags'])
        self.assertEqual(second['rows'][0]['cells'][0]['text'], 'B')

    def test_document_cell_budget_caps_retained_cells_across_tables(self):
        source = ('<table><tr><td>A</td><td>B</td></tr></table>'
                  '<table><tr><td>C</td><td>D</td></tr></table>')
        with patch('src.reit_tables.MAX_DOCUMENT_CELLS', 3):
            first, second = extract_html_tables(source)
        self.assertEqual([cell['text'] for table in [first, second] for row in table['rows']
                          for cell in row['cells']], ['A', 'B', 'C'])
        self.assertIn('document_cell_limit', second['quality_flags'])

    def test_grid_budget_checks_row_padding_before_allocation(self):
        source = '<table><tr><td>A</td></tr><tr><td>B</td><td>C</td><td>D</td></tr></table>'
        with patch('src.reit_tables.MAX_DOCUMENT_GRID_SLOTS', 4):
            table, = extract_html_tables(source)
        self.assertLessEqual(sum(len(row) for row in table['grid']), 4)
        self.assertIn('grid_limit', table['quality_flags'])
        self.assertEqual([cell['text'] for cell in table['rows'][1]['cells']], ['B', 'C', 'D'])

    def test_document_row_budget_caps_empty_rows_across_tables(self):
        source = '<table><tr></tr><tr></tr><tr></tr><tr></tr></table>' * 3
        with patch('src.reit_tables.MAX_DOCUMENT_ROWS', 5, create=True):
            first, second, third = extract_html_tables(source)
        self.assertEqual([len(table['rows']) for table in [first, second, third]], [4, 1, 0])
        self.assertEqual(sum(len(table['grid']) for table in [first, second, third]), 5)
        self.assertIn('document_row_limit', second['quality_flags'])
        self.assertIn('document_row_limit', third['quality_flags'])

    def test_document_row_limit_skips_cells_of_omitted_rows_without_crashing(self):
        source = '<table><tr><td>A</td></tr><tr><td>B</td></tr></table>'
        with patch('src.reit_tables.MAX_DOCUMENT_ROWS', 1, create=True):
            table, = extract_html_tables(source)
        self.assertEqual([cell['text'] for row in table['rows'] for cell in row['cells']], ['A'])
        self.assertIn('document_row_limit', table['quality_flags'])


if __name__ == '__main__':
    unittest.main()
