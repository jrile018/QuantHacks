"""Run a bounded, source-checked REIT money pilot on a retained annual report."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil

if __package__ in (None, ''):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_reit_money import analyze_collection


REALTY_REPORT_URL = ('https://www.realtyincome.com/sites/realty-income/files/'
                     'realty-income/investors/quartely-and-annual-result/2025-annual-report.pdf')
REALTY_SHA256 = '3669f20ce919eef667a7485e669ac9c76720fe245e22fdba5f59201296a5e0bc'
REALTY_ACCESSION = 'local-realty-income-2025-annual-report'
DEFAULT_SOURCE = Path('data/raw/ocr-benchmark/realty-income-2025-annual-report.pdf')
DEFAULT_OUTPUT = Path('data/processed/reit_filing_pilot/realty_income_2025_meaning_v2')
DEFAULT_GOLD = Path('configs/reit_pilot_gold.json')
SAMPLED_PAGES = (69, 70, 85)
GOLD_PAGES = (69, 85)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def selected_native_pdf_pages(source: Path, page_numbers: tuple[int, ...]) -> list[dict]:
    """Read the two financial pages and their reporting-currency note."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(source)
    pages = []
    try:
        for number in page_numbers:
            if number < 1 or number > len(pdf):
                raise ValueError(f'PDF page {number} is outside the source')
            page = pdf[number - 1]
            try:
                text_page = page.get_textpage()
                try:
                    value = text_page.get_text_bounded()
                finally:
                    text_page.close()
            finally:
                page.close()
            if len(value.strip()) < 100:
                raise ValueError(f'PDF page {number} lacks usable native text')
            pages.append({'number': number, 'text': value, 'method': 'native_pdf_text',
                          'confidence': None, 'quality_flags': []})
    finally:
        pdf.close()
    return pages


