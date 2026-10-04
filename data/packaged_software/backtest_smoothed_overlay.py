"""One fixed standalone strategy: causal momentum times an observed-data overlay.

Research replay only. No orders. No mock fundamental data or post-result tuning.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from smoothed_momentum_signals import causal_savgol, momentum_signals

BASE = Path(__file__).resolve().parent
OUT = BASE.parent/'processed/smoothed_overlay'
GROUP_WEIGHTS = {'quality':.35, 'software_investment':.20, 'physical_investment':.15,
                 'leases':.10, 'cloud':.10, 'disclosure_candidates':.10}
QUALITY = [('rev_growth_yoy_q',1), ('q_operating_margin',1),
           ('q_fcf_physical_capex_margin',1), ('q_sbc_pct_rev',-1)]
CLOUD = ['cloud_annual_minimum_commitment_disclosed_usd',
         'cloud_contract_minimum_total_disclosed_usd',
         'cloud_remaining_obligations_and_associated_services_disclosed_usd',
         'cloud_remaining_obligations_disclosed_usd',
         'mixed_services_commitments_primarily_cloud_disclosed_usd',
         'reported_AWS_agreement_spending_annual_disclosed_usd',
         'reported_AWS_agreement_spending_nine_month_disclosed_usd',
         'reported_AWS_agreement_spending_quarter_disclosed_usd',
         'reported_AWS_agreement_spending_six_month_disclosed_usd',
         'reported_cloud_and_server_hosting_expense_annual_disclosed_usd',
         'reported_cloud_and_server_hosting_expense_nine_month_disclosed_usd',
         'reported_cloud_and_server_hosting_expense_quarter_disclosed_usd',
         'reported_cloud_and_server_hosting_expense_six_month_disclosed_usd',
         'reported_hosting_and_infrastructure_expense_annual_disclosed_usd',
         'reported_hosting_and_infrastructure_expense_nine_month_disclosed_usd',
         'reported_hosting_and_infrastructure_expense_quarter_disclosed_usd',
         'reported_hosting_and_infrastructure_expense_six_month_disclosed_usd']
GUIDANCE = ['capex_guidance_annual_high_usd', 'capex_guidance_annual_low_usd',
            'capex_guidance_remaining_year_high_usd','capex_guidance_remaining_year_low_usd',
            'capex_guidance_next_12_months_upper_bound_usd']
OVERLAY_INPUTS = ['total_assets','ttm_revenue','ttm_software_development_cash_payments',
                 'capex_cash_ttm_to_revenue','capex_cash_ttm_growth_yoy','capex_cash_quarter_growth_yoy',
                 'ppe_net_growth_yoy','ppe_gross_usd','ppe_net_usd','unused_cloud_commitment_expense_quarter_disclosed_usd',
                 'operating_lease_liability_growth_qoq','operating_lease_liability_growth_yoy',
                 'finance_lease_liability_growth_qoq','finance_lease_liability_growth_yoy',
                 'operating_lease_liability_usd','operating_lease_rou_asset_usd','operating_lease_undiscounted_payments_usd',
                 'operating_lease_noncash_additions_quarter_usd','operating_lease_noncash_additions_annual_usd',
                 'finance_lease_liability_usd','finance_lease_rou_asset_usd','finance_lease_undiscounted_payments_usd',
                 'finance_lease_noncash_additions_quarter_usd','finance_lease_noncash_additions_annual_usd'] + [c for c,_ in QUALITY] + CLOUD + GUIDANCE + ['pjm_rto_capacity_price_change_vs_previous_auction','ferc_power_search_candidate_count','capex_guidance_candidate_sentences','datacenter_capex_candidate_sentences','ppa_disclosure_candidate_sentences']

CANDIDATES = ['ferc_power_search_candidate_count','capex_guidance_candidate_sentences',
              'datacenter_capex_candidate_sentences','ppa_disclosure_candidate_sentences']


def rank_signal(series):
    good = series.replace([np.inf,-np.inf],np.nan).dropna()
    result = pd.Series(np.nan,index=series.index,dtype=float)
    if len(good)>=5:
        result.loc[good.index] = 2*(good.rank(method='average')-1)/(len(good)-1)-1
    return result


def ratio(a,b):
    return a/b.where(b>0)


def with_absent_columns_as_missing(frame):
    """Columns removed by the qualification step are treated as missing data, so their groups stay neutral."""
    frame = frame.copy()
    for col in OVERLAY_INPUTS:
        if col not in frame:
            frame[col] = np.nan
    return frame


def overlay(frame, old_frame=None):
    """Rank observable components separately; don't equate absent data to zero spend."""
    frame = with_absent_columns_as_missing(frame)
    values, groups = {}, {}
    for col,sign in QUALITY:
        values[col] = frame[col]*sign
    groups['quality'] = [x for x,_ in QUALITY]
    assets, revenue = frame.total_assets, frame.ttm_revenue
    values['software_cash_intensity'] = ratio(frame.ttm_software_development_cash_payments,revenue)
    if old_frame is None:
        values['software_cash_growth_2q'] = pd.Series(np.nan,index=frame.index)
    else:
        prior = with_absent_columns_as_missing(old_frame).ttm_software_development_cash_payments.reindex(frame.index)
        values['software_cash_growth_2q'] = ratio(frame.ttm_software_development_cash_payments,prior)-1
    groups['software_investment'] = ['software_cash_intensity','software_cash_growth_2q']
    groups['physical_investment'] = []
    for col in ['capex_cash_ttm_growth_yoy','capex_cash_quarter_growth_yoy','ppe_net_growth_yoy']:
        values[col] = frame[col]; groups['physical_investment'].append(col)
    # These intensities are scale-free levels, kept distinct from growth.
    for col,denom in [('capex_cash_ttm_to_revenue',None),('ppe_gross_usd',assets),('ppe_net_usd',assets)]:
        values[col] = frame[col] if denom is None else ratio(frame[col],denom)
        groups['physical_investment'].append(col)
    for col in GUIDANCE:
        values[col] = ratio(frame[col],revenue)
        groups['physical_investment'].append(col)
    groups['leases'] = []
    for kind in ['operating','finance']:
        for suffix in ['liability_growth_qoq','liability_growth_yoy']:
            col=f'{kind}_lease_{suffix}'; values[col]=frame[col]; groups['leases'].append(col)
        for suffix in ['liability_usd','rou_asset_usd','undiscounted_payments_usd',
                       'noncash_additions_quarter_usd','noncash_additions_annual_usd']:
            col=f'{kind}_lease_{suffix}'
            if col in frame:
                # Fixed liability/payment burden is negative; expansion assets/additions positive.
                sign = -1 if suffix in ['liability_usd','undiscounted_payments_usd'] else 1
                values[col]=ratio(frame[col],assets)*sign; groups['leases'].append(col)
    groups['cloud'] = []
    for col in CLOUD:
        values[col]=ratio(frame[col],revenue); groups['cloud'].append(col)
    # Unused commitment expense is a negative efficiency observation, not expansion.
    col='unused_cloud_commitment_expense_quarter_disclosed_usd'
    values[col]=-ratio(frame[col],revenue); groups['cloud'].append(col)
    groups['disclosure_candidates'] = CANDIDATES
    for col in CANDIDATES: values[col]=frame[col]
    ranked = pd.DataFrame({name:rank_signal(v) for name,v in values.items()})
    result = pd.DataFrame(index=frame.index)
    for group,cols in groups.items():
        result[group] = ranked[cols].mean(axis=1)
        result[group+'_components'] = ranked[cols].notna().sum(axis=1)
    result['observed_groups'] = result[list(GROUP_WEIGHTS)].notna().sum(axis=1)
    result['observed_weight'] = sum(result[g].notna()*w for g,w in GROUP_WEIGHTS.items())
    # Fixed weights: missing groups contribute neutral score but remain explicitly missing.
    result['fundamental_score'] = sum(result[g].fillna(0)*w for g,w in GROUP_WEIGHTS.items())
    qualified = (result.quality_components>=2)&(result.observed_groups>=2)
    result.loc[~qualified,'fundamental_score']=np.nan
    components = ranked.stack().rename('ranked_component').reset_index()
    components.columns=['ticker','component','ranked_component']
    return result,components


