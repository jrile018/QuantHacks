"""Offline metadata and exact-extractor compatibility receipt for one archive capture."""
import ast
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path

here = Path(__file__).resolve().parent
source = Path('/tmp/quanthaxs-reit-pilot-repair-20261004-v1/source-pack')
retained = source / 'objects/d3e0d2b13d9b4ff50cb104362855975b96dfc354804343f5bdfe1a9c842c3a62'
retained_native = source / 'release-sources-v2/0001053507-24-000009-press_release_exhibit.txt'
capture = here / 'feb_sec_capture.raw'
receipt = json.loads((here / 'receipt.json').read_text())
url = 'https://www.sec.gov/Archives/edgar/data/1053507/000105350724000009/pressreleaseq42023.htm'
stamp = '20240227130804'

def sha(data): return hashlib.sha256(data).hexdigest()
def jsha(path): return sha(path.read_bytes())

# Compile just the unchanged class node from the retained producer's exact source file.
producer_path = here / 'collect_reit_peer_originals.py'
tree = ast.parse(producer_path.read_text(encoding='utf-8'))
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'NativeText')
namespace = {'HTMLParser': HTMLParser}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(producer_path), 'exec'), namespace)
NativeText = namespace['NativeText']

def native(data):
    p = NativeText()
    p.feed(data.decode('utf-8', errors='replace'))
    p.close()
    return ''.join(p.parts).encode('utf-8')

