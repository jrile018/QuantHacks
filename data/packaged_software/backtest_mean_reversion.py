"""Nested chronological walk-forward equity mean reversion. No live orders.

Training selects companies/pairs, validation chooses one of three entry thresholds,
and each six-month test freezes those choices. All variants and cash folds retained.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from statsmodels.tsa.stattools import coint

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'data/packaged_software/extracts'
if not (BASE/'prices/daily_bars.csv').exists():BASE=ROOT/'data/extracts'
OUT=ROOT/'data/processed/mean_reversion'
SEED=1682022
MAX_HOLD=42
ENTRY_GRID=(1.5,2.0,2.5)
VARIANTS=('correlated_pairs','cointegrated_pairs','fundamental_pairs','sector_reversal','profitable_long_weak_short')


def bh(p):
    p=np.asarray(p);order=np.argsort(p);result=np.empty(len(p))
    result[order]=np.minimum(1,np.minimum.accumulate((p[order]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1])
    return result


def fit_pair(a,b,values):
    logs=np.log(values[[a,b]].dropna().to_numpy())
    coef=np.linalg.lstsq(np.column_stack([np.ones(len(logs)),logs[:,1]]),logs[:,0],rcond=None)[0]
    spread=logs[:,0]-coef[0]-coef[1]*logs[:,1]
    phi=np.linalg.lstsq(np.column_stack([np.ones(len(spread)-1),spread[:-1]]),spread[1:],rcond=None)[0][1]
    _,p,_=coint(logs[:,0],logs[:,1],trend='c',maxlag=5,autolag='aic')
    return dict(a=a,b=b,intercept=coef[0],beta=coef[1],coint_p=float(p),
                half_life=-np.log(2)/np.log(phi) if 0<phi<1 else np.nan)


def eligible_tickers(close,volume,companies):
    cash=(close*volume).median()
    names=companies.set_index('ticker').name
    return [t for t in close if close[t].count()>=400 and close[t].notna().mean()>=.99
            and cash[t]>=1e6 and close[t].median()>=3 and 'warrant' not in str(names[t]).lower()]


def sector_residuals(close,tickers,fit_dates):
    ret=np.log(close[tickers]).diff()
    sums=ret.sum(axis=1,min_count=1);counts=ret.count(axis=1)
    residual=ret.copy()*np.nan;coefs={}
    for t in tickers:
        market=(sums-ret[t])/(counts-1)
        g=pd.DataFrame({'r':ret[t],'m':market}).loc[fit_dates].dropna()
        coef=np.linalg.lstsq(np.column_stack([np.ones(len(g)),g.m]),g.r,rcond=None)[0]
        residual[t]=ret[t]-coef[0]-coef[1]*market;coefs[t]=coef.tolist()
    return residual,coefs


def select_pairs(close,volume,companies,panel,fit_dates,fold):
    train=close.loc[fit_dates]
    tickers=eligible_tickers(train,volume.loc[fit_dates],companies)
    residual,_=sector_residuals(close,tickers,fit_dates)
    raw=np.log(train[tickers]).diff().corr(min_periods=350)
    rc=residual.loc[fit_dates].corr(min_periods=350)
    candidates=[]
    for a,b in itertools.combinations(tickers,2):
        if raw.loc[a,b]>=.55 and rc.loc[a,b]>=.20:
            candidates.append((a,b,raw.loc[a,b],rc.loc[a,b]))
    candidates=sorted(candidates,key=lambda x:(-x[3],x[0],x[1]))[:50]
    fields=['rd_share_reported_q','sm_share_reported_q','gross_margin_reported_q',
            'operating_margin_reported_q','goodwill_share_assets','ppe_share_assets']
    hist=panel[(panel.month>=fit_dates[0]) & (panel.month<=fit_dates[-1])]
    profiles=hist.groupby('ticker')[fields].median()
    profiles=(profiles-profiles.median())/(profiles.quantile(.75)-profiles.quantile(.25)).replace(0,np.nan)
    models=[]
    for a,b,corr,rescorr in candidates:
        m=fit_pair(a,b,train)
        difference=(profiles.reindex([a,b]).iloc[0]-profiles.reindex([a,b]).iloc[1]).dropna()
        m.update(fold=fold,raw_corr=corr,residual_corr=rescorr,
                 fundamental_metrics=len(difference),fundamental_distance=np.sqrt((difference**2).mean()) if len(difference)>=3 else np.nan,
                 fit_start=str(fit_dates[0].date()),fit_end=str(fit_dates[-1].date()))
        models.append(m)
    if models:
        q=bh([m['coint_p'] for m in models])
        for m,v in zip(models,q):m['coint_q']=float(v)
    return models,tickers


def choose_pairs(models,variant):
    selected=[];used=set()
    for m in models:
        if not (.25<=m['beta']<=4 and 5<=m['half_life']<=90):continue
        if variant!='correlated_pairs' and m['coint_q']>.10:continue
        if variant=='fundamental_pairs' and (m['fundamental_metrics']<3 or not m['fundamental_distance']<=1.5):continue
        if m['a'] in used or m['b'] in used:continue
        selected.append(m.copy());used.update([m['a'],m['b']])
        if len(selected)==5:break
    return selected


def pair_signals(close,models):
    signals=[]
    for m in models:
        spread=np.log(close[m['a']])-m['intercept']-m['beta']*np.log(close[m['b']])
        z=(spread-spread.rolling(60,min_periods=60).mean().shift(1))/spread.rolling(60,min_periods=60).std().shift(1)
        signals.append(z.to_numpy())
    return signals


def simulate(close,opens,dividend,dates,models,threshold,cost_bps=5,borrow_rate=.03,
             basket_z=None,margin=None,random_seed=None):
    """Share-based accounting: signal previous close, execute next open; no daily silent rehedging."""
    columns=close.columns.tolist();lookup={t:i for i,t in enumerate(columns)}
    cp=close.to_numpy();op=opens.to_numpy();dv=dividend.to_numpy()
    date_indices=close.index.get_indexer(dates)
    signals=pair_signals(close,models) if basket_z is None else None
    bz=basket_z.reindex(columns=columns).to_numpy() if basket_z is not None else None
    qty=np.zeros(len(columns));book={};daily=[];trades=[];nav=1.0
    last_close=cp[date_indices[0]-1].copy();rng=np.random.default_rng(random_seed)
    portfolio_id=0
    def liquidate(key,prices,date,reason,signal_date,z=np.nan):
        nonlocal qty
        p=book.pop(key);cost=float(np.nansum(np.abs(p['qty']*prices))*cost_bps/10000)
        qty=sum((position['qty'] for position in book.values()),start=np.zeros(len(columns)))
        gross=float(np.nansum(p['qty']*(prices-p['entry_prices'])))
        trades.append(dict(trade_id=p['id'],entry_date=p['entry_date'],exit_date=date,
                           entry_signal_date=p['signal_date'],exit_signal_date=signal_date,
                           tickers=p['tickers'],direction=p['direction'],entry_z=p['entry_z'],exit_z=z,
                           holding_sessions=p['age'],exit_reason=reason,gross_price_pnl=gross,
                           dividend_pnl=p['dividends'],borrow_cost=p['borrow'],execution_cost=p['entry_cost']+cost,
                           net_pnl=gross+p['dividends']-p['borrow']-p['entry_cost']-cost))
        return cost
    for step,di in enumerate(date_indices):
        date=close.index[di];prior_date=close.index[di-1];opening=op[di];closing=cp[di]
        held=qty!=0
        if not np.isfinite(opening[held]).all() or not np.isfinite(closing[held]).all():
            raise ValueError(f'Missing price while holding a position on {date}; refusing silent omission')
        old_qty=qty.copy();div_cash=float(np.nansum(old_qty*dv[di]))
        gap=(date-prior_date).days
        borrow=float(np.nansum(abs(old_qty[old_qty<0]*last_close[old_qty<0]))*borrow_rate*gap/365)
        for p in book.values():
            p['dividends']+=float(np.nansum(p['qty']*dv[di]))
            p['borrow']+=float(np.nansum(abs(p['qty'][p['qty']<0]*last_close[p['qty']<0]))*borrow_rate*gap/365)
        overnight=float(np.nansum(old_qty*(opening-last_close)))
        cost=0.0
        if basket_z is None:
            exited=set()
            for key in list(book):
                p=book[key];p['age']+=1;z=signals[key][di-1]
                reason=('spread_stop' if np.isfinite(z) and abs(z)>=4 else
                        'reverted' if np.isfinite(z) and (abs(z)<=.5 or z*p['entry_z']<0) else
                        'max_holding' if p['age']>=MAX_HOLD else '')
                if reason:
                    cost+=liquidate(key,opening,date,reason,prior_date,z);exited.add(key)
            for key,m in enumerate(models):
                z=signals[key][di-1]
                ids=[lookup[m['a']],lookup[m['b']]]
                if key in book or key in exited or not np.isfinite(z) or not threshold<=abs(z)<4:continue
                if not np.isfinite(opening[ids]).all() or (opening[ids]<=0).any():continue
                direction=-np.sign(z) if random_seed is None else rng.choice([-1,1])
                q=np.zeros(len(columns));weights=direction*np.array([1,-m['beta']])/(1+m['beta'])
                budget=max(nav,0)/max(len(models),1)
                # Allocate each pair one fixed slot; unchanged positions retain their share counts.
                q[ids]=budget*weights/opening[ids]
                entry_cost=float(np.sum(np.abs(q[ids]*opening[ids]))*cost_bps/10000)
                cost+=entry_cost;qty+=q;portfolio_id+=1
                book[key]=dict(qty=q,entry_prices=opening.copy(),entry_date=date,signal_date=prior_date,
                               tickers=m['a']+'/'+m['b'],direction=direction,entry_z=z,age=0,
                               dividends=0.0,borrow=0.0,entry_cost=entry_cost,id=portfolio_id)
        elif step%5==0:
            for key in list(book):cost+=liquidate(key,opening,date,'weekly_rebalance',prior_date)
            values=bz[di-1].copy()
            long_ids=np.flatnonzero(np.isfinite(values)&(values<=-threshold)&np.isfinite(opening)&(opening>0))
            short_ids=np.flatnonzero(np.isfinite(values)&(values>=threshold)&np.isfinite(opening)&(opening>0))
            if margin is not None:
                mg=margin[di-1]
                long_ids=long_ids[np.isfinite(mg[long_ids])&(mg[long_ids]>=0)]
                short_ids=short_ids[np.isfinite(mg[short_ids])&(mg[short_ids]<0)]
            long_ids=long_ids[np.argsort(values[long_ids])[:5]]
            short_ids=short_ids[np.argsort(-values[short_ids])[:5]]
            if len(long_ids) and len(short_ids):
                q=np.zeros(len(columns));q[long_ids]=nav*.5/len(long_ids)/opening[long_ids]
                q[short_ids]=-nav*.5/len(short_ids)/opening[short_ids]
                entry_cost=float(np.nansum(abs(q*opening))*cost_bps/10000)
                cost+=entry_cost;qty+=q;portfolio_id+=1
                book[0]=dict(qty=q,entry_prices=opening.copy(),entry_date=date,signal_date=prior_date,
                             tickers=','.join(columns[i] for i in np.r_[long_ids,short_ids]),direction=0,
                             entry_z=np.nan,age=0,dividends=0.0,borrow=0.0,entry_cost=entry_cost,id=portfolio_id)
        for p in book.values():
            if basket_z is not None:p['age']+=1
        if not np.isfinite(closing[qty!=0]).all():raise ValueError(f'Missing closing mark after entry on {date}')
        intraday=float(np.nansum(qty*(closing-opening)))
        for p in book.values():
            if p['entry_date']==date:
                first_day=float(np.nansum(abs(p['qty'][p['qty']<0]*closing[p['qty']<0]))*borrow_rate*.25/365)
                p['borrow']+=first_day;borrow+=first_day
        long_pnl=float(np.nansum(np.where(old_qty>0,old_qty,0)*(opening-last_close))+np.nansum(np.where(qty>0,qty,0)*(closing-opening)))
        short_pnl=float(np.nansum(np.where(old_qty<0,old_qty,0)*(opening-last_close))+np.nansum(np.where(qty<0,qty,0)*(closing-opening)))
        gross_exposure=float(np.nansum(abs(qty*closing)))
        if step==len(date_indices)-1:
            for key in list(book):cost+=liquidate(key,closing,date,'scheduled_fold_close',prior_date)
        delta=overnight+intraday+div_cash-cost-borrow
        prev_nav=nav;nav+=delta
        if nav<=0:raise ValueError('Strategy capital depleted')
        daily.append(dict(date=date,net_return=delta/prev_nav,nav=nav,price_pnl=overnight+intraday,
                          long_price_pnl=long_pnl,short_price_pnl=short_pnl,dividend_pnl=div_cash,
                          execution_cost=cost,borrow_cost=borrow,gross_exposure=gross_exposure/prev_nav,
                          active_positions=len(book)))
        last_close=closing.copy()
    result=pd.DataFrame(daily);ledger=pd.DataFrame(trades)
    if len(ledger):np.testing.assert_allclose(ledger.net_pnl.sum(),nav-1,atol=1e-9)
    return result,ledger


def performance(daily,trades):
    r=daily.net_return.to_numpy();wealth=np.r_[1,np.cumprod(1+r)]
    total=wealth[-1]-1;std=r.std(ddof=1)
    return dict(total_return=total,annualized_return=(wealth[-1]**(252/len(r))-1),
                sharpe=r.mean()/std*np.sqrt(252) if std>1e-12 else np.nan,
                max_drawdown=float(np.min(wealth/np.maximum.accumulate(wealth)-1)),
                trades=len(trades),win_fraction=(trades.net_pnl>0).mean() if len(trades) else np.nan,
                average_gross_exposure=daily.gross_exposure.mean(),
                execution_cost_on_fold_capital=daily.execution_cost.sum(),
                borrow_cost_on_fold_capital=daily.borrow_cost.sum())


def load_data():
    bars=pd.read_csv(BASE/'prices/daily_bars.csv',parse_dates=['date'])
    if bars.duplicated(['ticker','date']).any():raise ValueError('Duplicate bars')
    close=bars.pivot(index='date',columns='ticker',values='close').sort_index().where(lambda x:x>0)
    opens=bars.pivot(index='date',columns='ticker',values='open').reindex_like(close).where(lambda x:x>0)
    volume=bars.pivot(index='date',columns='ticker',values='volume').reindex_like(close)
    raw_div=pd.read_csv(BASE/'backtest_inputs/dividends.csv')
    invalid=raw_div[(raw_div.currency.str.upper()!='USD') | raw_div.split_adjusted_cash_amount.isna()]
    if len(invalid):raise ValueError('Unsupported/missing dividend amount needs review')
    dividend=pd.DataFrame(0.0,index=close.index,columns=close.columns)
    for row in raw_div.itertuples():
        d=pd.Timestamp(row.ex_dividend_date)
        if d in dividend.index and row.ticker in dividend:dividend.loc[d,row.ticker]+=row.split_adjusted_cash_amount
    companies=pd.read_csv(ROOT/'data/packaged_software/packaged_software_companies.csv')
    panel=pd.read_csv(ROOT/'data/processed/company_signal_research/monthly_research_panel.csv',parse_dates=['month'])
    margins=pd.DataFrame(np.nan,index=close.index,columns=close.columns)
    # Reindex each complete row rather than backfill a newly missing metric from an older quarter.
    for ticker,g in panel.groupby('ticker'):
        s=g.set_index('month').operating_margin_reported_q
        days=pd.Series(close.index,index=close.index)
        merged=pd.merge_asof(days.rename('date').reset_index(drop=True).to_frame(),
                             s.reset_index().rename(columns={'month':'date'}).sort_values('date'),on='date')
        margins[ticker]=merged.operating_margin_reported_q.to_numpy()
    return close,opens,volume,dividend,companies,panel,margins.to_numpy()


def bootstrap_interval(returns):
    a=np.asarray(returns);rng=np.random.default_rng(SEED);values=[]
    for _ in range(2000):
        starts=rng.integers(0,len(a),size=math.ceil(len(a)/21))
        sample=np.concatenate([a[(start+np.arange(21))%len(a)] for start in starts])[:len(a)]
        values.append(sample.mean()*252)
    return np.quantile(values,[.025,.975])


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=OUT);args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    close,opens,volume,dividend,companies,panel,margins=load_data()
    selections=[];folds=[];validation=[];all_daily=[];all_trades=[];placebos=[]
    starts=pd.to_datetime(['2025-01-01','2025-07-01','2026-01-01','2026-07-01'])
    for fi,start in enumerate(starts):
        end=starts[fi+1] if fi+1<len(starts) else close.index.max()+pd.Timedelta(days=1)
        test_dates=close.index[(close.index>=start)&(close.index<end)]
        train_dates=close.index[close.index<start][-756:]
        val_dates=train_dates[-126:];fit_dates=train_dates[:-126-MAX_HOLD]
        fold=f'{start.date()}_{test_dates[-1].date()}'
        models,tickers=select_pairs(close,volume,companies,panel,fit_dates,fold)
        selections.extend(models)
        residual,_=sector_residuals(close,tickers,fit_dates)
        bz=residual.rolling(5,min_periods=5).sum()/(residual.rolling(60,min_periods=60).std().shift(1)*np.sqrt(5))
        print(f'Fold {fold}: {len(tickers)} eligible stocks; {len(models)} screened pairs',flush=True)
        for variant in VARIANTS:
            chosen=choose_pairs(models,variant) if 'pairs' in variant else []
            grid=[]
            for threshold in ENTRY_GRID:
                d,t=simulate(close,opens,dividend,val_dates,chosen,threshold,
                             basket_z=bz if 'pairs' not in variant else None,
                             margin=margins if variant=='profitable_long_weak_short' else None)
                stat=performance(d,t);score=stat['sharpe'] if stat['trades']>=5 and np.isfinite(stat['sharpe']) else -np.inf
                grid.append((score,threshold))
                validation.append(dict(fold=fold,variant=variant,entry_threshold=threshold,**stat))
            # Tie-break towards the middle default, not a more complex model.
            best=max(grid,key=lambda x:(x[0],-abs(x[1]-2.0)))
            entry=best[1] if np.isfinite(best[0]) else 2.0
            refitted=[]
            for model in chosen:
                m=fit_pair(model['a'],model['b'],close.loc[train_dates])
                m.update(raw_corr=model['raw_corr'],residual_corr=model['residual_corr'])
                # Pair identities retained; refits use training only and basic hedge validity guards.
                if .25<=m['beta']<=4:refitted.append(m)
            full_residual,coefs=sector_residuals(close,tickers,train_dates)
            full_bz=full_residual.rolling(5,min_periods=5).sum()/(full_residual.rolling(60,min_periods=60).std().shift(1)*np.sqrt(5))
            for scenario,cost,borrow in [('base',5,.03),('stress',20,.10)]:
                d,t=simulate(close,opens,dividend,test_dates,refitted,entry,cost,borrow,
                             basket_z=full_bz if 'pairs' not in variant else None,
                             margin=margins if variant=='profitable_long_weak_short' else None)
                d['fold']=fold;d['variant']=variant;d['scenario']=scenario
                if len(t):t['fold']=fold;t['variant']=variant;t['scenario']=scenario
                all_daily.append(d);all_trades.append(t)
                folds.append(dict(fold=fold,variant=variant,scenario=scenario,entry_threshold=entry,
                                  training_start=train_dates[0],training_end=train_dates[-1],
                                  selection_fit_end=fit_dates[-1],validation_start=val_dates[0],validation_end=val_dates[-1],
                                  test_start=test_dates[0],test_end=test_dates[-1],eligible_stocks=len(tickers),
                                  pairs=';'.join(m['a']+'/'+m['b'] for m in refitted),
                                  hedge_models=json.dumps(refitted),**performance(d,t)))
            if variant=='correlated_pairs':
                for seed in range(20):
                    d,t=simulate(close,opens,dividend,test_dates,refitted,entry,random_seed=SEED+seed)
                    placebos.append(dict(fold=fold,seed=seed,**performance(d,t)))
    daily=pd.concat(all_daily,ignore_index=True);trades=pd.concat(all_trades,ignore_index=True)
    fold_results=pd.DataFrame(folds);summaries=[]
    for (variant,scenario),g in daily.groupby(['variant','scenario']):
        g=g.sort_values('date');led=trades[(trades.variant==variant)&(trades.scenario==scenario)] if len(trades) else trades
        stat=performance(g,led);ci=bootstrap_interval(g.net_return)
        # Cost totals across independent folds are descriptive sums of fold-capital fractions.
        stat.update(variant=variant,scenario=scenario,positive_folds=int((fold_results[(fold_results.variant==variant)&(fold_results.scenario==scenario)].total_return>0).sum()),
                    annualized_mean_ci_low=ci[0],annualized_mean_ci_high=ci[1])
        summaries.append(stat)
    summary=pd.DataFrame(summaries)
    for filename,frame in [('daily_oos.csv',daily),('trades_oos.csv',trades),('fold_results.csv',fold_results),
                           ('validation_grid.csv',pd.DataFrame(validation)),('training_pair_screen.csv',pd.DataFrame(selections)),
                           ('strategy_summary.csv',summary),('random_direction_placebos.csv',pd.DataFrame(placebos))]:
        frame.to_csv(out/filename,index=False,float_format='%.9g')
    fig,axes=plt.subplots(2,1,figsize=(13,9),layout='constrained')
    for variant in VARIANTS:
        g=daily[(daily.variant==variant)&(daily.scenario=='base')].sort_values('date')
        wealth=(1+g.net_return).cumprod();axes[0].plot(g.date,wealth,label=variant)
        axes[1].plot(g.date,wealth/wealth.cummax()-1,label=variant)
    axes[0].set_title('Walk-forward equity mean reversion: net simulated equity');axes[0].set_ylabel('Initial capital = 1')
    axes[0].legend(fontsize=8);axes[1].set_title('Drawdowns');axes[1].set_ylabel('Fraction below peak')
    for ax in axes:
        for start in starts:ax.axvline(start,color='gray',ls=':',lw=.6)
    fig.savefig(out/'walk_forward_equity.png',dpi=160);plt.close(fig)
    manifest=dict(test_start='2025-01-01',test_end=str(close.index.max().date()),training_observations=756,
                  validation_observations=126,selection_gap_observations=MAX_HOLD,entry_grid=ENTRY_GRID,
                  max_holding_sessions=MAX_HOLD,exit_z=.5,stop_z=4,variants=VARIANTS,
                  base={'one_way_execution_bps':5,'annual_short_borrow':.03},stress={'one_way_execution_bps':20,'annual_short_borrow':.10},
                  short_locates='assumed available; no historical borrow/locate records',cash_interest=0,
                  execution='previous-close signal; next-open trade; predetermined final-day close liquidation',
                  dividend_accounting='actual split-adjusted cash, signed shares held before ex-date; economic accrual on ex-date',
                  limitations=['Current universe survivorship and unspliced historical symbols',
                    'Prior work inspected 2025-26 prices; this is exploratory chronological evaluation, not untouched final holdout',
                    'No historical borrow availability, spread quotes, impact model, taxes or funding/margin stress',
                    'Daily opens are execution proxies; daily bars cannot establish actual fills',
                    'Five predefined variants plus validation grid; no winner promoted automatically',
                    '50 correlation-prescreened pairs tested per fold; cointegration BH correction is conditional on that prescreen',
                    'Margins use dated monthly research features; metric accounting/coverage limitations persist',
                    'Borrow on prior-close short notional across calendar gaps, including exit days; first session adds 0.25 day; no rebates'],
                  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                 [BASE/'prices/daily_bars.csv',BASE/'backtest_inputs/dividends.csv',
                                  ROOT/'data/processed/company_signal_research/monthly_research_panel.csv']})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    capability=json.loads((BASE/'backtest_inputs/options_capability.json').read_text())
    columns=['variant','scenario','total_return','sharpe','max_drawdown','trades','positive_folds','annualized_mean_ci_low','annualized_mean_ci_high']
    lines=['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']
    for row in summary[columns].itertuples(index=False,name=None):
        lines.append('| '+' | '.join(f'{x:.3f}' if isinstance(x,(float,np.floating)) else str(x) for x in row)+' |')
    report='''# Walk-forward mean-reversion research

This is an exploratory historical equity test, not a claim of deployable alpha. Earlier research already inspected
the later period, so chronological separation reduces leakage but cannot make it a fresh unseen holdout.
All five variants are retained, including failed screens and cash periods. No pair is selected using test results.

## Chronological protocol

Four six-month test folds begin January 2025, July 2025, January 2026 and July 2026 (last fold partial).
Each fold uses at most 756 earlier sessions. Pair selection uses the earlier training segment; 42 sessions
separate that segment from the final 126-session validation window. Validation chooses only the entry z-score
from 1.5, 2.0 or 2.5. Hedge coefficients and sector exposures are then refitted using all pre-test data and frozen.
Rolling signal normalization uses only previous closes. Validation/test positions are liquidated at known boundaries;
their outcomes never spill across the split. Later folds may use earlier test periods once those dates are historical.

Training eligibility requires >=400 bars, >=99% observed dates, median price >=$3 and median daily dollar volume
>=$1m. Warrants are excluded. A 50-pair correlation prescreen uses raw daily correlation >=0.55 and sector-residual
correlation >=0.20. Pair beta must be 0.25-4 and estimated half-life 5-90 observations at selection. Up to five
non-overlapping pairs are chosen in training residual-correlation order. Strict variants require Engle-Granger
cointegration BH q<=0.10 across the prescreened set; the fundamentals variant also requires >=3 comparable metrics
and normalized profile distance <=1.5. These thresholds are fixed, not tuned on test returns.

The two basket variants rank five-session sector residual reversals and rebalance every five sessions.
The fundamental basket additionally buys nonnegative operating-margin companies and shorts negative-margin
companies. It is a fixed hypothesis, not a proven consequence of the earlier metric correlations.

## Results

Returns below are fractions (0.10 = 10%). Sharpe uses zero cash-interest excess returns. Bootstrap intervals are
21-session block intervals for annualized arithmetic mean returns, not annualized compound returns or a proof
of significance after strategy search. Four fold results, all parameter trials and all trades are saved.

'''+ '\n'.join(lines)+'''

## Accounting and limitations

Pairs trade both legs in beta-weighted gross exposure, using fixed share counts between entries/exits.
Signals at close execute at the next open; the final close is a scheduled boundary liquidation. Per-pair capital
slots leave cash when no signal is active. Gross exposure can drift while holding; no volatility-target leverage
is applied. Actual dividends are accrued to longs and debited to shorts held before ex-date. The base case charges
5bp one-way execution cost plus 3% annual short borrow; stress charges 20bp and 10% borrow. These are assumptions,
not observed broker fees. Cash earns zero. Corporate actions other than split/cash-dividend adjustments and
historical symbol gaps are not reconstructed. Missing bars while holding stop the run rather than dropping losses.

The trade ledger reconciles price P&L, dividends, execution costs and borrow to each fold's equity. Daily output
separates long-leg and short-leg price contributions; those columns are attribution, not standalone funded strategies.
Twenty fixed random-direction controls use the same correlated-pair screen/entry thresholds. They are illustrative
placebos, not a full data-snooping-adjusted significance test. Survivorship, historical short locates and actual
bid/ask execution remain material limitations. No orders were placed.

## Options

No historical options quotes or chains were previously stored. The real API probe is recorded below.
Stock signals do not establish profitable options trades: premiums, expiry, bid/ask, volatility and exercise
cashflows must be modeled using actual historical contracts and quotes. A snapshot of today's Greeks cannot
be backdated. No Black-Scholes-generated prices are presented as observed options P&L.

```json
'''+json.dumps(capability,indent=2)+'''
```

Sources: [statsmodels cointegration](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.coint.html),
[Massive dividends](https://massive.com/docs/rest/stocks/corporate-actions/dividends),
[Massive historical options](https://massive.com/docs/rest/options/overview).

Run from the project root after downloading dividend inputs:

```powershell
.\\venv\\Scripts\\python.exe data/packaged_software/extract_backtest_inputs.py
.\\venv\\Scripts\\python.exe data/packaged_software/backtest_mean_reversion.py
```
'''
    (out/'REPORT.md').write_text(report,encoding='utf-8')
    base=summary[summary.scenario=='base'].set_index('variant')
    stress=summary[summary.scenario=='stress'].set_index('variant')
    findings=f'''## Findings

**No dependable edge was established.** Correlated pairs returned {base.loc['correlated_pairs','total_return']:.2%}
net in the chronological test, with Sharpe {base.loc['correlated_pairs','sharpe']:.2f} and maximum drawdown
{base.loc['correlated_pairs','max_drawdown']:.2%}. The cost stress returned
{stress.loc['correlated_pairs','total_return']:.2%}. All non-cash strategies' block confidence intervals include zero.
The correlation pattern does not translate into reliably profitable mean reversion under these rules.

The sector-reversal basket returned {base.loc['sector_reversal','total_return']:.2%}; the operating-margin
filtered basket returned {base.loc['profitable_long_weak_short','total_return']:.2%}. The strict cointegration
strategy made {int(base.loc['cointegrated_pairs','trades'])} trade and returned
{base.loc['cointegrated_pairs','total_return']:.2%}; that is far too little activity to validate a strategy.
Fundamental-matched cointegrated pairs made zero trades. A 0% cash result is not a successful trading signal.

PAYC/PCTY contributed losses under these rules despite its earlier correlation. QLYS/TENB produced only one
trade. Pair attribution is descriptive and must not be used to remove losers and report a revised historical winner.
Twenty random-direction controls also span positive and negative results; the observed outcome does not
establish significance against strategy-search noise. None of the thresholds was changed after viewing test results.

'''
    text=(out/'REPORT.md').read_text(encoding='utf-8')
    (out/'REPORT.md').write_text(text.replace('## Chronological protocol\n',findings+'## Chronological protocol\n',1),encoding='utf-8')
    print(summary[columns].to_string(index=False),flush=True)


if __name__=='__main__':main()
