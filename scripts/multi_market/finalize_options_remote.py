#!/usr/bin/env python3
"""Finish one already-paid OPRA batch remotely, without ordering more data.

Stage the existing downloader, normalizer, native ingest, and frozen matched
diagnostic beside this script. --check-staged is read-only with respect to API
and creates a frozen source hash record. The real run belongs in remote tmux.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

JOB_ID = 'OPRA-20261003-4APD3MDYPJ'
RUN_ID = 'databento-full-20261003'
REMOTE_ROOT = Path('/home/john-riley/QuantHacks/multi-market-20261003/full-options')
SCORES = Path('/home/john-riley/projects/geomarket/runs/pit-survivorship/gm-boundaries/scores.parquet')
SOURCE_TABLES = ('events', 'results', 'capacity', 'option_legs', 'option_bars')
ASSETS = ('scripts/multi_market/finalize_options_remote.py',
          'scripts/multi_market/run_options_matched_study.py',
          'scripts/download_databento_options.py', 'scripts/build_databento_daily_quotes.py',
          'stat-arb/tools/options_native.py', 'stat-arb/tools/options_bridge.py',
          'hpc/multi_market/run_full_options.sh')


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def source_hashes(project: Path) -> dict:
    source = project / 'data/processed/cfo-2024-2025-massive'
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    hashes = {asset: sha(project / asset) for asset in ASSETS}
    hashes['data/processed/cfo-2024-2025-massive/manifest.json'] = sha(source / 'manifest.json')
    for name in SOURCE_TABLES:
        path = source / (name + '.csv')
        digest = sha(path)
        if manifest.get('exported_tables', {}).get(name, {}).get('sha256') != digest:
            raise ValueError(f'original study manifest hash mismatch: {name}')
        hashes[str(path.relative_to(project))] = digest
    return hashes


def safe_job_details(details: dict) -> dict:
    """Persist only a known job's nonsensitive status metadata."""
    if not isinstance(details, dict):
        raise ValueError('unexpected batch job metadata')
    if details.get('job_id', JOB_ID) != JOB_ID or details.get('id', JOB_ID) != JOB_ID:
        raise ValueError('response belongs to a different job')
    return {key: details[key] for key in ('state', 'progress', 'cost_usd', 'record_count', 'actual_size')
            if key in details}


def staged_check(project: Path) -> dict:
    sys.path.insert(0, str(project / 'scripts'))
    # Import the existing modules to establish that their dependencies are ready.
    import requests  # noqa: F401
    import pyarrow  # noqa: F401
    import pandas  # noqa: F401
    import download_databento_options  # noqa: F401
    import build_databento_daily_quotes  # noqa: F401
    if not SCORES.is_file():
        raise FileNotFoundError('native exact-score source is missing')
    hashes = source_hashes(project)
    path = project / 'staged_provenance.json'
    payload = {'job_id': JOB_ID, 'run_id': RUN_ID, 'existing_paid_job_only': True,
               'additional_orders': False, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
               'source_sha256': hashes, 'scores': str(SCORES),
               'scope': 'download all files of this existing batch; normalize, ingest, unchanged matched protocol'}
    if path.exists():
        frozen = json.loads(path.read_text(encoding='utf-8'))
        if frozen.get('job_id') != JOB_ID or frozen.get('source_sha256') != hashes:
            raise ValueError('staged source assets changed after freeze')
        return frozen
    write_json(path, payload)
    return payload


