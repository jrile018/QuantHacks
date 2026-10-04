"""Offline streaming qualification of explicitly selected, already-delivered files."""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from src.reit_market_qualification import FROZEN_RULE_SHA256, INTERVAL_REPLAY_ASSUMPTION, run_qualification


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--config', type=Path, required=True,
        help='Explicit jobs/files JSON with compressed raw paths, sizes and SHA256s')
    result.add_argument('--quality-rule', type=Path, required=True)
    result.add_argument('--quality-rule-sha256', default=FROZEN_RULE_SHA256)
    result.add_argument('--output', type=Path, required=True, help='Fresh directory; existing directories are refused')
    result.add_argument('--sample-limit', type=int, default=128)
    result.add_argument('--candidate-symbol', default='AMT')
    result.add_argument('--interval-replay-assumption', action='store_true',
        help='Explicitly assume endpoint availability for diagnostic replay; observed market clocks stay unknown')
    result.add_argument('--cost-evidence', type=Path, help='Optional reviewed dated source evidence; missing costs remain unknown')
    selection = result.add_mutually_exclusive_group()
    selection.add_argument('--quote-month', default='202401', help='Frozen derivative month; equity/definitions remain full selection')
    selection.add_argument('--all-derivative-months', action='store_true', help='Explicitly scan all supplied derivative quote files')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    raw_rule = args.quality_rule.read_bytes()
    digest = hashlib.sha256(raw_rule).hexdigest()
    if digest != args.quality_rule_sha256 or digest != FROZEN_RULE_SHA256:
        raise ValueError('frozen_quality_rule_file_hash_mismatch')
    rule = json.loads(raw_rule)
    if len(set(rule['union_dates'])) != 21:
        raise ValueError('frozen_quality_rule_requires_21_union_dates')
    config_bytes = args.config.read_bytes()
    config = json.loads(config_bytes)
    config.update(quality_rule_file_sha256=digest,
                  source_config_file_sha256=hashlib.sha256(config_bytes).hexdigest())
    costs = json.loads(args.cost_evidence.read_bytes()) if args.cost_evidence else {}
    report = run_qualification(config, rule, args.output, sample_limit=args.sample_limit,
        quote_month=None if args.all_derivative_months else args.quote_month,
        candidate_symbol=args.candidate_symbol, costs=costs,
        interval_replay_assumption=INTERVAL_REPLAY_ASSUMPTION if args.interval_replay_assumption else None)
    print(json.dumps({'status': report['status'], 'candidate_count': report['candidate_count'],
        'consumer_accepted': False, 'arbitrage_claim': False, 'output': str(args.output)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
