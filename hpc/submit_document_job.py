"""Validate a finite input manifest and print or submit an explicit Slurm job."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_document_batch import read_manifest


def build_command(config, manifest, *, mode='ocr'):
    if mode not in ('ocr', 'lora', 'pilot'):
        raise ValueError('mode must be ocr, lora or pilot')
    required = ('account', 'qos', 'partition', 'gres', 'cpus_per_task', 'memory', 'time',
                'workdir', 'python', 'output_dir', 'model_cache', 'model_revision', 'environment_script')
    for key in required:
        value = config.get(key)
        if value is None or value == '' or '\n' in str(value) or '\r' in str(value):
            raise ValueError('Explicit nonempty runtime configuration required: ' + key)
    if not re.fullmatch('[0-9a-f]{40}', config['model_revision']):
        raise ValueError('model_revision must be a pinned commit SHA')
    if config.get('dtype', 'bfloat16') not in ('bfloat16', 'float16'):
        raise ValueError('dtype must be bfloat16 or float16')
    if int(config['cpus_per_task']) <= 0 or not str(config['gres']).startswith('gpu:'):
        raise ValueError('Positive CPUs and explicit GPU GRES required')
    if not re.fullmatch(r'\d+(?:[KMGTP])?', str(config['memory']), re.I):
        raise ValueError('memory must be an explicit Slurm size')
    if not re.fullmatch(r'(?:\d+-)?\d{1,3}:\d{2}:\d{2}', config['time']):
        raise ValueError('time must be HH:MM:SS or D-HH:MM:SS')
    path = Path(manifest).resolve()
    read_manifest(path, unique_documents=mode != 'lora')  # No automatic catalog/corpus selection.
    workdir = str(config['workdir'])
    if mode == 'lora' and not config.get('training_dataset_dir'):
        raise ValueError('lora requires training_dataset_dir from reviewed export')
    output = Path(config['output_dir'])
    if mode in ('lora', 'pilot') and output.exists():
        raise ValueError(mode + ' requires a fresh output directory')
    if mode == 'pilot':
        from hpc.run_document_pilot import read_filings
        from src.glm_document_ocr import VERIFIED_MODEL_REVISION
        if config['model_revision'] != VERIFIED_MODEL_REVISION:
            raise ValueError('Combined pilot requires its verified model revision')
        read_filings(path.parent / 'filings.json')
    log_path = output.parent / (output.name + '-slurm-%j.log') if mode in ('lora', 'pilot') else output / 'slurm-%j.log'
    # Config values are positional arguments, never interpolated into shell code.
    command = ['sbatch', '--parsable', '--job-name=quanthaxs-document-' + mode,
               '--account=' + config['account'], '--qos=' + config['qos'],
               '--partition=' + config['partition'], '--gres=' + config['gres'],
               '--cpus-per-task=' + str(config['cpus_per_task']), '--mem=' + str(config['memory']),
               '--time=' + config['time'], '--chdir=' + workdir,
               '--output=' + str(log_path),
               str(Path(workdir) / 'hpc' / ('document_' + mode + '.sbatch'))]
    if mode == 'pilot':
        command.extend([config['environment_script'], config['python'], str(config['model_cache']),
                        str(config['output_dir']), str(path), str(path.parent / 'filings.json')])
    else:
        command.extend([config['environment_script'], config['python'], str(path), str(config['output_dir']),
                        config['model_revision'], str(config['model_cache']), config.get('dtype', 'bfloat16')])
    if mode == 'lora':
        command.append(config['training_dataset_dir'])
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--mode', choices=('ocr', 'lora', 'pilot'), default='ocr')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    command = build_command(config, args.manifest, mode=args.mode)
    if args.dry_run:
        print(shlex.join(command))
        return 0
    if sys.platform == 'win32':
        raise RuntimeError('Submission must run on HiPerGator with the deployed manifest/config paths')
    for key in ('workdir', 'python', 'environment_script'):
        if not Path(config[key]).exists():
            raise ValueError('Runtime path does not exist: ' + key)
    output = Path(config['output_dir'])
    if args.mode in ('lora', 'pilot'):
        # The preparer creates the run directory exclusively. Slurm logs are siblings.
        output.parent.mkdir(parents=True, exist_ok=True)
    else:
        output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    print(result.stdout.strip())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