def prepare_local_pdf(source: Path, root: Path, *, expected_sha256: str = REALTY_SHA256) -> dict:
    """Create collector-shaped local inputs without making a SEC request."""
    source = Path(source).resolve()
    root = Path(root).resolve()
    digest = sha256(source.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError('Retained PDF hash differs from the verified pilot source')
    raw_path = root / 'cache' / 'realty-income-2025-annual-report.pdf'
    text_path = root / 'text' / 'realty-income-2025-annual-report.json'
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if not raw_path.is_file() or sha256(raw_path.read_bytes()).hexdigest() != digest:
        shutil.copyfile(source, raw_path)
    extracted = None
    if text_path.is_file():
        try:
            cached = json.loads(text_path.read_text(encoding='utf-8'))
            if (cached.get('sha256') == digest and cached.get('source_path') == str(raw_path)
                    and cached.get('source_url') == REALTY_REPORT_URL
                    and cached.get('accession') == REALTY_ACCESSION
                    and isinstance(cached.get('pages'), list)
                    and [page.get('number') for page in cached['pages']] == list(SAMPLED_PAGES)):
                extracted = cached
        except (ValueError, OSError, AttributeError):
            pass
    if extracted is None:
        pages = selected_native_pdf_pages(raw_path, SAMPLED_PAGES)
        extracted = {'sha256': digest, 'source_path': str(raw_path),
                     'source_url': REALTY_REPORT_URL, 'accession': REALTY_ACCESSION,
                     'source_method': 'native_pdf_text_selected_pages',
                     'page_count': len(pages), 'pages': pages}
        _write_json(text_path, extracted)
    document = {'cik': '0000726728', 'accession': REALTY_ACCESSION,
                'filename': raw_path.name, 'url': REALTY_REPORT_URL,
                'source_path': str(raw_path), 'text_path': str(text_path),
                'sha256': digest, 'form': '2025 annual report including Form 10-K',
                'reportDate': '2025-12-31', 'document_role': 'annual_report_pdf'}
    manifest = {'run_status': 'complete', 'companies': [], 'documents': [document],
                'collection_mode': 'retained_official_company_pdf',
                'sampled_pdf_pages': list(SAMPLED_PAGES),
                'note': 'Two financial pages plus currency context; retained company PDF'}
    _write_json(root / 'manifest.json', manifest)
    return manifest


def _normalize(value: object) -> str:
    return ' '.join(str(value).casefold().split())


def _amount_key(value: object) -> str:
    # Account for source sign formatting without allowing 100 to match 1000.
    return _normalize(value).strip('()').lstrip('$-').strip()


def _has_evidence(item: dict, gold: dict) -> bool:
    if item.get('source_url') != gold['source_url']:
        return False
    for evidence in item.get('evidence', []):
        if evidence.get('evidence_role') not in (None, 'amount'):
            continue
        if evidence.get('page_number') != gold['page']:
            continue
        selected = evidence.get('selected_amount_text')
        if selected is not None and _amount_key(gold['amount_text']) != _amount_key(selected):
            continue
        year = evidence.get('column_year')
        if year is not None and gold.get('period') != year:
            continue
        quote = _normalize(evidence.get('quoted_text', ''))
        if _normalize(gold['label']) in quote and _normalize(gold['amount_text']) in quote:
            return True
    return False


def score_assertions(gold: list[dict], records: list[dict], candidates: list[dict]) -> dict:
    """Score sampled facts only; candidate presence is not correct interpretation."""
    results = []
    for assertion in gold:
        matched_records = [row for row in records if _has_evidence(row, assertion)]
        parsed = [row for row in matched_records if row.get('status') == 'parsed']
        def matches_period(row: dict) -> bool:
            period = assertion.get('period')
            if period is None:
                return True
            if len(period) == 4:
                return row.get('period_start') == period + '-01-01' and row.get('period_end') == period + '-12-31'
            return row.get('as_of_date') == period

        correct = [row for row in parsed if str(row.get('value')) == assertion['value_usd']
                   and row.get('currency') == assertion.get('currency', 'USD')
                   and matches_period(row) and all(row.get(key) == assertion[key]
                   for key in ('amount_kind', 'amount_basis', 'relationship'))]
        if parsed and len(correct) == len(parsed):
            outcome = 'classified_correctly'
        elif parsed:
            outcome = 'misclassified'
        elif matched_records or any(_has_evidence(row, assertion) for row in candidates):
            outcome = 'review_candidate'
        else:
            outcome = 'missed'
        results.append({'id': assertion['id'], 'outcome': outcome, 'page': assertion['page'],
                        'matched_record_count': len(matched_records),
                        'matched_candidate_count': sum(_has_evidence(row, assertion) for row in candidates)})
    counts = Counter(result['outcome'] for result in results)
    return {'summary': {'total': len(results), **{key: counts[key] for key in
            ('classified_correctly', 'misclassified', 'review_candidate', 'missed')}},
            'results': results}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def validate_answer_key(answer_key: dict) -> None:
    if answer_key.get('source_sha256') != REALTY_SHA256:
        raise ValueError('Answer key source hash differs from retained PDF')
    if answer_key.get('source_url') != REALTY_REPORT_URL:
        raise ValueError('Answer key source URL differs from retained PDF')
    assertions = answer_key.get('assertions')
    if not isinstance(assertions, list) or not assertions:
        raise ValueError('Answer key has no assertions')
    ids = [item.get('id') for item in assertions]
    if len(set(ids)) != len(ids):
        raise ValueError('Answer key contains duplicate assertion IDs')
    for item in assertions:
        if item.get('page') not in GOLD_PAGES:
            raise ValueError('Answer key assertion page is outside the selected PDF pages')
        if item.get('source_url') != REALTY_REPORT_URL:
            raise ValueError('Answer key assertion source URL differs from retained PDF')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--gold', type=Path, default=DEFAULT_GOLD)
    parser.add_argument('--max-candidates', type=int, default=100)
    args = parser.parse_args(argv)
    manifest = prepare_local_pdf(args.source, args.output_dir)
    analysis_dir = args.output_dir / f'analysis_{args.max_candidates}'
    analyzed = analyze_collection(args.output_dir, analysis_dir,
                                  max_candidates_per_document=args.max_candidates)
    answer_key = json.loads(args.gold.read_text(encoding='utf-8'))
    validate_answer_key(answer_key)
    assertions = answer_key['assertions']
    score = score_assertions(assertions, _read_jsonl(analysis_dir / 'money_records.jsonl'),
                             _read_jsonl(analysis_dir / 'review_candidates.jsonl'))
    score.update(source_sha256=manifest['documents'][0]['sha256'], source_url=REALTY_REPORT_URL,
                 analysis_manifest_sha256=sha256((analysis_dir / 'analysis_manifest.json').read_bytes()).hexdigest(),
                 candidate_limit=args.max_candidates, analyzer_status=analyzed['run_status'],
                 analyzed_document_count=analyzed['analyzed_document_count'],
                 candidates_omitted=sum(d.get('coverage', {}).get('candidates_omitted', 0)
                                        for d in analyzed['documents']))
    _write_json(analysis_dir / 'pilot_score.json', score)
    print(json.dumps({'analysis_dir': str(analysis_dir.resolve()), **score['summary'],
                      'candidates_omitted': score['candidates_omitted']}, indent=2))
    return 0 if analyzed['analyzed_document_count'] == 1 else 1


if __name__ == '__main__':
    raise SystemExit(main())