def risk_weights(strength, returns, target=.10, leverage_cap=2.5, name_cap=.10):
    """Inverse 20-session vol, then covariance-based PORTFOLIO target and caps."""
    valid = returns.notna().sum()>=20
    vol = returns.std(ddof=1)*np.sqrt(252)
    strength = strength.where(valid & (vol>1e-6),0).fillna(0).clip(lower=0)
    raw = strength/vol
    raw = raw.replace([np.inf,-np.inf],np.nan).fillna(0)
    if raw.sum()<=0: return raw*0,0.
    raw/=raw.sum()
    selected=raw[raw>0].index
    # Complete observations avoid pairwise covariance inconsistency.
    hist=returns[selected].dropna()
    if len(hist)<20: return raw*0,0.
    covariance=hist.cov().to_numpy()*252
    vector=raw.loc[selected].to_numpy()
    predicted=float(np.sqrt(max(0,vector@covariance@vector)))
    if predicted<1e-8: return raw*0,0.
    weights=(raw*min(target/predicted,leverage_cap)).clip(upper=name_cap)
    predicted_final=float(np.sqrt(max(0,weights.loc[selected].to_numpy()@covariance@weights.loc[selected].to_numpy())))
    return weights,predicted_final


def rebalance(qty,cash,prices,target,cost_rate):
    """Self-financing target weights, solving costs against post-cost capital."""
    held=qty!=0
    if not np.isfinite(prices[held]).all(): raise ValueError('Missing held execution price')
    nav=cash+np.sum(qty[held]*prices[held])
    safe=np.where(np.isfinite(prices)&(prices>0),prices,1.)
    if ((target>0)&(~np.isfinite(prices)|(prices<=0))).any():
        raise ValueError('Missing desired execution price; strategy cannot assume a fill')
    capital=nav
    for _ in range(30):
        desired=target*capital/safe
        cost=float(np.sum(np.abs(desired-qty)*safe)*cost_rate)
        new_capital=nav-cost
        if abs(new_capital-capital)<1e-12: break
        capital=new_capital
    desired=target*new_capital/safe
    delta=desired-qty
    cost=float(np.sum(np.abs(delta)*safe)*cost_rate)
    new_cash=cash-float(np.sum(delta*safe))-cost
    return desired,new_cash,cost,delta,nav


