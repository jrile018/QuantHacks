#!/usr/bin/env python3
"""Build an immutable, all-opportunity contextual feature audit from local inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.contextual_lattice.context import build_context


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _read_optional(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    if path.suffix.lower() == '.parquet':
        return pd.read_parquet(path)
    if path.suffix.lower() == '.csv':
        try:
            return pd.read_csv(path, dtype={'cik': str})
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    raise ValueError(f'expected .csv or .parquet: {path}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', required=True, type=Path, help='Existing causal feature panel')
    parser.add_argument('--filings', type=Path, help='Offline SEC 8-K inventory CSV/Parquet')
    parser.add_argument('--coverage', type=Path, help='Offline issuer inventory coverage statuses')
    parser.add_argument('--source-shocks', type=Path, help='Dated source-market price shocks with availability')
    parser.add_argument('--links', type=Path, help='Dated signed public economic-link evidence')
    parser.add_argument('--output', required=True, type=Path, help='New output directory')
    parser.add_argument('--window', type=int, default=63, help='Registered 63 sessions; override creates a distinct trial')
    args = parser.parse_args(argv)
    paths = {'features': args.features, 'filings': args.filings, 'coverage': args.coverage,
             'source_shocks': args.source_shocks, 'links': args.links}
    if args.output.exists():
        parser.error('output directory already exists; source artifacts are immutable')
    if not args.features.is_file():
        parser.error('features input does not exist')
    inputs = {name: path for name, path in paths.items() if path is not None}
    missing = [str(path) for path in inputs.values() if not path.is_file()]
    if missing:
        parser.error(f'input files do not exist: {missing}')
    features = pd.read_parquet(args.features)
    context = build_context(features, filings=_read_optional(args.filings),
                            coverage=_read_optional(args.coverage),
                            source_shocks=_read_optional(args.source_shocks),
                            links=_read_optional(args.links), window=args.window)
    if len(context) != len(features) or not context[['date', 'ticker']].equals(features[['date', 'ticker']].assign(date=pd.to_datetime(features.date).dt.normalize())):
        raise AssertionError('adapter changed the daily opportunity index')
    if 'target' in features and not context.target.equals(features.target):
        raise AssertionError('adapter changed target labels')
    manifest = {
        'status': 'price_proxy_exploratory_actual_news_blocked',
        'rows': len(context), 'window': args.window,
        'files_sha256': {name: _sha256(path) for name, path in inputs.items()},
        'context_module_sha256': _sha256(ROOT / 'src/contextual_lattice/context.py'),
        'experiment_config_sha256': _sha256(ROOT / 'configs/experiments/contextual-lattice-links-v1.json'),
        'filing_clock': 'SEC acceptance retained as metadata; known state deferred through filingDate plus one calendar day; first public/receipt unproved',
        'monitoring': 'complete status covers only retrieved SEC 8-K population, not all issuer news',
        'catchup': 'price shock is a market proxy, not a factual news surprise; actual-news transmission remains blocked',
        'futures_units': 'prior normalized residual approximation; volatility is a scale ratio, not equity return standard deviation',
        'counts': {
            'filing_context_available': int(context.filing_context_available.sum()),
            'price_context_available': int(context.price_context_available.sum()),
            'reversal_events': int(context.reversal_event.sum()),
            'catchup_price_proxy_rows': int(context.catchup_eligibility.eq('price_proxy_exploratory').sum()),
        },
    }
    args.output.mkdir(parents=True)
    context.to_parquet(args.output / 'context.parquet', index=False)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output.resolve()), **manifest['counts'], 'rows': len(context)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
