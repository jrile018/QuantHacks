"""The calibration selector must distinguish table headings from prose/TOC."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch

from scripts import prepare_gpu_calibration_page as calibration


def table_text(title='CONSOLIDATED BALANCE SHEETS', count=74):
    numbers = ' '.join(f'{1000 + number:,}' for number in range(count))
    return title + '\nAssets and liabilities as of year end\n' + numbers


class CalibrationSelectionTests(unittest.TestCase):
    def test_main_renders_page_66_instead_of_page_53_prose(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pdf = root / 'report.pdf'
            pdf.write_bytes(b'PDF fixture; PDFium is mocked')
            manifest = root / 'documents.jsonl'
            manifest.write_text('')
            pages = [Mock() for _ in range(66)]
            for page in pages:
                page.get_textpage.return_value.get_text_range.return_value = 'ordinary narrative'
            pages[52].get_textpage.return_value.get_text_range.return_value = ('See CONSOLIDATED BALANCE SHEETS in the report. ' * 20) + '\n53'
            pages[65].get_textpage.return_value.get_text_range.return_value = table_text()
            doc = MagicMock()
            doc.__len__.return_value = len(pages)
            doc.__getitem__.side_effect = pages.__getitem__
            for page in (pages[52], pages[65]):
                page.render.return_value.to_pil.return_value.save.side_effect = lambda path: Path(path).write_bytes(b'rendered table fixture')
            factory = Mock(return_value=doc)
            argv = ['prepare_gpu_calibration_page.py', '--pdf', str(pdf), '--manifest', str(manifest), '--output-dir', str(root / 'rendered')]
            with patch.dict('sys.modules', {'pypdfium2': SimpleNamespace(PdfDocument=factory)}), patch('sys.argv', argv), patch('builtins.print'):
                calibration.main()
            row = json.loads(manifest.read_text())
            self.assertEqual(row['page_number'], 66)
            pages[52].render.assert_not_called()
            pages[65].render.assert_called_once_with(scale=150 / 72)
            doc.close.assert_called_once()

    def test_prose_mention_does_not_select_a_table_page(self):
        prose = ('See our CONSOLIDATED BALANCE SHEETS for further information. '
                 'The statements accompany the following discussion. ') * 8 + '\n53'
        self.assertFalse(calibration.is_balance_sheet_page(prose))
        # A long narrative with many numbers still lacks the exact title line.
        self.assertFalse(calibration.is_balance_sheet_page(prose + '\n' + table_text().split('\n')[-1]))

    def test_title_normalizes_case_and_horizontal_whitespace(self):
        self.assertTrue(calibration.is_balance_sheet_page(table_text('  Consolidated\u00a0  balance\t sheets  ')))

    def test_sparse_title_and_toc_are_rejected(self):
        self.assertFalse(calibration.is_balance_sheet_page('CONSOLIDATED BALANCE SHEETS\n53'))
        self.assertFalse(calibration.is_balance_sheet_page('Consolidated Balance Sheets ........ 66\n' + table_text().split('\n')[-1]))
        self.assertFalse(calibration.is_balance_sheet_page('TABLE OF CONTENTS\n' + table_text()))

    def test_meaningful_numeric_token_threshold(self):
        self.assertFalse(calibration.is_balance_sheet_page(table_text(count=19)))
        self.assertTrue(calibration.is_balance_sheet_page(table_text(count=20)))
        self.assertFalse(calibration.is_balance_sheet_page('CONSOLIDATED BALANCE SHEETS\n' + ' '.join('note' + str(n) for n in range(74))))

    def test_selects_table_after_prose_and_closes_pdf_resources(self):
        texts = [
            'See CONSOLIDATED BALANCE SHEETS in the report. ' * 20 + '53',
            'TABLE OF CONTENTS\n' + table_text(),
            table_text(),
        ]
        pages = []
        for text in texts:
            page = Mock()
            page.get_textpage.return_value.get_text_range.return_value = text
            pages.append(page)
        self.assertEqual(calibration.select_calibration_page(pages), 2)
        for page in pages:
            page.get_textpage.return_value.close.assert_called_once()
            page.close.assert_called_once()
            page.render.assert_not_called()

    def test_missing_table_fails_without_rendering(self):
        page = Mock()
        page.get_textpage.return_value.get_text_range.return_value = 'ordinary narrative 2025'
        with self.assertRaisesRegex(ValueError, 'financial-table'):
            calibration.select_calibration_page([page])
        page.close.assert_called_once()
        page.render.assert_not_called()


if __name__ == '__main__':
    unittest.main()