def macro_calendar():
    """Official current historical schedules; not certified original schedule vintages."""
    cpi={2024:['01-11','02-13','03-12','04-10','05-15','06-12','07-11','08-14','09-11','10-10','11-13','12-11'],
         2025:['01-15','02-12','03-12','04-10','05-13','06-11','07-15','08-12','09-11','10-24','12-18'],
         2026:['01-13','02-13','03-11','04-10','05-12','06-10','07-14','08-12']}
    fomc={2024:['01-31','03-20','05-01','06-12','07-31','09-18','11-07','12-18'],
          2025:['01-29','03-19','05-07','06-18','07-30','09-17','10-29','12-10'],
          2026:['01-28','03-18','04-29','06-17','07-29']}
    rows=[]
    for event,byyear in [('CPI',cpi),('FOMC',fomc)]:
        for year,dates in byyear.items():
            url=f'https://www.bls.gov/schedule/{year}/' if event=='CPI' else 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
            for suffix in dates:
                rows.append({'date':pd.Timestamp(f'{year}-{suffix}'),'event':event,'source_url':url,
                             'schedule_vintage':'current historical schedule; originally-known timing assumed'})
    return pd.DataFrame(rows).sort_values('date')


def simulate(close,opens,identity,dividend,rf,dates,targets,bps,financing_spread=.02,benchmark=False):
    tickers=close.columns; qty=np.zeros(len(tickers));cash=1.; prior_nav=1.
    daily=[];trades=[];holdings=[];warning=None
    for step,date in enumerate(dates):
        di=close.index.get_loc(date);prior_date=close.index[di-1]
        op=opens.loc[date].to_numpy();cp=close.loc[date].to_numpy()
        held=qty!=0
        ok=identity.loc[date].eq('provider_issuer_and_share_identity_match').to_numpy()
        if ((~np.isfinite(op)|~np.isfinite(cp)|~ok)&held).any():
            warning={'status':'unresolved_held_price_or_identity','date':str(date.date()),
                     'tickers':tickers[(~np.isfinite(op)|~np.isfinite(cp)|~ok)&held].tolist()}
            break
        old_qty=qty.copy()
        dividends=float(np.sum(qty*dividend.loc[date].to_numpy()))
        gap=(date-prior_date).days
        # Proxy accrued interest; rf held cash from prior close, financing adds spread.
        rate=float(rf.loc[prior_date])
        interest=cash*rate if cash>=0 else cash*(rate+financing_spread*gap/365)
        cash+=dividends+interest
        target=targets.loc[date].to_numpy()
        if benchmark and step>0: target=None
        if target is not None:
            desired=(target>0)
            if ((~np.isfinite(op)|~np.isfinite(cp)|~ok)&desired).any():
                # Do not use current closing availability to decide an opening trade.
                # Any unavailable requested fill makes the run unqualified instead.
                warning={'status':'unresolved_requested_fill_or_identity','date':str(date.date()),
                         'tickers':tickers[(~np.isfinite(op)|~np.isfinite(cp)|~ok)&desired].tolist()}
                break
            qty,cash,cost,delta,opening_nav=rebalance(qty,cash,op,target,bps/10000)
            for i in np.flatnonzero(np.abs(delta)>1e-12):
                trades.append({'date':date,'signal_date':prior_date,'ticker':tickers[i],
                               'share_delta':delta[i],'price':op[i],'notional':abs(delta[i]*op[i]),
                               'execution_cost':abs(delta[i]*op[i])*bps/10000})
        else: cost=0.; opening_nav=cash+float(np.sum(qty[qty!=0]*op[qty!=0]))
        if step==len(dates)-1:
            terminal_qty=qty.copy();terminal_cost=float(np.sum(np.abs(qty[qty!=0]*cp[qty!=0]))*bps/10000)
            cash+=float(np.sum(qty[qty!=0]*cp[qty!=0]))-terminal_cost
            for i in np.flatnonzero(qty!=0):
                trades.append({'date':date,'signal_date':'scheduled_terminal_liquidation','ticker':tickers[i],
                               'share_delta':-qty[i],'price':cp[i],'notional':abs(qty[i]*cp[i]),
                               'execution_cost':abs(qty[i]*cp[i])*bps/10000})
            qty*=0;cost+=terminal_cost
        nav=cash+float(np.sum(qty[qty!=0]*cp[qty!=0]))
        if nav<=0: raise ValueError('Capital depleted')
        overnight=float(np.sum(old_qty[old_qty!=0]*(op[old_qty!=0]-close.loc[prior_date].to_numpy()[old_qty!=0])))
        trading_qty=terminal_qty if step==len(dates)-1 else qty
        intraday=float(np.sum(trading_qty[trading_qty!=0]*(cp[trading_qty!=0]-op[trading_qty!=0])))
        np.testing.assert_allclose(nav-prior_nav,overnight+intraday+dividends+interest-cost,atol=1e-10)
        equity_notional=float(np.sum(np.abs(trading_qty[trading_qty!=0]*cp[trading_qty!=0])))
        daily.append({'date':date,'signal_date':prior_date,'nav':nav,'net_return':nav/prior_nav-1,
                      'price_pnl':overnight+intraday,'dividend_pnl':dividends,'interest_pnl':interest,
                      'execution_cost':cost,'gross_exposure':equity_notional/nav,
                      'positions':int((trading_qty>0).sum()),'cash':cash})
        for i in np.flatnonzero(qty>0):
            holdings.append({'date':date,'ticker':tickers[i],'shares':qty[i],
                             'close':cp[i],'weight':qty[i]*cp[i]/nav})
        prior_nav=nav
    return pd.DataFrame(daily),pd.DataFrame(trades),pd.DataFrame(holdings),warning


