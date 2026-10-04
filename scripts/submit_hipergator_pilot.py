"""Interactively authenticate and submit the already uploaded, hash-verified pilot."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    state_dir = ROOT / 'data/processed/hipergator'
    uploaded = json.loads((state_dir / 'upload-status.json').read_text())
    digest = uploaded['sha256']
    if uploaded['status'] != 'uploaded' or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('A verified successful upload is required')
    directory = 'quanthaxs-pilot-' + digest[:12]
    archive = directory + '.tar.gz'
    remote = '\n'.join([
        'set -e',
        'cd /blue/ai-workshop/kkatiyar',
        "printf '%s\\n' " + shlex.quote(digest + '  ' + archive) + ' | sha256sum -c -',
        'mkdir ' + shlex.quote(directory),
        'tar -xzf ' + shlex.quote(archive) + ' -C ' + shlex.quote(directory),
        'cd ' + shlex.quote(directory),
        'python3 hpc/start_ai_workshop.py',
        'cat deployment-jobs.json',
    ])
    status_path = state_dir / 'submission-status.json'
    status = {'status': 'awaiting_authentication', 'remote_directory': '/blue/ai-workshop/kkatiyar/' + directory,
              'started_at_utc': datetime.now(timezone.utc).isoformat(), 'sha256': digest}
    status_path.write_text(json.dumps(status, indent=2))
    print('Complete password and Duo in this window. The verified pilot will then be submitted to Slurm.', flush=True)
    try:
        result = subprocess.run(['ssh', '-tt', 'kkatiyar@hpg.rc.ufl.edu',
                                 'bash -lc ' + shlex.quote(remote)],
                                stdout=subprocess.PIPE, text=True, check=False)
        (state_dir / 'submission-output.txt').write_text(result.stdout, encoding='utf8')
        print(result.stdout, flush=True)
        status['exit_code'] = result.returncode
        status['status'] = 'submitted_not_completed' if result.returncode == 0 else 'submission_failed'
        # Preserve remote IDs only when the submitted JSON contains valid evidence.
        start = result.stdout.find('{')
        if start >= 0:
            try:
                deployment = json.JSONDecoder().raw_decode(result.stdout[start:])[0]
                for key in ('setup_job_id', 'pilot_job_id'):
                    value = deployment.get(key)
                    if isinstance(value, str) and re.fullmatch('[1-9][0-9]*', value):
                        status[key] = value
            except (ValueError, TypeError):
                pass
        return result.returncode
    except Exception as error:
        status.update(status='submission_failed', error=str(error))
        raise
    finally:
        status['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        status_path.write_text(json.dumps(status, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
