"""Read a verified repair payload from stdin; stage a new run, submit and collect it.

Executed through authenticated SSH with Python 3.9; only lightweight control and
result collection run on the login node. Model execution remains in Slurm.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

PATCH_FILES = {'hpc/setup_model_cache.py', 'hpc/run_document_pilot.py', 'hpc/prepare_lora_config.py',
               'src/glm_document_ocr.py'}


def emit(**record):
    print(json.dumps(record), flush=True)


def validate_payload(payload):
    base = Path(payload['base_directory']).resolve()
    if not base.is_relative_to(Path('/blue/ai-workshop/kkatiyar')):
        raise ValueError('Unexpected deployment directory')
    if not re.fullmatch(r'[a-z0-9-]+', payload['repair_name']):
        raise ValueError('Invalid repair name')
    expected = PATCH_FILES | ({'hpc/diagnose_glm_ocr.py', 'hpc/diagnose_glm_ocr.sbatch'} if payload.get('diagnose') else set())
    if set(payload['files']) != expected:
        raise ValueError('Repair files differ from the reviewed change scope')
    decoded = {}
    for name, record in payload['files'].items():
        data = base64.b64decode(record['base64'], validate=True)
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Repair content hash mismatch')
        if name.endswith('.py'):
            compile(data, name, 'exec')
        decoded[name] = data
    return base, decoded


def main():
    payload = json.load(sys.stdin)
    base, patches = validate_payload(payload)
    archive = base.parent / (base.name + '.tar.gz')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != payload['original_bundle_sha256']:
        raise ValueError('Original archive hash mismatch')
    manifest = json.loads((base / 'bundle-manifest.json').read_text())
    for name, digest in manifest['files'].items():
        source = (base / name).resolve()
        if not source.is_relative_to(base) or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError('Original deployment differs from verified bundle: ' + name)
    target = base / 'repairs' / payload['repair_name']
    target.mkdir(parents=True, exist_ok=False)
    for name in manifest['files']:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / name, destination)
    for name, data in patches.items():
        (target / name).write_bytes(data)
        manifest['files'][name] = hashlib.sha256(data).hexdigest()
    (target / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2))
    (target / 'repair-provenance.json').write_text(json.dumps({
        'original_bundle_sha256': payload['original_bundle_sha256'],
        'original_directory': str(base), 'changed_files': {
            name: hashlib.sha256(data).hexdigest() for name, data in patches.items()}}, indent=2))
    config = json.loads((base / 'hipergator.json').read_text())
    config.update(workdir=str(target), output_dir=str(target / 'results/pilot'))
    config_path = target / 'hipergator.json'
    config_path.write_text(json.dumps(config, indent=2))
    env = dict(os.environ, PYTHONNOUSERSITE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    preflight = subprocess.run([config['python'], 'hpc/setup_model_cache.py', '--cache-dir', config['model_cache'],
                                '--model', 'both'], cwd=target, env=env, capture_output=True, text=True)
    (target / 'cache-preflight.log').write_text(preflight.stdout + preflight.stderr)
    if preflight.returncode:
        emit(status='preflight_failed', output=preflight.stdout + preflight.stderr, remote_directory=str(target))
        return 1
    emit(status='offline_cache_verified', remote_directory=str(target))
    if payload.get('diagnose'):
        # The validated pilot launcher keeps the same resource and path checks.
        # Replace only its entrypoint in this fresh diagnostic deployment.
        shutil.copyfile(target / 'hpc/diagnose_glm_ocr.sbatch', target / 'hpc/document_pilot.sbatch')
        manifest['files']['hpc/document_pilot.sbatch'] = hashlib.sha256((target / 'hpc/document_pilot.sbatch').read_bytes()).hexdigest()
        (target / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2))
    submitted = subprocess.run([config['python'], 'hpc/submit_document_job.py', '--config', str(config_path),
                                '--manifest', str(target / 'pilot/documents.jsonl'), '--mode', 'pilot'],
                               cwd=target, env=env, capture_output=True, text=True)
    if submitted.returncode:
        emit(status='submission_failed', output=submitted.stdout + submitted.stderr, remote_directory=str(target))
        return 1
    match = re.fullmatch(r'([1-9][0-9]*)(?:;[A-Za-z0-9_.-]+)?', submitted.stdout.strip())
    if not match:
        raise ValueError('Unrecognized Slurm job ID: ' + submitted.stdout)
    job_id = match.group(1)
    (target / 'retry-job.json').write_text(json.dumps({'job_id': job_id, 'status': 'submitted_not_completed'}))
    emit(status='submitted_not_completed', job_id=job_id, remote_directory=str(target))
    previous = None
    deadline = time.monotonic() + 7200
    terminal = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'NODE_FAIL', 'PREEMPTED', 'BOOT_FAIL', 'DEADLINE'}
    while time.monotonic() < deadline:
        result = subprocess.run(['sacct', '-X', '-j', job_id, '-n', '-P', '--format=State%30,ExitCode,Elapsed'],
                                capture_output=True, text=True, timeout=30)
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if lines:
            state, exit_code, elapsed = lines[-1].split('|')[:3]
            state = state.strip().split()[0].rstrip('+')
            if (state, exit_code) != previous:
                emit(status='job_state', job_id=job_id, state=state, exit_code=exit_code, elapsed=elapsed)
                previous = (state, exit_code)
            if state in terminal:
                break
        time.sleep(20)
    else:
        emit(status='monitor_timeout', job_id=job_id, message='Job was not cancelled; check Slurm for remaining work.')
        return 2
    total = 0
    for source in sorted((target / 'results').rglob('*')):
        if not source.is_file() or source.suffix not in {'.json', '.jsonl', '.md', '.log'}:
            continue
        size = source.stat().st_size
        if size > 8_000_000 or total + size > 40_000_000:
            emit(status='artifact_not_copied_size_limit', path=str(source))
            continue
        data = source.read_bytes()
        total += len(data)
        emit(status='artifact', path=source.relative_to(target).as_posix(),
             sha256=hashlib.sha256(data).hexdigest(), base64=base64.b64encode(data).decode())
    emit(status='collection_finished', job_id=job_id, state=state, exit_code=exit_code,
         remote_directory=str(target), collected_bytes=total)
    return 0 if state == 'COMPLETED' and exit_code == '0:0' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        emit(status='repair_failed', error=type(error).__name__ + ': ' + str(error))
        raise
