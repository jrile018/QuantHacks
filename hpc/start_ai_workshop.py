"""Submit CPU setup and a dependent L4 pilot using the observed ai-workshop allocation.

This bootstrap uses only the standard library and supports the observed Python 3.9.
Run once from an extracted, verified bundle on HiPerGator.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hpc.submit_document_job import build_command
from src.glm_document_ocr import VERIFIED_MODEL_REVISION


def make_commands(root):
    root = Path(root).resolve()
    runtime = root / 'runtime'
    profile = dict(account='ai-workshop', qos='ai-workshop', partition='hpg-turin',
                   gres='gpu:l4:1', cpus_per_task=2, memory='16G', time='00:30:00',
                   workdir=str(root), python=str(runtime / 'env/bin/python'),
                   environment_script=str(runtime / 'activate.sh'),
                   output_dir=str(root / 'results/pilot'), model_cache=str(runtime / 'models'),
                   model_revision=VERIFIED_MODEL_REVISION, dtype='bfloat16')
    pilot = build_command(profile, root / 'pilot/documents.jsonl', mode='pilot')
    setup = ['sbatch', '--parsable', '--job-name=quanthaxs-setup',
             '--account=ai-workshop', '--qos=ai-workshop', '--partition=hpg-default',
             '--cpus-per-task=4', '--mem=16G', '--time=01:00:00',
             '--chdir=' + str(root), '--output=' + str(root / 'results/setup-%j.log'),
             str(root / 'hpc/environment_setup.sbatch'), str(root)]
    return setup, pilot, profile


def job_id(value):
    match = re.fullmatch(r'([1-9][0-9]*)(?:;[A-Za-z0-9_.-]+)?', value.strip())
    if not match:
        raise ValueError('Expected a parsable Slurm job ID')
    return match.group(1)


def dependent_command(command, setup_result):
    return command[:1] + ['--dependency=afterok:' + job_id(setup_result),
                          '--kill-on-invalid-dep=yes'] + command[1:]


def verify_bundle(root):
    manifest = json.loads((root / 'bundle-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        source = (root / name).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError('Invalid bundle source: ' + name)
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError('Bundle hash mismatch: ' + name)


def save(path, record):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    temporary.replace(path)


def main():
    if sys.platform != 'linux' or not ROOT.is_relative_to(Path('/blue/ai-workshop/kkatiyar')):
        raise RuntimeError('Run this deployment from /blue/ai-workshop/kkatiyar on HiPerGator')
    verify_bundle(ROOT)
    setup, pilot, profile = make_commands(ROOT)
    state_path = ROOT / 'deployment-jobs.json'
    state = {'status': 'preparing', 'setup_job_id': None, 'pilot_job_id': None,
             'commands': {'setup': setup, 'pilot_without_dependency': pilot},
             'resource_settings_basis': 'User-provided slurmInfo and sinfo, 2026-10-03'}
    # Exclusive creation prevents accidentally submitting the same deployment twice.
    with state_path.open('x') as handle:
        json.dump(state, handle, indent=2)
    try:
        runtime = ROOT / 'runtime'
        runtime.mkdir(exist_ok=False)
        (ROOT / 'results').mkdir(exist_ok=True)
        (runtime / 'activate.sh').write_text(
            'export PYTHONNOUSERSITE=1\nunset PYTHONPATH PYTHONHOME\n'
            'export PATH=' + shlex.quote(str(runtime / 'env/bin')) + ':"$PATH"\n'
            'export HF_HOME=' + shlex.quote(str(runtime / 'hf-home')) + '\n', encoding='utf8')
        (ROOT / 'hipergator.json').write_text(json.dumps(profile, indent=2))
        result = subprocess.run(setup, check=True, capture_output=True, text=True)
        state['setup_job_id'] = job_id(result.stdout)
        state['status'] = 'setup_submitted'
        save(state_path, state)
        print('Setup job: ' + state['setup_job_id'], flush=True)
        command = dependent_command(pilot, result.stdout)
        state['commands']['pilot'] = command
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        state['pilot_job_id'] = job_id(result.stdout)
        state['status'] = 'submitted_not_completed'
        save(state_path, state)
        print('GPU pilot job: ' + state['pilot_job_id'], flush=True)
        print('Status: squeue -j ' + state['setup_job_id'] + ',' + state['pilot_job_id'])
        print('Logs: ' + str(ROOT / 'results'))
    except Exception as error:
        state['status'] = 'submission_failed'
        state['error'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            state['stderr'] = error.stderr
            print(error.stderr, file=sys.stderr)
        save(state_path, state)
        raise


if __name__ == '__main__':
    main()