def performance(daily,rf,warning):
    if daily.empty: return {'status':warning or 'no_data'}
    r=daily.net_return; wealth=np.r_[1,daily.nav]
    excess=r-rf.reindex(pd.DatetimeIndex(daily.date)).to_numpy()
    sd=excess.std(ddof=1)
    return {'status':'complete' if warning is None else 'incomplete_NOT_full_period_performance',
            'start':str(daily.date.min().date()),'end':str(daily.date.max().date()),'sessions':len(daily),
            'total_return':float(daily.nav.iloc[-1]-1),
            'annualized_return':float(daily.nav.iloc[-1]**(252/len(daily))-1),
            'sharpe':float(excess.mean()/sd*np.sqrt(252)) if sd>1e-10 else None,
            'max_drawdown':float((wealth/np.maximum.accumulate(wealth)-1).min()),
            'realized_volatility':float(r.std(ddof=1)*np.sqrt(252)),
            'mean_gross_exposure':float(daily.gross_exposure.mean()),
            'mean_positions':float(daily.positions.mean()),
            'warning':warning}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    inputs=[BASE/'final/feature_matrix_qualified.csv',BASE/'final/feature_matrix_provenance.csv',
            BASE/'extracts/power_capex/matrix_feature_provenance.csv',
            BASE/'extracts/company_coverage/daily_bars_reviewed.csv',
            BASE/'extracts/backtest_inputs/dividends.csv',BASE/'output/factor_returns_daily.csv']
    hashes={str(p.relative_to(BASE.parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    matrix=with_absent_columns_as_missing(pd.read_csv(inputs[0],dtype={'cik':str},low_memory=False))
    assert matrix.cik.nunique()==168 and not matrix.duplicated(['cik','quarter']).any()
    names=sorted(matrix.ticker.unique())
    bars=pd.read_csv(inputs[3],parse_dates=['date'],low_memory=False)
    assert not bars.duplicated(['ticker','date']).any()
    factors=pd.read_csv(inputs[5],parse_dates=['date']).set_index('date').sort_index()
    calendar=factors.index
    close=bars.pivot(index='date',columns='ticker',values='close').reindex(index=calendar,columns=names)
    opens=bars.pivot(index='date',columns='ticker',values='open').reindex_like(close)
    volume=bars.pivot(index='date',columns='ticker',values='volume').reindex_like(close)
    identity=bars.pivot(index='date',columns='ticker',values='price_identity_status').reindex_like(close)
    raw_div=pd.read_csv(inputs[4],parse_dates=['ex_dividend_date'])
    assert raw_div.currency.eq('USD').all() and raw_div.split_adjusted_cash_amount.notna().all()
    dividend=raw_div.groupby(['ex_dividend_date','ticker']).split_adjusted_cash_amount.sum().unstack().reindex_like(close).fillna(0)
    rf=factors.rf/100
    macro=macro_calendar();macro.to_csv(OUT/'macro_calendar.csv',index=False)
    macro_days=set(macro.date)
    provenance=pd.concat([pd.read_csv(inputs[1],dtype={'cik':str},low_memory=False),
                          pd.read_csv(inputs[2],dtype={'cik':str},low_memory=False)],ignore_index=True)
    populated=provenance[provenance.value.notna()].copy()
    availability=pd.to_datetime(populated.available_date,errors='coerce')
    decision=pd.to_datetime(populated.decision_date,errors='coerce')
    assert (availability.dropna()<=decision[availability.notna()]).all()
    # Keep selected source dates to re-expire balances/flows between quarterly updates.
    period_ends=provenance.drop_duplicates(['cik','quarter','feature']).set_index(['cik','quarter','feature']).period_end
    smoothed=close.apply(causal_savgol)
    momentum=pd.DataFrame({t:momentum_signals(smoothed[t]).momentum_score for t in names})
    returns=close.pct_change(fill_method=None)
    dollar=(close*volume).rolling(60,min_periods=55).median()
    enough=close.rolling(60,min_periods=1).count()>=55
    historical_identity=identity.eq('provider_issuer_and_share_identity_match')
    # Full smoothing + 252-horizon history required, no listing-date invention.
    eligibility=enough&(close>=3)&(dollar>=1e6)&historical_identity&momentum.notna()
    quarterly={q:g.set_index('ticker').copy() for q,g in matrix.groupby('quarter')}
    expiries={}
    for q,frame in quarterly.items():
        source=populated[populated.quarter.eq(q)].drop_duplicates(['cik','feature']).copy()
        source['expires']=pd.to_datetime(source.period_end,errors='coerce')+pd.Timedelta(days=400)
        exp=source.pivot(index='cik',columns='feature',values='expires').reindex(frame.cik)
        exp.index=frame.index
        cols=[col for col in exp if not col.startswith(('pjm_','ferc_')) and 'candidate' not in col
              and 'disclosed' not in col and 'guidance' not in col and col in frame]
        expiries[q]=exp[cols]
    target_rows=[];signal_rows=[];component_rows=[];lineage_rows=[]
    dates=calendar[calendar>=pd.Timestamp('2024-01-01')]
    for date in dates:
        di=calendar.get_loc(date);signal_date=calendar[di-1]
        formation_quarter=str(signal_date.to_period('Q')-1) if not signal_date.is_quarter_end else str(signal_date.to_period('Q'))
        # Latest ENDED calendar quarter (not the current incomplete quarter).
        current_period=signal_date.to_period('Q')
        formation_quarter=str(current_period if signal_date>=current_period.end_time.normalize() else current_period-1)
        frame=quarterly[formation_quarter].reindex(names).copy()
        allowed=eligibility.loc[signal_date]
        exp=expiries[formation_quarter].reindex(names)
        frame[exp.columns]=frame[exp.columns].mask(exp<signal_date)
        frame=frame.loc[allowed].copy()
        old=quarterly.get(str(pd.Period(formation_quarter,freq='Q')-2))
        fundamental,components=overlay(frame,old)
        fundamental=fundamental.reindex(names)
        f=fundamental.fundamental_score
        m=momentum.loc[signal_date]
        strength=f.clip(lower=0)*m.clip(lower=0)
        strength=strength.where(allowed,0).fillna(0)
        hist=returns.loc[:signal_date].tail(20)
        weights,predicted=risk_weights(strength,hist)
        # PJM is a common macro series; a positive change scales total risk down.
        # No invented company-specific power exposure is implied.
        snapshot=quarterly[formation_quarter]
        change=snapshot.pjm_rto_capacity_price_change_vs_previous_auction.dropna()
        increase=max(0,float(change.iloc[0])) if len(change) else 0.
        power_scale=1/(1+min(increase,1.))
        macro_scale=.5 if date in macro_days else 1.
        weights*=power_scale*macro_scale
        target_rows.append(weights.rename(date))
        for t in names:
            signal_rows.append({'date':date,'signal_date':signal_date,'formation_quarter':formation_quarter,
                                'ticker':t,'eligible':bool(allowed[t]),'fundamental_score':f.get(t),
                                'momentum_score':m[t],'target_weight':weights[t],
                                'observed_groups':fundamental.observed_groups.get(t),
                                'predicted_portfolio_volatility_before_risk_cuts':predicted,
                                'power_risk_scale':power_scale,'macro_event_scale':macro_scale})
        # Quarterly component/source audit: don't duplicate the entire ledger daily.
        if date==dates[0] or formation_quarter!=last_quarter:
            component_rows.append(components.assign(formation_quarter=formation_quarter,signal_date=signal_date))
            selected=provenance[provenance.quarter.eq(formation_quarter)].copy()
            lineage_rows.append(selected)
        last_quarter=formation_quarter
    targets=pd.DataFrame(target_rows).reindex(columns=names)
    targets.index=pd.DatetimeIndex(targets.index)
    signals=pd.DataFrame(signal_rows)
    signals.to_csv(OUT/'signals.csv',index=False)
    targets.to_csv(OUT/'target_weights.csv',index_label='date')
    component_audit=pd.concat(component_rows,ignore_index=True)
    component_audit.to_csv(OUT/'overlay_components.csv',index=False)
    component_audit.groupby('component').agg(scored_rows=('ranked_component','count'),
                                             audit_rows=('ticker','size')).to_csv(OUT/'component_coverage.csv')
    pd.concat(lineage_rows,ignore_index=True).drop_duplicates().to_csv(OUT/'source_lineage.csv',index=False)
    summaries=[];all_daily=[];all_trades=[];all_holdings=[]
    for phase,start,end in [('development_2024','2024-01-01','2024-12-31'),
                            ('chronological_test','2025-01-01','2026-08-31')]:
        run_dates=dates[(dates>=start)&(dates<=end)]
        for scenario,bps in [('base_10bp',10),('stress_50bp',50)]:
            daily,trades,holdings,warning=simulate(close,opens,identity,dividend,rf,run_dates,targets,bps)
            label={'phase':phase,'scenario':scenario,'strategy':'smoothed_momentum_fundamental_overlay'}
            summaries.append(label|performance(daily,rf,warning))
            all_daily.append(daily.assign(**label));all_trades.append(trades.assign(**label));all_holdings.append(holdings.assign(**label))
        # Passive buy-and-hold comparator uses only initial historical eligibility.
        first_signal=calendar[calendar.get_loc(run_dates[0])-1]
        initial=eligibility.loc[first_signal]
        benchmark_targets=targets*0
        benchmark_targets.loc[run_dates[0],initial]=1/int(initial.sum())
        daily,trades,holdings,warning=simulate(close,opens,identity,dividend,rf,run_dates,benchmark_targets,10,benchmark=True)
        label={'phase':phase,'scenario':'base_10bp','strategy':'passive_initial_eligible_software_basket'}
        summaries.append(label|performance(daily,rf,warning))
        all_daily.append(daily.assign(**label));all_trades.append(trades.assign(**label));all_holdings.append(holdings.assign(**label))
    summary=pd.DataFrame(summaries)
    summary.to_csv(OUT/'summary.csv',index=False)
    daily=pd.concat(all_daily,ignore_index=True); daily.to_csv(OUT/'daily.csv',index=False)
    test_base=daily[(daily.phase=='chronological_test')&(daily.scenario=='base_10bp')&
                    (daily.strategy=='smoothed_momentum_fundamental_overlay')]
    test_base[['price_pnl','dividend_pnl','interest_pnl','execution_cost']].sum().rename(
        'contribution_in_initial_capital_units').to_csv(OUT/'test_accounting_attribution.csv')
    pd.concat(all_trades,ignore_index=True).to_csv(OUT/'trades.csv',index=False)
    pd.concat(all_holdings,ignore_index=True).to_csv(OUT/'holdings.csv',index=False)
    # Hash source and definitions before interpreting returns; no optimized variants.
    manifest={'inputs_sha256':hashes,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'signal_helper_sha256':hashlib.sha256((BASE/'smoothed_momentum_signals.py').read_bytes()).hexdigest(),
              'group_weights':GROUP_WEIGHTS,'smoothing':{'window':21,'degree':2,'causal_endpoint_only':True},
              'horizons':[21,63,168,252],'fusion':'max(F,0) * max(M,0), long-only',
              'missingness':'Missing groups neutral in fixed weighted sum, disclosed as missing; need >=2 quality components and >=2 groups',
              'vol_target':.10,'trailing_vol_covariance_sessions':20,'max_target_leverage':2.5,'max_target_name_weight':.10,
              'risk_cuts':'50% macro event-day risk; PJM risk scale 1/(1+clipped positive auction price change)',
              'execution':'previous-close signals, next-session open, daily rebalance; scheduled final close liquidation',
              'financing':'daily factor risk-free proxy, cash accrues; debt pays proxy plus 2% annual spread',
              'dividends':'cached split-adjusted USD cash dividends for positions held before ex-date; inventory not independently exhaustive',
              'excluded':['unqualified historical federal award amounts/counts','unavailable historical FedRAMP transitions',
                          'uncertified legacy event counts','duplicate absolute-dollar growth deltas already represented by normalized growth',
                          'PJM cap-hit/shortfall sparse fields (audited but not scored)'],
              'not_original_pitch':'observed PaymentsToDevelopSoftware cash proxy replaces unavailable ASC350-40 additions; broad observable overlay replaces missing federal specialization',
              'macro_calendar_limits':'current official historical schedules; original schedule vintages assumed. CPI reduction at open cannot protect pre-open announcement gaps',
              'selection':'fixed rules, no test-based tuning; later historical data previously inspected, not fresh holdout',
              'price_identity_and_actions':'coarse provider review, split-adjusted price basis; unresolved requested fills or held marks stop replay; no fabricated terminal price'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    fig,ax=plt.subplots(figsize=(11,6))
    for (strategy,scenario),g in daily[daily.phase=='chronological_test'].groupby(['strategy','scenario']):
        ax.plot(g.date,g.nav,label=strategy+' / '+scenario)
    ax.set(title='Standalone smoothed momentum with observed fundamental overlay',ylabel='Growth of $1')
    ax.grid(alpha=.25);ax.legend(fontsize=8);fig.autofmt_xdate();fig.tight_layout();fig.savefig(OUT/'equity.png',dpi=160);plt.close(fig)
    lines=['# Standalone smoothed momentum + observed fundamental overlay','',
           'One strategy, no passive blend and no post-result tuning. This is a research adaptation of the proposed federal-software strategy: historical FedRAMP transitions and federal-contract vintages are unavailable/withheld, so the overlay uses observable company financials and the added infrastructure signals instead. It does not validate a government-contract alpha thesis.','',
           '## Rules','',
           'Causal 21-session, degree-2 Savitzky–Golay endpoint fits; 21/63/168/252-session sign ensemble. Four agreeing signs get multiplier 1; three get .5, applied to the mean sign (three positive/one negative yields .25). Positive momentum is multiplied by the positive fundamental score. Long-only; no signal means cash.','',
           'Fundamental groups: quality 35%, software cash investment 20%, physical investment/guidance 15%, leases 10%, cloud disclosures 10%, FERC/text candidates 10%. Each group averages separately normalized cross-sectional component ranks; ranks need five observations, ties use average ranks. Missing groups remain missing and contribute neutral to fixed-weight fusion. Require two quality components and two observed groups. Investment is hypothesized positive, liability burden and stock compensation negative; these are assumptions, not learned relationships.','',
           'Coverage check: numeric CapEx guidance and all cloud-disclosure components had fewer than five eligible observations per audited snapshot, so they did not affect the scored portfolio. They remain explicit missing components rather than fabricated observations. FERC candidate counts, software cash investment, CapEx/PP&E and leases did contribute where eligible. See component_coverage.csv for actual scored counts.','',
           'Software cash investment uses PaymentsToDevelopSoftware cash intensity and its two-quarter snapshot growth; it does not establish ASC350-40 scope or government feature development. Physical investment uses CapEx and PP&E growth/intensity. Lease growth/assets/additions indicate possible expansion; liability/payment burdens are negative. Cloud contract and expense horizons are ranked separately, never summed as comparable spending. Sparse guidance/cloud fields can be present but remain unranked. FERC/text candidates are weak disclosure-attention proxies, not confirmed projects, PPA capacity, or contract amounts.','',
           'Last completed quarterly snapshots are used only after quarter-end; financial cells additionally expire 400 days after economic period end. Signals at previous close execute next open, with actual share/cash accounting. Liquidity uses previous 60 sessions, >=55 bars, median dollar volume >=$1m, last price >=$3, and provider identity match; full momentum history is required.','',
           'Daily inverse 20-session volatility weights are scaled using the same trailing covariance to a 10% portfolio volatility target, then capped at 2.5x target leverage and 10% per issuer. Scores influence eligibility and relative weights; normalization does not retain their absolute magnitude as an additional portfolio exposure cut. Caps and risk cuts can leave realized volatility below target; gaps can exceed it. Positive PJM auction price changes reduce total exposure by up to half, without claiming measured issuer power exposure. CPI/FOMC event-day target exposure is halved.','',
           'Base execution cost is 10bp per traded dollar, stress is 50bp. Cash earns the factor risk-free proxy; borrowing pays that proxy plus 2% annually. Cached USD cash dividends are included on held shares, but corporate action/dividend inventories and executable liquidity remain incompletely certified. A missing requested fill, held price, or identity stops the replay; incomplete paths cannot be interpreted as full-period returns.','',
           '## Accounting interpretation','',
           'Base chronological evaluation attribution in initial-capital units: '+
           ', '.join(f'{col}: {test_base[col].sum():.2%}' for col in ['price_pnl','dividend_pnl','interest_pnl','execution_cost'])+
           '. Execution costs are deductions. A positive total return with negative stock price P&L does not establish profitable stock selection.','',
           '## Results','',
           '| Period | Strategy | Costs | Status | Return | Annualized | Sharpe | Max drawdown | Realized vol |',
           '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in summaries:
        fmt=lambda x:'n/a' if x is None else f'{x:.2%}'
        lines.append(f"| {row['phase']} | {row['strategy']} | {row['scenario']} | {row['status']} | {fmt(row.get('total_return'))} | {fmt(row.get('annualized_return'))} | {row.get('sharpe',float('nan')):.2f} | {fmt(row.get('max_drawdown'))} | {fmt(row.get('realized_volatility'))} |")
    lines+=['','## Limits and sources','',
            'Fixed present-day 168-issuer universe has survivorship bias; CIK is not a trading-security identifier. Original historical schedule vintages are not certified, and current calendars include revised release dates. CPI releases precede the stock-market open; event-day open reductions do not avoid the overnight announcement gap. Dates after August 31, 2026 are excluded because stored factor/risk-free data ends there. 2022–2023 is warm-up, 2024 is reported separately, and 2025–August 2026 is chronological evaluation. These later dates were inspected in earlier research, so this is not an unseen holdout.','',
            'Calendar sources: [Federal Reserve](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), [BLS 2024](https://www.bls.gov/schedule/2024/), [BLS 2025](https://www.bls.gov/schedule/2025/), [BLS 2026](https://www.bls.gov/schedule/2026/). Daily input provenance and field scope are retained in source_lineage.csv and the canonical matrix README.','',
            'Reproduce with `venv/Scripts/python.exe data/packaged_software/backtest_smoothed_overlay.py`. Results, holdings, trades, signals and weights are saved alongside this report. Existing matrices/results are unchanged.']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(summary.drop(columns='warning').to_string(index=False))
    for row in summaries:
        if row.get('warning'): print(row['phase'],row['strategy'],row['warning'])
    assert all(hashlib.sha256((BASE.parents[1]/p).read_bytes()).hexdigest()==h for p,h in hashes.items())


if __name__=='__main__': main()