def run(project: Path) -> None:
    if os.name != 'posix' or project.resolve() != REMOTE_ROOT:
        raise RuntimeError('heavy finalization must run at the isolated home-pc root')
    import fcntl
    sys.path.insert(0, str(project / 'scripts'))
    import requests
    from download_databento_options import _api_key, download_job
    from build_databento_daily_quotes import build

    with (project / 'full_options.lock').open('a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('another full-options finalizer already owns this namespace') from None
        frozen_path = project / 'staged_provenance.json'
        if not frozen_path.exists():
            raise RuntimeError('staged readiness freeze is missing')
        frozen = json.loads(frozen_path.read_text(encoding='utf-8'))
        if frozen.get('job_id') != JOB_ID or source_hashes(project) != frozen.get('source_sha256'):
            raise ValueError('source assets differ from staged readiness freeze')
        results = project / 'results'
        if any((results / name).exists() for name in ('gm-options-ingest', 'gm-options-study', 'options-matched-v1')):
            raise FileExistsError('an output exists; preserve it and choose an explicit recovery action')
        ledger_path = project / 'full_options_ledger.json'
        ledger = {'job_id': JOB_ID, 'run_id': RUN_ID, 'existing_paid_job_only': True,
                  'additional_orders': False, 'history': [], 'source_sha256': frozen['source_sha256']}
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
            if ledger.get('job_id') != JOB_ID:
                raise ValueError('namespace ledger belongs to a different job')

        def status(stage: str, **details) -> None:
            payload = {'job_id': JOB_ID, 'run_id': RUN_ID, 'stage': stage,
                       'checked_at_utc': datetime.now(timezone.utc).isoformat(), **details}
            write_json(project / 'finalize_status.json', payload)
            ledger['history'].append(payload)
            write_json(ledger_path, ledger)
            print(json.dumps(payload, sort_keys=True, allow_nan=False), flush=True)

        secret = project / '.env'
        if not secret.is_file() or stat.S_IMODE(secret.stat().st_mode) & 0o077:
            raise RuntimeError('temporary Databento key file must exist with mode 0600 or stricter')
        started = time.monotonic()
        try:
            key = _api_key(project)
            if not key:
                raise RuntimeError('temporary Databento key is empty')
            try:
                while True:
                    try:
                        response = requests.get('https://hist.databento.com/v0/batch.get_job_details',
                            auth=(key, ''), params={'job_id': JOB_ID}, timeout=(10, 60))
                        response.raise_for_status()
                        metadata = safe_job_details(response.json())
                    except requests.RequestException as exc:
                        status('poll_error', error_type=type(exc).__name__)
                    else:
                        state = metadata.get('state')
                        status('ready' if state == 'done' else 'waiting', **metadata)
                        if state == 'done':
                            ledger['paid_job_metadata'] = metadata
                            write_json(ledger_path, ledger)
                            break
                        if state in ('expired', 'failed', 'cancelled', 'canceled'):
                            raise RuntimeError('existing paid job is terminal without downloadable data')
                    if time.monotonic() - started >= 8 * 60 * 60:
                        raise TimeoutError('existing job did not complete within the bounded eight-hour wait')
                    time.sleep(90)
                status('downloading')
                downloaded = download_job(project, JOB_ID)
                ledger['download_manifest_sha256'] = sha(project / 'data/raw/databento' / JOB_ID / 'download_manifest.json')
                ledger['downloaded_files'] = len(downloaded['files'])
                write_json(ledger_path, ledger)
            finally:
                secret.unlink(missing_ok=True)
                del key
            status('download_verified_key_removed', files=ledger['downloaded_files'])
            status('normalizing')
            quote_summary = build(project, JOB_ID)
            ledger['quote_summary'] = quote_summary
            write_json(ledger_path, ledger)
            native = project / 'stat-arb/tools/options_native.py'
            source = project / 'data/processed/cfo-2024-2025-massive'
            ingest = results / 'gm-options-ingest'
            study = results / 'gm-options-study'
            matched = results / 'options-matched-v1'
            status('lattice_ingest', daily_quote_marks=quote_summary['daily_quote_marks'])
            subprocess.run([sys.executable, str(native), 'ingest', '--study-dir', str(source),
                '--quotes', quote_summary['output'], '--output-dir', str(ingest), '--run-id', RUN_ID],
                cwd=project, check=True)
            status('lattice_native_study')
            subprocess.run([sys.executable, str(native), 'study', '--ingest-dir', str(ingest),
                '--scores', str(SCORES), '--output-dir', str(study), '--run-id', RUN_ID], cwd=project, check=True)
            status('matched_diagnostic')
            subprocess.run([sys.executable, str(project / 'scripts/multi_market/run_options_matched_study.py'),
                '--ingest-dir', str(ingest), '--scores', str(SCORES), '--output', str(matched)],
                cwd=project, check=True)
            matched_summary = json.loads((matched / 'summary.json').read_text(encoding='utf-8'))
            artifacts = [project / 'staged_provenance.json', project / 'full_options_ledger.json',
                         project / 'data/raw/databento' / JOB_ID / 'download_manifest.json',
                         Path(quote_summary['output']), Path(quote_summary['output']).with_name('quote_coverage.json')]
            artifacts += [path for path in results.rglob('*') if path.is_file()]
            # The ledger and final status change below; freeze only stable artifacts.
            artifacts = [path for path in artifacts if path != ledger_path]
            write_json(project / 'result_sha256.json', {'job_id': JOB_ID,
                'sha256': {str(path.relative_to(project)): sha(path) for path in artifacts}})
            status('complete', diagnostic_status=matched_summary['status'],
                daily_quote_marks=quote_summary['daily_quote_marks'], coverage=matched_summary['coverage'],
                economic_profit_claim=False, temporary_key_removed=not secret.exists())
        except Exception as exc:
            # Preserve raw data and all partial outputs. Never expose credentials
            # or potentially signed download URLs in an exception traceback.
            secret.unlink(missing_ok=True)
            status('failed', error_type=type(exc).__name__, temporary_key_removed=not secret.exists())
            raise SystemExit(1) from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--check-staged', action='store_true', help='Validate/freeze assets without API requests or heavy jobs')
    args = parser.parse_args(argv)
    if args.check_staged:
        checked = staged_check(args.project.resolve())
        print(json.dumps({'stage': 'staged_ready', 'job_id': JOB_ID,
                          'source_files': len(checked['source_sha256']), 'additional_orders': False}))
    else:
        run(args.project.resolve())
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'stage': 'failed_before_start', 'job_id': JOB_ID,
                          'error_type': type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
