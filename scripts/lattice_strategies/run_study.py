#!/usr/bin/env python3
"""Frozen residual-state and fixed-book risk diagnostics on existing prices."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import traceback
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.contextual_lattice.tracking import write_frozen_manifest, append_lifecycle_event
from src.multi_market.features import price_changes
from src.lattice_strategies.residuals import build_residual_forecasts, MODELS
from src.lattice_strategies.risk import build_risk_forecasts, ESTIMATORS, POLICIES
from src.lattice_strategies.evaluation import summarize_forecasts, summarize_risk, residual_cost_sensitivity


def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [clean(v) for v in value]
    if isinstance(value, np.generic): return clean(value.item())
    if value is pd.NaT or value is pd.NA: return None
    if isinstance(value, pd.Timestamp): return value.isoformat()
    if isinstance(value, float) and not np.isfinite(value): return None
    return value


def write_json(path, value):
    path.write_text(json.dumps(clean(value), indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def run(args):
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if config['residual']['models'] != list(MODELS) or config['risk']['estimators'] != list(ESTIMATORS) or config['risk']['policies'] != list(POLICIES):
        raise ValueError('registered models differ from implemented models')
    config['runtime_before_fit'] = {'python': platform.python_version(),
        'packages': {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'pyarrow', 'scipy', 'scikit-learn', 'pytest']}}
    sources = {'prices': args.prices, 'config': args.config, 'runtime_lock': args.environment, 'runner': Path(__file__)}
    for name in ['graph.cpp', 'distance.cpp']:
        if not (ROOT/'source_reference'/name).is_file():
            raise ValueError('native graph source reference missing: ' + name)
    for directory in ['src/lattice_strategies', 'source_reference']:
        for path in sorted((ROOT / directory).glob('*')):
            if path.is_file(): sources[str(path.relative_to(ROOT))] = path
    for path in [ROOT/'src/contextual_lattice/tracking.py', ROOT/'src/multi_market/features.py']:
        sources[str(path.relative_to(ROOT))] = path
    for path in sorted((ROOT/'tests').glob('test_lattice*.py')):
        sources[str(path.relative_to(ROOT))] = path
    write_frozen_manifest(args.output, config, sources)
    try:
        # Scan/filter on home-pc under the shared lock; never ingest the full
        # native dataset on the laptop. Source dates are YYYY-MM-DD strings.
        table = pq.read_table(args.prices, columns=['ticker', 'date', 'adjclose'],
            filters=[('ticker', 'in', config['universe']), ('date', '>=', config['input_start']),
                     ('date', '<=', config['label_end'])])
        prices = table.to_pandas()
        prices['date'] = pd.to_datetime(prices.date)
        if set(prices.ticker.unique()) != set(config['universe']):
            raise ValueError('registered universe missing from source')
        changed = price_changes(prices)
        returns = changed.pivot(index='date', columns='ticker', values='price_change').sort_index().sort_index(axis=1)
        metadata = {'source_schema': str(pq.read_schema(args.prices)), 'filtered_price_rows': len(prices),
            'return_sessions': len(returns), 'universe': list(returns.columns),
            'input_first': returns.index.min(), 'input_last': returns.index.max(),
            'missing_return_cells': int(returns.isna().sum().sum()),
            'provenance': 'native Yahoo adjusted-close snapshot, historical identity/adjustment/receipt vintages unqualified',
            'clock': config['clock'], 'calendar': 'union of native screened price sessions; exchange-completeness unverified'}
        write_json(args.output/'input_audit.json', metadata)
        append_lifecycle_event(args.output, 'inputs_loaded', {'input_audit': args.output/'input_audit.json'})
        print('INPUTS_LOADED', json.dumps(clean(metadata)), flush=True)
        residual = config['residual']
        forecasts = build_residual_forecasts(returns, diagnostic_start=config['diagnostic_start'],
            diagnostic_end=config['diagnostic_end'], formation=residual['formation_sessions'],
            calibration=residual['calibration_sessions'], horizons=(1, *config['secondary_horizons_sessions']),
            max_tau=residual['max_characteristic_reversion_sessions'])
        uncertainty = config['uncertainty']
        scoring = dict(repetitions=uncertainty['bootstrap_repetitions'], block=uncertainty['primary_block_sessions'], seed=uncertainty['seed'])
        forecast_report = summarize_forecasts(forecasts, **scoring)
        serialized = forecasts.copy()
        serialized['hedge_weights'] = serialized.hedge_weights.map(lambda value: json.dumps(clean(value), sort_keys=True))
        serialized['peer_tickers'] = serialized.peer_tickers.map(lambda value: json.dumps(clean(value)))
        serialized.to_csv(args.output/'residual_forecasts.csv.gz', index=False)
        write_json(args.output/'residual_report.json', forecast_report)
        print('RESIDUAL_COMPLETE', len(forecasts), flush=True)
        cost_rows = residual_cost_sensitivity(forecasts, config['cost_scenarios_one_way_bps'])
        cost_rows.to_csv(args.output/'residual_cost_scenarios.csv.gz', index=False)
        cost_report = []
        for (model, bps), group in cost_rows.groupby(['model', 'cost_bps']):
            valid = group.loc[np.isfinite(group.net_mark_proxy)]
            cost_report.append({'model': model, 'cost_bps': bps, 'marked_opportunities': len(valid),
                'active_marks': int(valid.status.eq('mark_proxy').sum()), 'no_trades': int(valid.status.eq('no_trade').sum()),
                'mean_net_mark_proxy_per_opportunity': float(valid.net_mark_proxy.mean()),
                'mean_gross_mark_proxy_per_opportunity': float(valid.gross_mark_return.mean()),
                'scope': 'independent one-session gross-normalized baskets, assumed roundtrip costs, no fill/account claim'})
        write_json(args.output/'residual_cost_report.json', cost_report)
        risks, allocations = build_risk_forecasts(returns, diagnostic_start=config['diagnostic_start'],
            diagnostic_end=config['diagnostic_end'], window=config['risk']['window_sessions'],
            max_weight=config['risk']['max_weight'], cost_bps=tuple(config['cost_scenarios_one_way_bps']))
        risks.to_csv(args.output/'risk_forecasts.csv.gz', index=False)
        allocations.to_csv(args.output/'allocation_cost_scenarios.csv.gz', index=False)
        risk_report = summarize_risk(risks, allocations, **scoring)
        write_json(args.output/'risk_report.json', risk_report)
        print('RISK_COMPLETE', len(risks), len(allocations), flush=True)
        date = forecasts.date.min()
        fixture_rows = forecasts.loc[forecasts.date.eq(date) & forecasts.ticker.isin(['AAPL', 'AMZN', 'BAC']) & forecasts.horizon.eq(1)]
        write_json(args.output/'component_fixture.json', {
            'protocol': config['experiment_id'], 'status': 'ready_for_consumer_diagnostic_audit',
            'forecast_unit': 'fractional_adjusted_close_return', 'risk_unit': 'fractional_return_squared_per_session',
            'horizon_sessions': 1, 'decision_clock': config['clock'], 'promotion': False,
            'identity_at_decision': None, 'actual_received_at': None, 'adjustment_vintage': None,
            'execution': None, 'costs': 'assumed_scenarios_only',
            'stock_candidates': fixture_rows.to_dict(orient='records'),
            'fixed_book_risk': risks.loc[risks.date.eq(date)].to_dict(orient='records')})
        summary = {'status': 'completed_exploratory', 'promotion': False, 'new_orders': 0,
            'forecast_rows': len(forecasts), 'risk_rows': len(risks), 'allocation_scenario_rows': len(allocations),
            'forecasts': forecast_report, 'risk': risk_report, 'deferred': config['deferred'],
            'interpretation': 'Previously inspected outcomes, assumed replay clocks and costs; no executable profit proof.'}
        write_json(args.output/'summary.json', summary)
        append_lifecycle_event(args.output, 'study_complete', {p.name: p for p in args.output.iterdir()
            if p.is_file() and p.name not in ['manifest.json', 'events.jsonl']}, details={'promotion': False, 'new_orders': 0})
        return 0
    except Exception as exc:
        write_json(args.output/'failure.json', {'error': f'{type(exc).__name__}: {exc}', 'traceback': traceback.format_exc()})
        append_lifecycle_event(args.output, 'run_failed', {'failure': args.output/'failure.json'})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prices', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--environment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
