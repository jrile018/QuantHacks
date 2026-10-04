"""Re-score frozen predictions on their own frozen hedged targets; no fitting.

Each model's basket differs. Its candidate-versus-zero comparison is valid;
cross-model hedged MSE comparisons would not be valid.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.lattice_strategies.evaluation import paired_interval


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = pd.read_csv(args.input, parse_dates=['date'])
    reports = []
    states = ['market_state', 'mst_peer_state', 'topcorr_peer_state', 'distance_peer_state']
    for (model, horizon), group in rows.loc[rows.model.isin(states)].groupby(['model', 'horizon']):
        mask = np.isfinite(group[['forecast', 'outcome', 'hedge_outcome']]).all(axis=1)
        for cohort, selected in [('available_basket', group.loc[mask]),
                                 ('valid_model', group.loc[mask & group.status.eq('ok')])]:
            entry = {'model': model, 'horizon': int(horizon), 'cohort': cohort,
                     'rows': len(selected), 'dates': selected.date.nunique(),
                     'no_trade_rows': int(selected.status.eq('no_trade').sum()),
                     'target_scope': 'same frozen model-specific additive hedge basket, candidate versus zero only',
                     'cross_model_comparison_valid': False, 'model_refits': 0}
            forecast = selected.forecast
            for target in ['outcome', 'hedge_outcome']:
                actual = selected[target]
                candidate, zero = (forecast - actual)**2, actual**2
                date_losses = pd.DataFrame({'candidate': candidate, 'zero': zero, 'date': selected.date}).groupby('date')[['candidate', 'zero']].mean()
                entry[target] = {
                    'candidate_mse': float(candidate.mean()), 'zero_mse': float(zero.mean()),
                    'forecast_mean': float(forecast.mean()), 'target_mean': float(actual.mean()),
                    'mean_forecast_squared': float((forecast**2).mean()),
                    'twice_mean_forecast_times_target': float(2*(forecast*actual).mean()),
                    'loss_difference_decomposition': float((forecast**2).mean()-2*(forecast*actual).mean()),
                    'paired': paired_interval(date_losses, 'candidate', 'zero', repetitions=500, block=20, seed=20261004),
                }
                np.testing.assert_allclose(candidate.mean()-zero.mean(), entry[target]['loss_difference_decomposition'], rtol=1e-9, atol=1e-14)
            reports.append(entry)
    output = {'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
              'input_rows': len(rows), 'model_refits': 0, 'new_price_data': False,
              'study_scope': 'post-result exploratory audit, previously inspected 2024/2025',
              'notes': ['Unadjusted intervals; no cross-model hedged-target ranking.',
                        'Abstentions without an available frozen basket cannot be scored on that basket.',
                        'Forecast MSE does not certify a profitable or executable trade.'], 'comparisons': reports}
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
