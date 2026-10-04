#!/usr/bin/env python3
"""Fixed contextual comparisons on existing inputs; run remotely under flock."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import traceback

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.multi_market.features import BASELINE_FEATURES
from src.contextual_lattice.context import build_context
from src.contextual_lattice.evaluation import evaluate_contextual_hypothesis
from src.contextual_lattice.tracking import write_frozen_manifest,append_lifecycle_event

def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,float) and not np.isfinite(value):return None
    if isinstance(value,pd.Timestamp):return value.isoformat()
    return value

def write_json(path,value):
    path.write_text(json.dumps(clean(value),indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')

def prepare(frame, *, futures=False, window=63, source_version='contextual-lattice-v1-20261003'):
    data=frame.copy()
    data['date']=pd.to_datetime(data.date).dt.normalize()
    data['target_mark_change']=pd.to_numeric(data['target'],errors='coerce')
    data['target_units']='prior_risk_scaled_same_contract_points' if futures else 'fractional_adjusted_close_change'
    data['next_date']=pd.to_datetime(data.label_available_at,utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize() if futures else pd.to_datetime(data.label_available_at).dt.normalize()
    if futures:
        data['decision_at']=pd.to_datetime(data.decision_at,utc=True)
        data['feature_available_at']=pd.to_datetime(data.feature_last_session).map(lambda x:pd.Timestamp(x).tz_localize('America/New_York')+pd.Timedelta(hours=9,minutes=36)).dt.tz_convert('UTC')
        data['label_available_at']=pd.to_datetime(data.label_available_at,utc=True)
    else:
        data['decision_at']=(data.date.dt.tz_localize('America/New_York')+pd.Timedelta(hours=16)).dt.tz_convert('UTC')
        data['feature_available_at']=data.decision_at
        data['label_available_at']=(pd.to_datetime(data.label_available_at).dt.tz_localize('America/New_York')+pd.Timedelta(hours=16)).dt.tz_convert('UTC')
    data['historical_abs_return_mean']=np.nan
    for _,indices in data.groupby('ticker',sort=False).groups.items():
        order=data.loc[list(indices)].sort_values('date').index
        series=pd.to_numeric(data.loc[order,'return_1d'],errors='coerce').abs()
        data.loc[order,'historical_abs_return_mean']=series.shift(1).rolling(window,min_periods=window).mean().to_numpy()
    data['source_version']=source_version
    return data

def packet(data,hypothesis,*,equity):
    frame=data.copy()
    frame['context_available_at']=frame.decision_at
    # Context-only quantities come from ordinary own/factor inputs and SEC
    # history. New peer/graph geometry occurs ONLY in challenger interactions.
    raw=pd.to_numeric(frame.return_1d,errors='coerce')-pd.to_numeric(frame.beta,errors='coerce')*pd.to_numeric(frame.market_return,errors='coerce')
    denominator=pd.to_numeric(frame.volatility,errors='coerce').replace(0,np.nan)
    if not equity:
        denominator=pd.to_numeric(frame.own_prior_residual_scale,errors='coerce').replace(0,np.nan)
    frame['own_move_z']=raw/denominator
    frame['own_excursion']=frame.own_move_z.abs().ge(2).astype(float)
    frame['market_shock_event']=frame.price_proxy_event.astype(float)
    frame['graph_stability']=1-pd.to_numeric(frame.edge_turnover,errors='coerce')
    frame['filing_recent']=frame.known_8k.astype('Float64').to_numpy(dtype=float,na_value=np.nan)
    frame['abs_own_move']=frame.own_move_z.abs()
    frame['abs_peer_gap']=frame.peer_reaction_gap.abs()
    frame['abs_peer_shock']=frame.residual_peer_shock.abs()
    base=list(BASELINE_FEATURES)
    qualified=frame.price_context_available.fillna(False).astype(bool)
    if hypothesis=='catchup':
        context=['lagged_market_shock','market_shock_event']
        interactions=['peer_gap_on_market_event','relationship_conditioned_market_shock']
        frame[interactions[0]]=frame.peer_reaction_gap*frame.market_shock_event
        frame[interactions[1]]=frame.prior_peer_stability*frame.lagged_market_shock
        variant='generic_market_price_catchup_proxy'
    elif hypothesis=='reversal':
        context=['own_move_z','own_excursion']
        interactions=['stable_peer_gap','peer_gap_on_own_excursion']
        frame[interactions[0]]=frame.peer_reaction_gap*frame.graph_stability
        frame[interactions[1]]=frame.peer_reaction_gap*frame.own_excursion
        variant='observed_price_gap_reversal_proxy'
        if equity:
            context+=['filing_recent','own_move_with_filing']
            frame['own_move_with_filing']=frame.own_move_z*frame.filing_recent
            frame[interactions[1]]=frame[interactions[1]]*(1-frame.filing_recent)
            qualified &= frame.filing_context_available.fillna(False).astype(bool)
            frame.loc[~frame.filing_context_available,'context_reason']='SEC_population_coverage_unknown'
            variant='conservative_cutoff_SEC_8K_context_reversal'
    else:
        context=['abs_own_move','market_shock_event']
        interactions=['peer_gap_instability','peer_shock_on_market_event']
        frame[interactions[0]]=frame.peer_reaction_gap.abs()*(1-frame.graph_stability)
        frame[interactions[1]]=frame.residual_peer_shock.abs()*frame.market_shock_event
        base+=['historical_abs_return_mean']
        variant='absolute_next_session_mark_movement'
    frame['context_qualified']=qualified
    frame['variant']=variant
    return frame,base,context,interactions,variant

def run(args):
    config=json.loads(args.config.read_text(encoding='utf-8'))
    models=config['models'];uncertainty=config['uncertainty']
    if models['source_shock_threshold_std'] != 2. or models['gap_threshold_std'] != 2.:
        raise ValueError('context adapter supports only registered two-standard-deviation thresholds')
    window=int(models['window_sessions'])
    equity_path=args.prior_root/'results/native-equity-v1/features.parquet'
    future_path=args.prior_root/'results/futures-v1/causal_features_and_labels.csv'
    source_paths={'config':args.config,'equity_features':equity_path,'futures_features':future_path,'SEC_filings':args.sec_context/'filings.csv','SEC_coverage':args.sec_context/'coverage.csv','SEC_receipt':args.sec_context/'receipt.json'}
    for path in sorted((ROOT/'src/contextual_lattice').glob('*.py')):
        source_paths['code/'+path.name]=path
    for path in [ROOT/'src/multi_market/evaluation.py',ROOT/'src/multi_market/features.py',ROOT/'scripts/contextual_lattice/export_sec_context.py',ROOT/'configs/experiments/contextual-lattice-links-v1.json']:
        source_paths[str(path.relative_to(ROOT))]=path
    source_paths['runner']=Path(__file__)
    frozen=dict(config)
    frozen['packet_definition']='context-only: own/factor/SEC inputs; Lattice-only: two unconditioned peer/graph quantities; combined: two fixed peer/context interactions; no new geometry in context-only'
    write_frozen_manifest(args.output,frozen,source_paths)
    reports=[];failed=[];ledgers=[];decisions=[];predictions=[]
    try:
        filings=pd.read_csv(args.sec_context/'filings.csv',dtype=str).fillna('')
        coverage=pd.read_csv(args.sec_context/'coverage.csv',dtype=str).fillna('')
        equity=prepare(pd.read_parquet(equity_path),window=window,source_version=config['experiment_id'])
        futures=prepare(pd.read_csv(future_path),futures=True,window=window,source_version=config['experiment_id'])
        groups={'equities':equity}
        groups.update({root:futures.loc[futures.root.eq(root)].copy().reset_index(drop=True) for root in ['ES','ZN','CL','GC']})
        for group,source in groups.items():
            context=build_context(source,filings=filings if group=='equities' else None,coverage=coverage if group=='equities' else None,window=window)
            context.to_csv(args.output/f'{group}_context_rows.csv',index=False)
            for hypothesis in ['catchup','reversal','movement']:
                trial=f'{group}_{hypothesis}'
                try:
                    rows,base,ctx,interactions,variant=packet(context,hypothesis,equity=group=='equities')
                    lattice_columns=config['lattice_only_columns'][hypothesis]
                    dates=config['equity_dates' if group=='equities' else 'futures_dates']
                    result=evaluate_contextual_hypothesis(rows,hypothesis=hypothesis,baseline_columns=base,context_columns=ctx,interaction_columns=interactions,lattice_columns=lattice_columns,target_column='target_mark_change',train_start=dates['train_start'],holdout_start=dates['diagnostic_start'],holdout_end=dates['diagnostic_end'],ridge=float(models['ridge']),purge_sessions=int(models['purge_sessions']),bootstrap_repetitions=int(uncertainty['bootstrap_repetitions']),block_sessions=int(uncertainty['block_sessions']),seed=int(uncertainty['seed']))
                    result.report.update(market_group=group,variant=variant,trial_id=trial,interpretation='exploratory mark diagnostic; no independent confirmation or net profit claim')
                    result.report['target_units']=config['target_units']['equities' if group=='equities' else 'futures']
                    write_json(args.output/f'{trial}_report.json',result.report)
                    result.predictions.to_csv(args.output/f'{trial}_predictions.csv',index=False)
                    result.decisions.to_csv(args.output/f'{trial}_decisions.csv',index=False)
                    result.ledger.to_csv(args.output/f'{trial}_ledger.csv',index=False)
                    result.decisions['market_group']=group;result.decisions['hypothesis']=hypothesis
                    result.ledger['market_group']=group
                    ledgers.append(result.ledger);decisions.append(result.decisions)
                    reports.append(result.report)
                    predictions.append(result.predictions.assign(market_group=group,hypothesis=hypothesis))
                    if group=='equities' and hypothesis=='movement':
                        adapter=result.decisions[['ticker','date','context_lattice','status']].rename(columns={'date':'decision_date','context_lattice':'predicted_abs_return'})
                        adapter.to_csv(args.output/'equities_movement_option_adapter.csv',index=False)
                    print(json.dumps({'trial':trial,'status':result.report['status'],'cohort':result.report['cohort']}),flush=True)
                except Exception as exc:
                    failure={'trial_id':trial,'stage':'evaluate','reason':f'{type(exc).__name__}: {exc}','traceback':traceback.format_exc()}
                    failed.append(failure);write_json(args.output/f'{trial}_failure.json',failure)
        if ledgers:pd.concat(ledgers,ignore_index=True).to_csv(args.output/'all_candidate_decisions.csv',index=False)
        if decisions:pd.concat(decisions,ignore_index=True).to_csv(args.output/'all_opportunities.csv',index=False)
        if predictions:pd.concat(predictions,ignore_index=True).to_csv(args.output/'all_paired_predictions.csv',index=False)
        full_status=[{'hypothesis':'dated_business_link_public_surprise_catchup','status':'untestable','reason':'qualified historic signed business links, frozen expectations and first-public clocks not supplied; generic price proxy is separately registered'}, {'hypothesis':'complete_news_conditioned_reversal','status':'untestable','reason':'SEC inventory covers SEC 8-Ks only; no complete earnings/news monitoring or first-public proof'}, {'hypothesis':'option_movement_mispricing_and_net_return','status':'deferred_to_options_audit','reason':'underlying movement forecast is not a same-maturity option price comparison'}, {'hypothesis':'net_futures_or_portfolio_hedging','status':'untestable','reason':'costs, account capital, original quote updates and fixed exposure mandate not established'}]
        summary={'status':'completed_exploratory' if not failed else 'completed_with_operational_failures','registered_price_context_cells':15,'completed_reports':len(reports),'operational_failures':failed,'full_hypotheses':full_status,'reports':reports,'new_orders':0,'promotion':False}
        write_json(args.output/'summary.json',summary)
        append_lifecycle_event(args.output,'comparisons_complete',{p.name:p for p in args.output.iterdir() if p.is_file() and p.name not in {'events.jsonl','manifest.json'}},details={'reports':len(reports),'operational_failures':len(failed),'promotion':False})
        return 0 if not failed else 2
    except Exception as exc:
        failure={'stage':'run','reason':f'{type(exc).__name__}: {exc}','traceback':traceback.format_exc()}
        write_json(args.output/'run_failure.json',failure)
        append_lifecycle_event(args.output,'run_failed',{'failure':args.output/'run_failure.json'},details=failure)
        raise

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-root',type=Path,required=True)
    parser.add_argument('--sec-context',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    return run(parser.parse_args(argv))

if __name__=='__main__':raise SystemExit(main())
