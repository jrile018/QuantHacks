"""Run on remote host; source CSVs remain immutable. No data purchases."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.multi_market.futures_study import run_study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', required=True)
    parser.add_argument('--jobs-json', '--jobsJSON', dest='jobs_json', required=True)
    parser.add_argument('--output', required=True, help='New output directory, must not already exist')
    parser.add_argument('--config', default='configs/experiments/multi-market-v1.json')
    args = parser.parse_args()
    result = run_study(args.raw_root, args.jobs_json, args.output, config_path=args.config)
    print(json.dumps({'output': args.output, 'sessions': result['calendar_sessions'],
                      'root_status': {root: report['status'] for root, report in result['roots'].items()},
                      'economic_status': result['economic_roles']['status']}, indent=2))


if __name__ == '__main__':
    main()
