"""Download already purchased pilot batches on home-pc; never submit an order."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import time

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--jobs', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError('Download concurrency must be between 1 and 4')
    root = args.project.resolve()
    ownership = root / '.multi-market-owned-run'
    if not ownership.is_file() or ownership.read_text(encoding='utf-8').strip() != str(root):
        raise ValueError('Dedicated run ownership marker must match resolved project path')
    (root / 'results').mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('batch_downloader', root / 'scripts/download_databento_options.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    key = module._api_key(root)
    jobs = json.loads(args.jobs.read_text(encoding='utf-8'))
    job_ids = [job['id'] for job in jobs]
    if len(set(job_ids)) != len(job_ids) or not job_ids:
        raise ValueError('nonempty unique purchased job IDs required')
    state_file = root / 'results/download-status.json'
    status = {'jobs': {}, 'stage': 'downloading', 'credential_removed': False}
    completed = set()
    attempts = 0
    while len(completed) < len(job_ids):
        attempts += 1
        ready = []
        for job_id in job_ids:
            if job_id in completed:
                continue
            response = requests.get(module.API + 'batch.get_job_details',
                                    auth=(key, ''), params={'job_id': job_id}, timeout=60)
            if response.status_code != 200:
                raise RuntimeError(f'batch status HTTP {response.status_code}; no order retry')
            details = response.json()
            state = details.get('state')
            status['jobs'][job_id] = {name: details.get(name) for name in
                                      ('state', 'progress', 'record_count', 'cost_usd', 'actual_size')}
            if state == 'done':
                ready.append(job_id)
            elif state in {'failed', 'cancelled', 'canceled', 'expired'}:
                raise RuntimeError(f'purchased job {job_id} is {state}; no new request')
            status['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
            state_file.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(module.download_job, root, job_id): job_id for job_id in ready}
            for future in as_completed(futures):
                job_id = futures[future]
                summary = future.result()
                status['jobs'][job_id].update(downloaded_and_hashed=True,
                    files=len(summary['files']), manifest=str(root / 'data/raw/databento' / job_id / 'download_manifest.json'))
                completed.add(job_id)
                state_file.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
                print(f'JOB_VERIFIED {job_id} files={len(summary["files"])}', flush=True)
        if len(completed) < len(job_ids):
            if attempts >= 120:
                raise RuntimeError('purchased batches still incomplete; saved state retained')
            time.sleep(30)
    # This run owns only this dedicated credential copy, never the original project .env.
    credential = root / '.env'
    credential.unlink()
    status.update(stage='complete', credential_removed=True,
                  completed_at_utc=datetime.now(timezone.utc).isoformat())
    state_file.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    print('ALL_PURCHASED_PILOT_FILES_VERIFIED', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Suppress HTTP request internals/authentication in logs.
        print(f'DOWNLOAD_FAILED {type(exc).__name__}', file=sys.stderr, flush=True)
        raise SystemExit(1)
