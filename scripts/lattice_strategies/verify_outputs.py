#!/usr/bin/env python3
"""Independent hashes/target/accounting audit; no new model fit."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.contextual_lattice.tracking import append_lifecycle_event, file_sha256


def main():
    out = ROOT/'results/strategies-v1'
    manifest = json.loads((out/'manifest.json').read_text())
    events = [json.loads(line) for line in (out/'events.jsonl').read_text().splitlines()]
    for event in events:
        body = {k: v for k, v in event.items() if k != 'event_sha256'}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str, allow_nan=False).encode()).hexdigest()
        assert digest == event['event_sha256']
    for prior, event in zip(events, events[1:]):
        assert event['previous_event_sha256'] == prior['event_sha256']
    source_count = 0
    for source in manifest['sources'].values():
        assert file_sha256(source['path']) == source['sha256']
        source_count += 1
    outputs = events[-1]['outputs']
    for output in outputs.values():
        assert file_sha256(output['path']) == output['sha256']
    cfg = manifest['config']
    frame = pq.read_table(manifest['sources']['prices']['path'], columns=['ticker','date','adjclose'],
        filters=[('ticker','in',cfg['universe']), ('date','>=',cfg['input_start']), ('date','<=',cfg['label_end'])]).to_pandas()
    frame['date'] = pd.to_datetime(frame.date)
    prices = frame.pivot(index='date', columns='ticker', values='adjclose').sort_index().sort_index(axis=1)
    changes = prices / prices.shift(1) - 1
    changes = changes.where(prices.gt(0) & prices.shift(1).gt(0))
    forecast = pd.read_csv(out/'residual_forecasts.csv.gz', parse_dates=['date','formation_cutoff','calibration_cutoff'])
    keys = ['date','ticker','horizon']
    unique = forecast.drop_duplicates(keys)
    checks = 0
    for horizon, group in unique.groupby('horizon'):
        target = sum(changes.shift(-step) for step in range(1, int(horizon)+1))
        expected = target.reset_index().melt(id_vars='date', var_name='ticker', value_name='expected')
        actual = group.merge(expected, on=['date','ticker'], validate='one_to_one')
        assert np.allclose(actual.outcome, actual.expected, equal_nan=True, atol=1e-12)
        checks += len(actual)
    assert (forecast.formation_cutoff.dropna() < forecast.loc[forecast.formation_cutoff.notna(),'date']).all()
    assert (forecast.calibration_cutoff == forecast.date).all()
    risk = pd.read_csv(out/'risk_forecasts.csv.gz', parse_dates=['date'])
    realized = (changes.mean(axis=1, skipna=False).shift(-1))**2
    reconstructed = risk.date.map(realized)
    assert np.allclose(risk.observed_squared_return, reconstructed, equal_nan=True, atol=1e-12)
    allocations = pd.read_csv(out/'allocation_cost_scenarios.csv.gz')
    for row in allocations.loc[allocations.status.eq('marked')].itertuples():
        fees = row.initial_cost + row.rebalance_cost + row.terminal_cost
        assert abs(row.net_proxy_return - (row.mark_return - fees)) < 1e-12
        weights = json.loads(row.weights_json)
        assert abs(sum(weights.values()) - 1.) < 1e-7 and min(weights.values()) >= -1e-8
    receipt = {'status':'verified', 'model_refits':0, 'sources_verified':source_count,
        'outputs_verified':len(outputs), 'distinct_path_targets_reconstructed':checks,
        'risk_targets_reconstructed':len(risk), 'allocation_fee_weight_checks':int(allocations.status.eq('marked').sum()),
        'output_hashes':{name: value['sha256'] for name,value in outputs.items()},
        'manifest_sha256':file_sha256(out/'manifest.json'), 'auditor_sha256':file_sha256(Path(__file__))}
    (out/'verification.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    append_lifecycle_event(out,'outputs_verified',{'verification':out/'verification.json'}, details={'refits':0})
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
