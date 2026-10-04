#!/usr/bin/env python3
"""Bounded real-Parquet exploratory study. Large runs belong in remote tmux.

No data acquisition, synthetic fallback, parameter search or executable-alpha
claim. Fixed dates and source provenance are saved before the numerical fit.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.multi_market.features import BASELINE_FEATURES, CANDIDATE_FAMILIES, build_features
from src.multi_market.evaluation import evaluate_forecasts

DEFAULT_TICKERS = 'AAPL,MSFT,AMZN,GOOGL,META,NVDA,JPM,BAC,XOM,CVX,UNH,GD'


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prices', type=Path, required=True, help='Actual native prices.parquet')
    parser.add_argument('--output', type=Path, required=True, help='New run directory; must not exist')
    parser.add_argument('--tickers', default=DEFAULT_TICKERS, help='Frozen comma-separated target cohort')
    parser.add_argument('--benchmark', default='SPY', help='Audited symbol or explicitly registered __equal_weight_panel__')
    parser.add_argument('--start', required=True, type=date.fromisoformat, help='Input start incl. warmup')
    parser.add_argument('--end', required=True, type=date.fromisoformat, help='Input end incl. next-session labels')
    parser.add_argument('--train-start', type=date.fromisoformat)
    parser.add_argument('--holdout-start', required=True, type=date.fromisoformat)
    parser.add_argument('--holdout-end', required=True, type=date.fromisoformat)
    parser.add_argument('--window', type=int, default=63, help='Fixed registered lookback; changing it is a new trial')
    parser.add_argument('--bootstrap-repetitions', type=int, default=500)
    parser.add_argument('--block-sessions', type=int, default=10)
    parser.add_argument('--seed', type=int, default=20261003)
    parser.add_argument('--source-note', default='Previously inspected native equity panel; historical eligibility and adjustment vintages unaudited')
    args = parser.parse_args(argv)
    if not args.start <= args.holdout_start <= args.holdout_end < args.end:
        parser.error('require start <= holdout-start <= holdout-end < end (end includes target label session)')
    if args.window < 3 or args.bootstrap_repetitions < 1 or args.block_sessions < 1:
        parser.error('invalid fixed window/bootstrap values')
    targets = sorted(set(t.strip() for t in args.tickers.split(',') if t.strip()))
    if not targets or len(targets) > 20:
        parser.error('one to twenty predefined target tickers required')
    universe = sorted(set(targets + ([] if args.benchmark == '__equal_weight_panel__' else [args.benchmark])))
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'exploratory_previously_inspected_data', 'source_path': str(args.prices.resolve()),
        'source_note': args.source_note, 'tickers': targets, 'benchmark': args.benchmark,
        'input_start': str(args.start), 'input_end': str(args.end),
        'train_start': str(args.train_start or args.start),
        'holdout_start': str(args.holdout_start), 'holdout_end': str(args.holdout_end),
        'feature_version': 'causal_panel_v1', 'window': args.window, 'shrinkage': .1,
        'edge_threshold': .5, 'ridge': 1., 'purge_sessions': 1,
        'baseline_features': BASELINE_FEATURES, 'candidate_families': CANDIDATE_FAMILIES,
        'bootstrap_repetitions': args.bootstrap_repetitions, 'block_sessions': args.block_sessions,
        'seed': args.seed, 'role_classification': 'forecast and mark diagnostics only; economic roles blocked',
        'clock': 'session close mark proxy, target next available panel session; no historical receipt assertion',
        'files_sha256': {str(p.relative_to(ROOT)): _hash(p) for p in [
            ROOT / 'src/multi_market/features.py', ROOT / 'src/multi_market/evaluation.py', Path(__file__).resolve()]},
        'prior_trials': 'Existing H1 failed and other inspected research retained; this file is not the entire multiplicity ledger',
    }
    _write_json(args.output / 'protocol.json', protocol)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        schema = pq.read_schema(args.prices)
        price_col = 'adjclose' if 'adjclose' in schema.names else 'close'
        columns = ['date', 'ticker', price_col]
        for optional in ['asset_class', 'contract_id', 'available_at', 'decision_at']:
            if optional in schema.names:
                columns.append(optional)
        if 'asset_class' in columns and 'close' not in columns and 'close' in schema.names:
            columns.append('close')
        date_type = schema.field('date').type
        if pa.types.is_timestamp(date_type):
            first, last = pd.Timestamp(args.start).to_pydatetime(), pd.Timestamp(args.end).to_pydatetime()
        elif pa.types.is_date(date_type):
            first, last = args.start, args.end
        else:
            first, last = str(args.start), str(args.end)
        prices = pd.read_parquet(args.prices, columns=columns,
            filters=[('ticker', 'in', universe), ('date', '>=', first), ('date', '<=', last)])
        present = set(prices.ticker)
        absent = sorted(set(universe) - present)
        if absent:
            raise ValueError(f'frozen instruments absent; no replacement allowed: {absent}')
        protocol['source_sha256'] = _hash(args.prices)
        protocol['source_schema'] = str(schema)
        protocol['observed_input_rows'] = len(prices)
        protocol['observed_input_first_date'] = str(prices.date.min())
        protocol['observed_input_last_date'] = str(prices.date.max())
        features = build_features(prices, benchmark=args.benchmark, window=args.window)
        features = features[features.ticker.isin(targets)].reset_index(drop=True)
        result = evaluate_forecasts(features, baseline=BASELINE_FEATURES,
            candidates=CANDIDATE_FAMILIES, train_start=args.train_start or args.start,
            holdout_start=args.holdout_start, holdout_end=args.holdout_end,
            bootstrap_repetitions=args.bootstrap_repetitions,
            block_sessions=args.block_sessions, seed=args.seed)
        result.report['input_provenance'] = protocol
        _write_json(args.output / 'protocol.json', protocol)
        _write_json(args.output / 'report.json', result.report)
        with (args.output / 'trials.jsonl').open('w', encoding='utf-8') as stream:
            for trial in result.report['trials']:
                stream.write(json.dumps(trial, sort_keys=True, allow_nan=False) + '\n')
        _write_json(args.output / 'failures.json', result.report['failures'])
        result.predictions.to_csv(args.output / 'predictions.csv', index=False)
        features.to_parquet(args.output / 'features.parquet', index=False)
        summary = {'status': result.report['status'], 'input_rows': len(prices),
                   'paired_holdout_rows': result.report['cohort']['paired_holdout_rows'],
                   'output': str(args.output.resolve()),
                   'economic_roles': 'blocked; uncosted pricing proxy only',
                   'relative_mse_reductions': {k: v['relative_mse_reduction']
                       for k, v in result.report['paired_comparisons'].items()}}
        print(json.dumps(summary, sort_keys=True, allow_nan=False))
        return 0 if result.report['status'] != 'blocked' else 2
    except Exception as error:
        failure = {'status': 'failed', 'exception': type(error).__name__, 'reason': str(error)}
        _write_json(args.output / 'failures.json', [failure])
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
