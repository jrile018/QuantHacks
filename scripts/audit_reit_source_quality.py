"""Read retained registries/manifests and emit a separate offline quality audit."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.reit_source_quality import audit_registry

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIVE = ROOT / 'data/processed/reit_source_validation/20261003/live_urls.json'
CATALOG = ROOT / 'docs/reit_document_urls.txt'


def _load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _rows(value, keys):
    if isinstance(value, list):
        return value
    for key in keys:
        if isinstance(value.get(key), list):
            return value[key]
    raise ValueError('Expected list or object containing ' + ', '.join(keys))


def _resolve(reference, owner):
    path = Path(reference)
    if path.is_absolute():
        return path
    # Existing collectors record repository-relative paths; portable examples
    # record paths relative to their manifest. Never guess missing filenames.
    candidates = [owner.parent / path, ROOT / path]
    return next((p for p in candidates if p.is_file()), candidates[0])


def _hydrate(source, owner, protected):
    source = dict(source)
    reference = source.get('source_path') or source.get('raw_path')
    if reference:
        raw_path = _resolve(reference, owner)
        protected.add(raw_path.resolve())
        if raw_path.is_file():
            source['raw_bytes'] = raw_path.read_bytes()
        else:
            source['offline_load_warning'] = 'retained_source_file_missing'
    # PDF text is read only when its extraction identity exactly binds to source.
    text_reference = source.get('text_path')
    if text_reference:
        text_path = _resolve(text_reference, owner)
        protected.add(text_path.resolve())
        if text_path.is_file():
            extracted = _load(text_path)
            binding = extracted.get('sha256') or extracted.get('raw_sha256')
            checks = (binding == source.get('sha256'),
                      extracted.get('source_url') == source.get('url'),
                      extracted.get('accession') == source.get('accession'))
            if all(checks):
                pages = extracted.get('pages') or []
                source['content_text'] = '\n'.join(str(p.get('text', '')) for p in pages)
                source['extracted_raw_sha256'] = binding
            else:
                source['offline_load_warning'] = 'extraction_identity_mismatch'
    return source


def build_report(result):
    lines = ['# REIT source quality audit', '', 'Mode: offline retained evidence.',
             'Financial accuracy: not assessed. OCR: not audited.',
             'Source eligibility, observation completeness, and point in time readiness are separate.', '',
             '| Source | Eligibility | Authority | Identity | Integrity | Observations | Point in time |',
             '|---|---|---|---|---|---|---|']
    for row in result['sources']:
        axes = row['quality_axes']
        fields = [row['url'], row['eligibility'], axes['authority']['state'], axes['content_identity']['state'],
                  axes['integrity']['state'], axes['financial_evidence']['state'], row['coverage']['point_in_time']]
        lines.append('| ' + ' | '.join(str(f).replace('|', '\\|').replace('\n', ' ') for f in fields) + ' |')
    lines += ['', '## Reasons and evidence gaps', '']
    for row in result['sources']:
        lines.append('- ' + row['url'].replace('\n', ' ') + ': ' + ', '.join(row['reasons']))
    lines += ['', '## Lineage and conflicts', '',
              f"Retained byte duplicate groups: {len(result['duplicate_groups'])}.",
              f"Comparable financial conflicts: {len(result['conflicts'])}.",
              'Same amounts alone do not establish duplicate lineage. No conflicts found does not establish agreement.',
              'Current directories and aggregators do not prove a complete dated REIT universe.',
              'HTTP 200 and rendered snippets do not prove financial document identity. 403/tool limits do not prove a dead source.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, action='append', default=[])
    parser.add_argument('--manifest', type=Path, action='append', default=[])
    parser.add_argument('--receipts', type=Path, action='append', default=[])
    parser.add_argument('--live-evidence', type=Path, default=DEFAULT_LIVE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    protected, sources, receipts, origins = set(), [], [], []
    live = _load(args.live_evidence) if args.live_evidence.is_file() else {'urls': []}
    protected.add(args.live_evidence.resolve())
    live_rows = {row['url']: row for row in live.get('urls', [])}
    for registry in args.registry:
        protected.add(registry.resolve()); origins.append(str(registry))
        sources += [_hydrate(s, registry, protected) for s in _rows(_load(registry), ('sources', 'urls'))]
    for manifest in args.manifest:
        protected.add(manifest.resolve()); origins.append(str(manifest))
        data = _load(manifest)
        companies = {_c.get('cik'): _c for _c in data.get('companies', [])}
        for doc in data.get('documents', []):
            source = dict(doc)
            company = companies.get(source.get('cik'), {})
            source.setdefault('issuer', company.get('company_name') or company.get('name'))
            source.setdefault('source_role', 'retained financial document')
            sources.append(_hydrate(source, manifest, protected))
        if not isinstance(data.get('documents'), list):
            raise ValueError('Manifest has no documents list: ' + str(manifest))
    if not sources:
        # Preserve exact 15 initial entries in their original order. Expanded
        # registries are opt-in and never replace or rewrite the initial catalog.
        urls = CATALOG.read_text(encoding='utf-8-sig').splitlines()
        protected.add(CATALOG.resolve()); origins.append(str(CATALOG))
        sources = [dict(live_rows.get(url, {}), url=url, catalog_number=i + 1, source_id='catalog:' + str(i + 1))
                   for i, url in enumerate(urls) if url]
    for source in sources:
        saved = live_rows.get(source.get('url'))
        if saved:
            source.setdefault('live_validation', saved.get('live_validation'))
            source.setdefault('provenance', saved.get('provenance'))
    for receipt_file in args.receipts:
        protected.add(receipt_file.resolve()); origins.append(str(receipt_file))
        receipts += _rows(_load(receipt_file), ('receipts', 'http_receipts', 'urls'))
    result = audit_registry(sources, receipts)
    result['audit_time_utc'] = datetime.now(timezone.utc).isoformat()
    result['input_files'] = origins
    for source, row in zip(sources, result['sources']):
        for key in ('catalog_number', 'provenance', 'source_path', 'text_path', 'offline_load_warning'):
            if key in source:
                row['evidence'][key] = source[key]
    outputs = [args.output / 'source_quality.json', args.output / 'source_quality.md']
    if any(path.resolve() in protected for path in outputs):
        raise ValueError('Audit output would overwrite retained input evidence')
    args.output.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    outputs[1].write_text(build_report(result), encoding='utf-8')
    print(json.dumps({'sources': len(sources), 'eligibility_counts': result['eligibility_counts'], 'outputs': [str(p.resolve()) for p in outputs]}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