module_path = here / 'document_transcript.py'
spec = importlib.util.spec_from_file_location('document_transcript_verbatim', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# The extractor dispatches HTML based on suffix. Symlink source bytes in our own scratch.
archive_html = here / 'archived_exhibit.html'
retained_html = here / 'retained_exhibit.html'
for link, target in [(archive_html, capture), (retained_html, retained)]:
    if link.exists() or link.is_symlink(): link.unlink()
    link.symlink_to(target)
archive_record = module.extract_path(archive_html, 'amt-feb-archive', jsha(capture))
retained_record = module.extract_path(retained_html, 'amt-feb-retained', jsha(retained))
archive_native = native(capture.read_bytes())
retained_native_generated = native(retained.read_bytes())

scorer_root = Path('/home/john-riley/quant_hacks_financial_research/wording-2024-minimal-20261004-v1')
scorer_path = scorer_root / 'inputs-v1/transcripts/d3e0d2b13d9b4ff50cb104362855975b96dfc354804343f5bdfe1a9c842c3a62.json'
handoff_path = scorer_root / 'results/aggregate-v1/wording-event-handoff.json'
scorer = json.loads(scorer_path.read_bytes())
handoff = json.loads(handoff_path.read_bytes())
scorer_text = scorer['normalized_text']
fragments = handoff['candidates'][0]['fragment_lineage']
span_checks = [isinstance(f.get('char_start'), int) and isinstance(f.get('char_end'), int)
               and 0 <= f['char_start'] < f['char_end'] <= len(scorer_text)
               and scorer_text[f['char_start']:f['char_end']] == f.get('quoted_text')
               and f.get('text_sha256') == scorer['text_sha256']
               and f.get('character_weight') == f['char_end'] - f['char_start']
               for f in fragments]

cdx = receipt['results']['feb_sec_cdx']
row = cdx['rows'][1]
replay = receipt['captures'][0]
expected_replay = 'https://web.archive.org/web/' + stamp + 'id_/' + url
memento = replay['headers']['memento-datetime']
memento_utc = datetime.strptime(memento, '%a, %d %b %Y %H:%M:%S GMT').replace(tzinfo=timezone.utc)
expected_utc = datetime.strptime(stamp, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
checks = {
    'cdx_status_200': cdx.get('status') == 200,
    'cdx_original_url_exact': row[1] == url,
    'cdx_timestamp_exact': row[0] == stamp,
    'cdx_capture_http_200_html': row[2:4] == ['200','text/html'],
    'replay_requested_url_exact': replay['url'] == expected_replay,
    'replay_final_url_exact': replay['final_url'] == expected_replay,
    'replay_http_200': replay['status'] == 200,
    'memento_timestamp_matches_cdx': memento_utc == expected_utc,
    'capture_payload_hash_matches_receipt': jsha(capture) == replay['sha256'],
    'retained_raw_expected_hash': jsha(retained) == 'd3e0d2b13d9b4ff50cb104362855975b96dfc354804343f5bdfe1a9c842c3a62',
    'retained_native_expected_hash': jsha(retained_native) == '281856042cd75a0d40c79a76679a679d5c4a6e11cf2d1cdb51679c5e46e9cdb5',
    'producer_native_regenerates_retained_text': retained_native_generated == retained_native.read_bytes(),
    'archive_native_equals_retained_native_full_bytes': archive_native == retained_native.read_bytes(),
    'document_text_v1_full_text_equal': archive_record['normalized_text'] == retained_record['normalized_text'],
    'scorer_json_expected_sha256': jsha(scorer_path) == '28ee13d850c908503528b14a67d2ebd80c17d45e8c6036ca59e1f51bd0043efa',
    'scorer_source_sha256_matches_retained': scorer['source_sha256'] == jsha(retained),
    'scorer_version_and_engine_match': scorer['normalization_version'] == module.NORMALIZATION_VERSION and scorer['adapter_revision'] == module.ADAPTER_REVISION and scorer['extraction_method'] == 'native_html' and scorer['engine_revision'] == 'stdlib_v1' and scorer['settings'] == {},
    'scorer_text_hash_verified': sha(scorer_text.encode('utf-8')) == scorer['text_sha256'] == '4776176a977db7c3bd00eb8fd53b4e977ad7866642597dff4c8e50034c6743f4',
    'archive_full_text_equals_actual_scorer_text': archive_record['normalized_text'] == scorer_text,
    'handoff_expected_sha256': jsha(handoff_path) == '705842bb3df0d3faabfcf858953831090855e198a26e6ccc2139d547147abd4f',
    'handoff_fragment_count_exact': handoff['candidates'][0]['fragment_count'] == len(fragments) == 716,
    'all_handoff_fragment_spans_and_quotes_match_scorer_text': all(span_checks),
    'handoff_retains_excluded_truncated_status': handoff['candidates'][0]['status'] == 'excluded' and handoff['exclusion_counts'].get('truncated_fragment') == 1 and handoff['candidates'][0]['qualified_value'] is None,
}
out = {
    'checks': checks,
    'all_checks_pass': all(checks.values()),
    'expected_original_url': url,
    'cdx_digest': row[4],
    'capture_timestamp_utc': expected_utc.isoformat(),
    'memento_datetime': memento,
    'source_code': {'producer_native_path': str(producer_path), 'producer_source_sha256': jsha(producer_path), 'canonical_module_path': str(module_path), 'canonical_module_sha256': jsha(module_path), 'canonical_normalization_version': module.NORMALIZATION_VERSION, 'canonical_adapter_revision': module.ADAPTER_REVISION},
    'raw': {'capture_sha256': jsha(capture), 'retained_sha256': jsha(retained)},
    'producer_native': {'capture_sha256': sha(archive_native), 'retained_regenerated_sha256': sha(retained_native_generated), 'retained_artifact_sha256': jsha(retained_native), 'capture_chars': len(archive_native.decode('utf-8')), 'retained_chars': len(retained_native.read_text(encoding='utf-8'))},
    'document_text_v1': {'archive_text_sha256': archive_record['text_sha256'], 'retained_text_sha256': retained_record['text_sha256'], 'archive_chars': len(archive_record['normalized_text']), 'retained_chars': len(retained_record['normalized_text']), 'archive_flags': archive_record['quality_flags'], 'retained_flags': retained_record['quality_flags'], 'archive_tables': len(archive_record['table_records']), 'retained_tables': len(retained_record['table_records'])},
    'actual_scorer': {'path': str(scorer_path), 'json_bytes': scorer_path.stat().st_size, 'json_sha256': jsha(scorer_path), 'normalized_text_chars': len(scorer_text), 'normalized_text_utf8_sha256': sha(scorer_text.encode('utf-8')), 'normalization_version': scorer['normalization_version'], 'extraction_method': scorer['extraction_method'], 'engine_revision': scorer['engine_revision'], 'adapter_revision': scorer['adapter_revision'], 'settings': scorer['settings']},
    'actual_fullspan_handoff': {'path': str(handoff_path), 'json_bytes': handoff_path.stat().st_size, 'json_sha256': jsha(handoff_path), 'fragments': len(fragments), 'fragment_span_quote_matches': sum(span_checks), 'fragment_character_weight_sum': sum(f['character_weight'] for f in fragments), 'truncated_fragment_count': sum(bool(f.get('financial_sentiment', {}).get('truncated')) for f in fragments), 'status': handoff['candidates'][0]['status'], 'qualified_value': handoff['candidates'][0]['qualified_value'], 'exclusion_counts': handoff['exclusion_counts']},
    'http_attempts_note': 'Probe counted six top-level urllib requests. Automatic redirects, if any, were not separately counted; final replay URL matched request.',
    'scorer_span_binding': 'complete_exact_full_text_and_all_fragment_spans',
    'canonical_accepted': False,
}
(here / 'acceptance-check.json').write_text(json.dumps(out, indent=2) + '\n', encoding='utf-8')
print(json.dumps(out, indent=2))
