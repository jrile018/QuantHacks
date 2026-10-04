"""Upload the verified pilot through interactive system SCP; credentials stay in its terminal."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{64}', args.expected_sha256):
        raise ValueError('Expected a full bundle SHA256')
    bundle = ROOT / 'data/processed/hipergator/quanthaxs-pilot.tar.gz'
    if hashlib.sha256(bundle.read_bytes()).hexdigest() != args.expected_sha256:
        raise ValueError('Bundle changed; upload aborted before connecting')
    name = 'quanthaxs-pilot-' + args.expected_sha256[:12] + '.tar.gz'
    target = 'kkatiyar@hpg.rc.ufl.edu:/blue/ai-workshop/kkatiyar/' + name
    state_path = bundle.parent / 'upload-status.json'
    state = dict(status='awaiting_transfer', sha256=args.expected_sha256, target=target,
                 started_at_utc=datetime.now(timezone.utc).isoformat())
    state_path.write_text(json.dumps(state, indent=2))
    print('Uploading the verified QuantHaxs pilot to HiPerGator.\nComplete password and Duo prompts in this window.', flush=True)
    try:
        result = subprocess.run(['scp', str(bundle), target], check=False)
        state.update(exit_code=result.returncode, status='uploaded' if result.returncode == 0 else 'failed')
        print('UPLOAD COMPLETE' if result.returncode == 0 else 'UPLOAD FAILED; keep the error visible.', flush=True)
        return result.returncode
    except Exception as error:
        state.update(status='failed', error=str(error))
        raise
    finally:
        state['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        state_path.write_text(json.dumps(state, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
