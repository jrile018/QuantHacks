"""Actual-contract sampled futures pilot; never synthetic market prices.

The representation is a 63-session window of observed same-contract point
innovations, standardized separately per root using only that window. It is
computed directly, without manufacturing an equity-price/cumulative series.
All feature windows end at d-1 for the 09:30 decision on d. Labels compare the
front contract selected on d at the fixed d and next-common-session marks.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .evaluation import evaluate_forecasts
from .features import BASELINE_FEATURES, CANDIDATE_FAMILIES, _correlation
from .labels import Quote, executable_price

ROOTS = ('ES', 'ZN', 'CL', 'GC')
TZ = 'America/New_York'
PRICE_UNDEFINED = 9223372036854775807


def _timestamps(values: pd.Series) -> pd.Series:
    """Databento CSV timestamps are integer ns; text ISO is also accepted."""
    numeric = pd.to_numeric(values, errors='coerce')
    if numeric.notna().all():
        return pd.to_datetime(numeric, unit='ns', utc=True)
    return pd.to_datetime(values, utc=True, errors='coerce')


def _mark_time(date) -> pd.Timestamp:
    return pd.Timestamp(date).tz_localize(TZ) + pd.Timedelta(hours=9, minutes=36)


def fixed_interval_rows(chunk: pd.DataFrame) -> pd.DataFrame:
    """Retain only interval-END ts_recv=09:36:00 ET, never a later fallback.

    ts_event is retained as provider provenance, not interpreted as an original
    book-update clock. BBO interval data cannot establish execution freshness.
    """
    required = {'ts_recv', 'instrument_id', 'symbol', 'bid_px_00', 'ask_px_00',
                'bid_sz_00', 'ask_sz_00'}
    if not required.issubset(chunk):
        raise ValueError(f'BBO fields missing: {sorted(required - set(chunk))}')
    received = _timestamps(chunk.ts_recv)
    local = received.dt.tz_convert(TZ)
    selected = local.dt.hour.eq(9) & local.dt.minute.eq(36) & local.dt.second.eq(0) & local.dt.nanosecond.eq(0) & local.dt.microsecond.eq(0)
    rows = chunk.loc[selected].copy()
    rows['mark_at'] = received.loc[selected]
    rows['interval_start'] = rows.mark_at - pd.Timedelta(minutes=1)
    rows['date'] = local.loc[selected].dt.tz_localize(None).dt.normalize()
    for side in ('bid', 'ask'):
        encoded = pd.to_numeric(rows[f'{side}_px_00'], errors='coerce')
        rows[side] = (encoded * 1e-9).where(encoded.abs() < 9e18)
        rows[f'{side}_size'] = pd.to_numeric(rows[f'{side}_sz_00'], errors='coerce')
    rows['midpoint'] = (rows.bid + rows.ask) / 2
    valid, reasons = [], []
    for row in rows.itertuples():
        q = Quote(str(row.instrument_id), row.mark_at.to_pydatetime(), row.mark_at.to_pydatetime(),
                  row.bid, row.ask, row.bid_size, row.ask_size, 'interval_sample')
        buy = executable_price(q, 'buy', 1, q.available_time, 0, allow_sampled_proxy=True)
        sell = executable_price(q, 'sell', 1, q.available_time, 0, allow_sampled_proxy=True)
        valid.append(buy is not None and sell is not None)
        reasons.append('' if valid[-1] else 'invalid_or_insufficient_two_sided_sample')
    rows['valid'] = valid
    rows['quote_missing_reason'] = reasons
    return rows.reset_index(drop=True)


def build_contract_panel(marks: pd.DataFrame, calendar, *, roots=ROOTS) -> pd.DataFrame:
    """Resolve prior/exit from either rank, on exact adjacent common dates."""
    marks = marks.copy()
    marks['date'] = pd.to_datetime(marks.date).dt.normalize()
    dates = pd.DatetimeIndex(pd.to_datetime(calendar)).normalize().sort_values().unique()
    marks = marks[marks.date.isin(dates) & marks.root.isin(roots)]
    if marks.duplicated(['date', 'root', 'rank']).any():
        raise ValueError('ambiguous duplicate root/rank fixed mark')
    # Two rank files may contain the identical actual contract. Conflicting
    # prices are an adapter failure, never an invitation to choose a winner.
    key = ['date', 'root', 'instrument_id', 'contract_id']
    for _, duplicates in marks.groupby(key, dropna=False):
        if len(duplicates) > 1 and (duplicates.midpoint.nunique(dropna=False) > 1 or duplicates.valid.nunique() > 1):
            raise ValueError('conflicting same-contract fixed marks across ranks')
    by_contract = {}
    fronts = {}
    for row in marks.to_dict('records'):
        if row['rank'] == 0:
            fronts[(row['date'], row['root'])] = row
        if row.get('valid', False) and pd.notna(row.get('contract_id')):
            by_contract[(row['date'], row['root'], row['instrument_id'], row['contract_id'])] = row
    result = []
    for i, date in enumerate(dates):
        previous = dates[i - 1] if i else None
        following = dates[i + 1] if i + 1 < len(dates) else None
        for root in roots:
            front = fronts.get((date, root), {})
            identity = (root, front.get('instrument_id'), front.get('contract_id'))
            entry_valid = bool(front.get('valid', False)) and pd.notna(front.get('contract_id'))
            prior = by_contract.get((previous, *identity)) if previous is not None else None
            exit_mark = by_contract.get((following, *identity)) if following is not None else None
            point = front.get('midpoint', np.nan) if entry_valid else np.nan
            missing_entry = ('missing_front_fixed_entry' if not front else
                             'missing_definition_mapping' if pd.isna(front.get('contract_id')) else
                             front.get('quote_missing_reason', 'invalid_front_fixed_entry') or 'invalid_front_fixed_entry')
            label_reason = (missing_entry if not entry_valid else 'no_next_common_session' if following is None else
                            'missing_same_contract_fixed_exit' if exit_mark is None else '')
            innovation_reason = (missing_entry if not entry_valid else 'no_previous_common_session' if previous is None else
                                 'missing_same_contract_previous_mark' if prior is None else '')
            record = dict(date=date, root=root, ticker=root, instrument_id=front.get('instrument_id'),
                          contract_id=front.get('contract_id'), entry_midpoint=point,
                          previous_date=previous, exit_date=following,
                          innovation_points=point - prior['midpoint'] if entry_valid and prior else np.nan,
                          target_points=exit_mark['midpoint'] - point if entry_valid and exit_mark else np.nan,
                          previous_rank=prior.get('rank') if prior else None, exit_rank=exit_mark.get('rank') if exit_mark else None,
                          exit_midpoint=exit_mark['midpoint'] if exit_mark else np.nan,
                          decision_at=pd.Timestamp(date).tz_localize(TZ) + pd.Timedelta(hours=9, minutes=30),
                          mark_at=_mark_time(date), label_available_at=_mark_time(following) if following is not None else pd.NaT,
                          label_missing_reason=label_reason, innovation_missing_reason=innovation_reason)
            for column in ('bid', 'ask', 'bid_size', 'ask_size', 'source_job', 'symbol', 'definition_at'):
                record[column] = front.get(column)
            result.append(record)
    return pd.DataFrame(result)


def build_futures_features(panel: pd.DataFrame, *, window: int = 63,
                           shrinkage: float = .1, edge_threshold: float = .5) -> pd.DataFrame:
    """Feature packet on observed innovations, with strictly prior information.

    Every root's risk scale is sample std of its prior window of point changes.
    Own change, momentum, factor state and target are dimensionless. Volatility
    control is the current prior-window std / previous prior-window std, so a
    change in constant quoting units cannot alter model inputs. Missing windows
    are retained with NaNs and reasons; no bridging or interpolation occurs.
    """
    if window < 3:
        raise ValueError('at least three fixed-window sessions required')
    if panel.duplicated(['date', 'root']).any():
        raise ValueError('duplicate date/root panel')
    changes = panel.pivot(index='date', columns='root', values='innovation_points').reindex(columns=ROOTS).sort_index()
    data = panel[panel.root.isin(ROOTS)].copy()
    data['date'] = pd.to_datetime(data.date)
    by_key = data.set_index(['date', 'root'])
    output = []
    previous_edges = None
    previous_nodes = None
    prior_scale = changes.shift(1).rolling(window, min_periods=window).std()
    for i, date in enumerate(changes.index):
        history = changes.iloc[max(0, i - window):i]
        scales = prior_scale.loc[date]
        eligible = history.columns[history.notna().all() & (scales > 1e-12)] if len(history) == window else []
        normalized = history.loc[:, eligible].div(scales.loc[eligible], axis=1)
        states = {}
        avg_corr = concentration = turnover = np.nan
        if len(eligible) >= 3:
            values = normalized.to_numpy()
            corr = _correlation(values, shrinkage)
            upper = np.triu_indices(len(eligible), 1)
            avg_corr = float(corr[upper].mean())
            edges = np.abs(corr[upper]) >= edge_threshold
            if previous_nodes == tuple(eligible):
                turnover = float(np.mean(edges != previous_edges))
            previous_edges, previous_nodes = edges, tuple(eligible)
            factor = values.mean(axis=1)
            factor_var = float(np.var(factor, ddof=1))
            if factor_var > 1e-12:
                centered_factor = factor - factor.mean()
                beta = (values - values.mean(axis=0)).T @ centered_factor / ((window - 1) * factor_var)
                residual = values - factor[:, None] * beta[None, :]
                residual_scale = residual.std(axis=0, ddof=1)
                if np.all(residual_scale > 1e-12):
                    rcorr = _correlation(residual, shrinkage)
                    concentration = float(np.linalg.eigvalsh(rcorr)[-1] / len(eligible))
                    weights = np.abs(rcorr)
                    np.fill_diagonal(weights, 0)
                    shocks = residual[-1] / residual_scale
                    peer = weights @ shocks / np.maximum(weights.sum(axis=1), 1e-12)
                else:
                    peer = np.full(len(eligible), np.nan)
                for k, root in enumerate(eligible):
                    states[root] = dict(beta=float(beta[k]), market_return=float(factor[-1]),
                                        residual_peer_shock=float(peer[k]))
        else:
            previous_edges, previous_nodes = None, None
        for root in ROOTS:
            if (date, root) not in by_key.index:
                continue
            row = by_key.loc[(date, root)].to_dict()
            row.update(date=date, ticker=root, root=root, feature_last_session=changes.index[i - 1] if i else pd.NaT,
                       risk_scale_points=float(scales[root]), average_correlation=avg_corr,
                       residual_concentration=concentration, edge_turnover=turnover)
            row.update({name: np.nan for name in ['return_1d', 'momentum', 'volatility', 'beta', 'market_return', 'residual_peer_shock']})
            if root in eligible:
                row['return_1d'] = float(normalized[root].iloc[-1])
                row['momentum'] = float(normalized[root].mean())
                previous_scale = prior_scale.iloc[i - 1][root] if i else np.nan
                row['volatility'] = float(scales[root] / previous_scale) if previous_scale > 1e-12 else np.nan
                row.update(states.get(root, {}))
            row['target'] = row['target_points'] / scales[root] if scales[root] > 1e-12 else np.nan
            row['feature_missing_reason'] = '' if root in eligible else 'incomplete_or_constant_prior_innovation_window'
            output.append(row)
    return pd.DataFrame(output).sort_values(['date', 'ticker']).reset_index(drop=True)


@contextmanager
def _csv_stream(path: Path):
    with path.open('rb') as source:
        if path.suffix in {'.zst', '.zstd'}:
            try:
                import zstandard
            except ImportError as error:
                raise RuntimeError('zstandard is required on the remote compute host for CSV.zstd input') from error
            with zstandard.ZstdDecompressor().stream_reader(source) as stream:
                yield stream
        else:
            yield source


def _csv_files(raw_root: Path, job: dict) -> list[Path]:
    identifier = job['id']
    if Path(identifier).name != identifier or identifier in {'.', '..'}:
        raise ValueError('unsafe declared job identifier')
    directory = raw_root / identifier
    files = sorted(p for p in directory.rglob('*') if p.is_file() and
                   (p.name.endswith('.csv') or p.name.endswith('.csv.zst') or p.name.endswith('.csv.zstd')))
    if not files:
        raise FileNotFoundError(f'no declared CSV payload: {identifier}')
    return files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_sampled_marks(raw_root, jobs_json, *, chunk_rows: int = 250_000) -> tuple[pd.DataFrame, pd.DataFrame, list, dict]:
    """Stream only declared purchased job directories; retain a tiny mark panel."""
    raw_root, jobs_json = Path(raw_root), Path(jobs_json)
    jobs = json.loads(jobs_json.read_text(encoding='utf-8'))
    if not isinstance(jobs, list):
        raise ValueError('jobs JSON must be the declared provider job list')
    required = {'GLBX-20261004-HPJ4GHJME5', 'GLBX-20261004-PGTVBDDMSY',
                'GLBX-20261004-4AGNVKMCB3', 'GLBX-20261004-UE5HA8BEA9', 'EQUS-20261004-REQKYD4HUY',
                'EQUS-20261004-QKMVNWHJWT'}
    selected_jobs = {j['id']: j for j in jobs if j['id'] in required}
    if set(selected_jobs) != required:
        raise ValueError(f'missing declared purchased jobs: {sorted(required - set(selected_jobs))}')
    retained, files_manifest = [], []
    for job in selected_jobs.values():
        if job['schema'] != 'bbo-1m':
            continue
        for path in _csv_files(raw_root, job):
            count = kept = 0
            with _csv_stream(path) as stream:
                for chunk in pd.read_csv(stream, chunksize=chunk_rows):
                    count += len(chunk)
                    marks = fixed_interval_rows(chunk)
                    if job['dataset'] == 'GLBX.MDP3':
                        parsed = marks.symbol.str.extract(r'^(ES|MES|ZN|CL|GC)\.v\.([01])$')
                        marks['root'], marks['rank'] = parsed[0], pd.to_numeric(parsed[1], errors='coerce')
                        allowed = set(job['symbols'].split(','))
                        if not marks.symbol.isin(allowed).all():
                            raise ValueError('BBO symbol absent from declared requested aliases')
                    else:
                        marks = marks[marks.symbol.eq('SPY')].copy()
                        marks['root'], marks['rank'] = 'SPY', 0
                    marks['source_job'] = job['id']
                    kept += len(marks)
                    retained.append(marks)
            files_manifest.append(dict(job=job['id'], schema=job['schema'], path=str(path),
                                       sha256=_sha256(path), bytes=path.stat().st_size, rows=count, retained_fixed_marks=kept))
    all_marks = pd.concat(retained, ignore_index=True)
    spy = all_marks[all_marks.root.eq('SPY')].copy()
    if spy.duplicated('date').any():
        raise ValueError('ambiguous SPY fixed sample dates')
    # Independent observed session dates: a missing interval must not silently
    # change the next-session exit. Daily OHLCV timestamps are UTC bar dates;
    # converting midnight UTC into New York would create a preceding-date bug.
    daily_job = selected_jobs['EQUS-20261004-QKMVNWHJWT']
    daily_dates = []
    for path in _csv_files(raw_root, daily_job):
        count = kept = 0
        with _csv_stream(path) as stream:
            for chunk in pd.read_csv(stream, chunksize=chunk_rows):
                count += len(chunk)
                if not {'symbol', 'ts_event'}.issubset(chunk):
                    raise ValueError('SPY daily calendar requires symbol and ts_event')
                sampled = chunk[chunk.symbol.eq('SPY')]
                dates = _timestamps(sampled.ts_event).dt.tz_localize(None).dt.normalize()
                if dates.isna().any():
                    raise ValueError('invalid SPY daily calendar timestamp')
                daily_dates.extend(dates.tolist())
                kept += len(sampled)
        files_manifest.append(dict(job=daily_job['id'], schema=daily_job['schema'], path=str(path),
                                   sha256=_sha256(path), bytes=path.stat().st_size, rows=count, retained_SPY_calendar_rows=kept))
    if pd.Index(daily_dates).duplicated().any():
        raise ValueError('ambiguous duplicate SPY daily calendar dates')
    calendar = sorted(daily_dates)
    if not calendar:
        raise ValueError('no observed SPY daily sessions for common calendar')
    spy_by_date = spy.set_index('date')
    spy_audit = []
    for date in calendar:
        available = date in spy_by_date.index
        quote = spy_by_date.loc[date] if available else None
        spy_audit.append(dict(date=date, valid_fixed_sample=bool(quote.valid) if available else False,
            instrument_id=int(quote.instrument_id) if available else None,
            missing_reason=('missing_SPY_fixed_interval' if not available else
                            quote.quote_missing_reason if not quote.valid else '')))
    futures = all_marks[~all_marks.root.eq('SPY')].copy()
    needed_ids = set(futures.instrument_id.dropna().astype(int))
    definitions = []
    for job in selected_jobs.values():
        if job['schema'] != 'definition':
            continue
        for path in _csv_files(raw_root, job):
            count = kept = 0
            with _csv_stream(path) as stream:
                for chunk in pd.read_csv(stream, chunksize=chunk_rows, low_memory=False):
                    count += len(chunk)
                    if not {'instrument_id', 'raw_symbol', 'ts_recv'}.issubset(chunk):
                        raise ValueError('definition requires instrument_id/raw_symbol/ts_recv')
                    chunk = chunk[chunk.instrument_id.isin(needed_ids)].copy()
                    chunk['definition_at'] = _timestamps(chunk.ts_recv)
                    chunk['source_job'] = job['id']
                    kept += len(chunk)
                    definitions.append(chunk.drop_duplicates(['instrument_id', 'raw_symbol', 'definition_at']))
            files_manifest.append(dict(job=job['id'], schema=job['schema'], path=str(path),
                                       sha256=_sha256(path), bytes=path.stat().st_size, rows=count, retained_definition_rows=kept))
    definition = pd.concat(definitions, ignore_index=True).drop_duplicates(['instrument_id', 'raw_symbol', 'definition_at'])
    if definition.groupby(['instrument_id', 'definition_at']).raw_symbol.nunique().gt(1).any():
        raise ValueError('conflicting actual-contract definitions at same timestamp')
    # Identity only from the most recent definition already available at mark.
    futures['contract_id'] = pd.Series(None, index=futures.index, dtype=object)
    futures['definition_at'] = pd.Series(pd.NaT, index=futures.index, dtype='datetime64[ns, UTC]')
    mappings = {int(identifier): group.sort_values('definition_at') for identifier, group in definition.groupby('instrument_id')}
    for idx, mark in futures.iterrows():
        candidates = mappings.get(int(mark.instrument_id))
        if candidates is not None:
            known = candidates[candidates.definition_at <= mark.mark_at]
            if len(known):
                selected = known.iloc[-1]
                futures.loc[idx, 'contract_id'] = selected.raw_symbol
                futures.loc[idx, 'definition_at'] = selected.definition_at
    manifest = dict(jobs_json=str(jobs_json), jobs_json_sha256=_sha256(jobs_json), input_files=files_manifest,
                    jobs_used=sorted(required), calendar='observed SPY EQUS.MINI ohlcv-1d UTC bar dates, independent of fixed-interval quote availability',
                    spy_fixed_interval_audit=spy_audit,
                    quote_gate='both sides displayed size >=1 and finite noncrossed quote; interval proxy only')
    return futures.reset_index(drop=True), definition, calendar, manifest


def run_study(raw_root, jobs_json, output, *, config_path='configs/experiments/multi-market-v1.json') -> dict:
    """Write new outputs; never mutate raw data, provider metadata or config."""
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    if config['numeric_packet']['window_sessions'] != 63:
        raise ValueError('this registered study requires frozen 63-session window')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    marks, definition, calendar, provenance = load_sampled_marks(raw_root, jobs_json)
    panel = build_contract_panel(marks, calendar)
    features = build_futures_features(panel, window=63)
    marks.to_csv(output / 'fixed_interval_marks.csv', index=False)
    definition.to_csv(output / 'retained_actual_contract_definitions.csv', index=False)
    panel.to_csv(output / 'contract_panel_with_missing_reasons.csv', index=False)
    features.to_csv(output / 'causal_features_and_labels.csv', index=False)
    pd.DataFrame(provenance['spy_fixed_interval_audit']).to_csv(output / 'SPY_fixed_interval_calendar_audit.csv', index=False)
    summary = dict(experiment_id=config['experiment_id'], protocol='frozen_63_prior_sessions_train_2024_test_2025',
                   contract_selection='frozen provider .v.0 previous-day trading-volume rank; actual daily instrument identity required',
                   contract_selection_source='https://databento.com/docs/standards-and-conventions/symbology',
                   causal_scope='features use strictly prior observations; historical vintage of retrieved mappings and holiday zero-volume mapping behavior require a separate audit',
                   representation='direct observed same-contract point-innovation window, unit-standardized per root; no fabricated prices',
                   feature_cutoff='all observations through previous common session fixed mark; 09:30 ET decision',
                   target='selected rank0 actual contract entry midpoint to exact next-common-session same-contract midpoint / prior-window point std',
                   target_units='dimensionless_prior_risk_units', volatility_control='prior-window point std / one-session-earlier prior-window point std',
                   calendar_sessions=len(calendar), provenance=provenance, roots={},
                   economic_roles={'status': 'blocked', 'reason': 'account, fees, capacity, lifecycle and execution gates absent; interval prices are uncosted proxies'},
                   limitations=['2025 is a frozen exploratory temporal holdout, not independent confirmation',
                                'observed SPY daily calendar is independent of missing interval quotes but is not a complete historical exchange/PIT calendar audit',
                                'continuous mapping uses provider previous-day trading volume policy; retrieval vintage and holiday zero-volume resets are not independently reconstructed',
                                'rank0/rank1 coverage cannot repair a same-contract observation absent from both ranks',
                                'interval last-BBO samples cannot establish original book freshness, simultaneity or actual fills',
                                'training label availability and one-session purge enforced by evaluation API',
                                'no product multiplier guessed; cash/account returns not calculated'])
    for root in ROOTS:
        rows = features[features.ticker.eq(root)]
        result = evaluate_forecasts(rows, baseline=BASELINE_FEATURES, candidates=CANDIDATE_FAMILIES,
                                    train_start='2024-01-01', holdout_start='2025-01-01', holdout_end='2025-12-31',
                                    ridge=1., purge_sessions=1, bootstrap_repetitions=500, block_sessions=10, seed=20261003)
        report = result.report
        report['evidence'] = 'actual-contract fixed sampled futures midpoint point changes with exact definition mappings'
        report['limitations'] = summary['limitations'] + ['dependence bootstrap block assumption unvalidated; no significance or promotion claim']
        proxy_roles = report.pop('roles')
        # API returns equity-oriented generic role wording; retain its numerical
        # diagnostics but identify their true normalized futures units here.
        for item in proxy_roles['direct_signal']['proxy_metrics'].values():
            item['units'] = 'dimensionless_prior_risk_units; uncosted same-contract interval midpoint change'
        report['uncosted_normalized_pricing_diagnostics'] = {name: proxy_roles[name] for name in ('risk_filter', 'direct_signal')}
        report['economic_roles'] = summary['economic_roles']
        report['missing_labels'] = rows.label_missing_reason.value_counts().to_dict()
        report['missing_innovations'] = rows.innovation_missing_reason.value_counts().to_dict()
        report['contract_coverage'] = dict(common_sessions=len(rows), valid_exact_contract_labels=int(rows.target_points.notna().sum()),
             rank1_previous_mark_recoveries=int(rows.previous_rank.eq(1).sum()),
             rank1_fixed_exit_recoveries=int(rows.exit_rank.eq(1).sum()),
             observed_front_contract_changes=int((rows.contract_id.notna() & rows.contract_id.shift().notna() & rows.contract_id.ne(rows.contract_id.shift())).sum()))
        result.predictions.to_csv(output / f'{root}_paired_predictions.csv', index=False)
        summary['roots'][root] = report
    # MES is a matched implementation diagnostic of the index exposure, never
    # an additional independent forecasting cell or feature node.
    mes = build_contract_panel(marks, calendar, roots=('MES',))
    mes.to_csv(output / 'MES_implementation_diagnostic_panel.csv', index=False)
    summary['MES_implementation_diagnostic'] = dict(independent_alpha_cell=False,
             sessions=len(mes), valid_same_contract_labels=int(mes.target_points.notna().sum()),
             missing_labels=mes.label_missing_reason.value_counts().to_dict(), economic_status='blocked')
    (output / 'study_report.json').write_text(json.dumps(summary, indent=2, default=str, allow_nan=False), encoding='utf-8')
    return summary
