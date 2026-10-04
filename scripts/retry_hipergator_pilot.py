"""Authenticate once, stage a reviewed cache repair, and collect its Slurm result."""
import base64
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = ('hpc/setup_model_cache.py', 'hpc/run_document_pilot.py', 'hpc/prepare_lora_config.py',
         'src/glm_document_ocr.py')


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf8')
    temporary.replace(path)


def save_artifact(directory, record):
    destination = (directory / record['path']).resolve()
    if not destination.is_relative_to(directory.resolve()):
        raise ValueError('Artifact path escapes result directory')
    data = base64.b64decode(record['base64'], validate=True)
    if hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError('Downloaded artifact hash mismatch')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--repair-name', default='cache-scope-v1')
    args = parser.parse_args()
    state_dir = ROOT / 'data/processed/hipergator'
    original = json.loads((state_dir / 'submission-status.json').read_text())
    payload = {'base_directory': original['remote_directory'], 'repair_name': args.repair_name,
               'diagnose': args.diagnose,
               'original_bundle_sha256': original['sha256'], 'files': {}}
    files = FILES + (('hpc/diagnose_glm_ocr.py', 'hpc/diagnose_glm_ocr.sbatch') if args.diagnose else ())
    for name in files:
        data = (ROOT / name).read_bytes()
        payload['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(),
                                  'base64': base64.b64encode(data).decode()}
    source = (ROOT / 'hpc/retry_cached_pilot.py').read_text(encoding='utf8')
    state_path = state_dir / 'retry-status.json'
    results = state_dir / args.repair_name
    state = {'status': 'awaiting_authentication', 'started_at_utc': datetime.now(timezone.utc).isoformat()}
    save_json(state_path, state)
    print('Complete password and Duo here. This connection will remain open to collect the GPU retry results.', flush=True)
    try:
        process = subprocess.Popen(['ssh', '-T', 'kkatiyar@hpg.rc.ufl.edu',
                                    'python3 -u -c ' + shlex.quote(source)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                   encoding='utf8', errors='replace')
        process.stdin.write(json.dumps(payload))
        process.stdin.close()
        with (state_dir / 'retry-events.jsonl').open('a', encoding='utf8') as events:
            for line in process.stdout:
                try:
                    record = json.loads(line)
                except ValueError:
                    print(line, end='', flush=True)
                    continue
                if record.get('status') == 'artifact':
                    save_artifact(results, record)
                    record = {key: value for key, value in record.items() if key != 'base64'}
                    print('Saved: ' + record['path'], flush=True)
                else:
                    state.update(record)
                    save_json(state_path, state)
                    print(json.dumps(record), flush=True)
                events.write(json.dumps(record) + '\n')
                events.flush()
        exit_code = process.wait()
        state['ssh_exit_code'] = exit_code
        if exit_code and state.get('status') not in ('repair_failed', 'preflight_failed', 'submission_failed', 'collection_finished', 'monitor_timeout'):
            state['status'] = 'connection_failed'
        return exit_code
    except Exception as error:
        state.update(status='local_collection_failed', error=str(error))
        raise
    finally:
        state['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        save_json(state_path, state)


if __name__ == '__main__':
    raise SystemExit(main())
