"""Render one existing financial-table page for a bounded GPU OCR smoke run."""
import argparse
import hashlib
import json
from pathlib import Path
import re


BALANCE_SHEET_TITLE = 'CONSOLIDATED BALANCE SHEETS'
MINIMUM_NUMERIC_TOKENS = 20
CONTENTS_TITLES = {'TABLE OF CONTENTS', 'INDEX TO FINANCIAL STATEMENTS',
                   'INDEX TO CONSOLIDATED FINANCIAL STATEMENTS'}
NUMERIC_TOKEN = re.compile(r'(?<![\w,])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w,])')


def is_balance_sheet_page(text):
    """Find a standalone heading with table-like numeric density, not a mention."""
    lines = {re.sub(r'\s+', ' ', line).strip().upper() for line in text.splitlines()}
    if BALANCE_SHEET_TITLE not in lines or lines & CONTENTS_TITLES:
        return False
    return len(NUMERIC_TOKEN.findall(text)) >= MINIMUM_NUMERIC_TOKENS


def select_calibration_page(doc):
    """Return the zero-based first qualifying page; close all inspected resources."""
    for index in range(len(doc)):
        page = doc[index]
        try:
            textpage = page.get_textpage()
            try:
                if is_balance_sheet_page(textpage.get_text_range()):
                    return index
            finally:
                textpage.close()
        finally:
            page.close()
    raise ValueError('No financial-table page with an exact balance-sheet title and meaningful numeric content found; select a reviewed calibration page explicitly')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(args.pdf)
    try:
        selected = select_calibration_page(doc)
        page = doc[selected]
        try:
            bitmap = page.render(scale=150 / 72)
            try:
                image = bitmap.to_pil()
                args.output_dir.mkdir(parents=True, exist_ok=True)
                output = args.output_dir / ('financial-table-page-' + str(selected + 1) + '.png')
                image.save(output)
                image.close()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        doc.close()
    row = {'document_id': 'gpu_calibration:' + args.pdf.stem + ':page_' + str(selected + 1),
           'source_path': str(output.resolve()), 'source_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
           'parent_source_sha256': hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
           'parent_filename': args.pdf.name, 'page_number': selected + 1,
           'renderer': 'pypdfium2', 'dpi': 150, 'annotation_status': 'machine_unreviewed',
           'purpose': 'GPU OCR smoke only; annual-report calibration image, not an 8-K training label'}
    rows = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if r['document_id'] != row['document_id']] + [row]
    args.manifest.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    print(json.dumps(row, indent=2))


if __name__ == '__main__':
    main()
