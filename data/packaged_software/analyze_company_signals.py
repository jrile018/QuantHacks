"""Exploratory price, fundamental and disclosure relationships in the stored universe.

Run with venv/Scripts/python.exe. No downloads or credentials; source CSVs untouched.
Outputs are research diagnostics, not a trading backtest or causal estimates.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXTRACTS = ROOT / 'data' / 'extracts'
SPLIT = pd.Timestamp('2025-01-01')
MIN_CROSS_SECTION = 25
SEED = 1682022


def spearman(x, y):
    a = pd.DataFrame({'x': x, 'y': y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(a) < 3 or a.x.nunique() < 2 or a.y.nunique() < 2:
        return np.nan
    return a.x.rank().corr(a.y.rank())


def bh_adjust(values):
    p = np.asarray(values, dtype=float)
    out = np.full(len(p), np.nan)
    idx = np.flatnonzero(np.isfinite(p))
    order = idx[np.argsort(p[idx])]
    if len(order):
        adjusted = p[order] * len(order) / np.arange(1, len(order) + 1)
        out[order] = np.minimum(1, np.minimum.accumulate(adjusted[::-1])[::-1])
    return out


def uncertainty(values, lag=3):
    """HAC SE and sign randomization in blocks of three observed monthly diagnostics."""
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 8:
        return np.nan, np.nan, np.nan
    u = a - a.mean()
    lrv = np.dot(u, u) / len(a)
    for k in range(1, min(lag, len(a)-1) + 1):
        lrv += 2 * (1 - k/(lag+1)) * np.dot(u[k:], u[:-k]) / len(a)
    se = np.sqrt(max(lrv, 0) / len(a))
    t = a.mean()/se if se > 0 else np.nan
    rng = np.random.default_rng(SEED)
    blocks = np.arange(len(a)) // 3
    signs = rng.choice([-1, 1], size=(10000, blocks.max()+1))[:, blocks]
    null = np.mean(signs*a, axis=1)
    # Include equal endpoint statistics despite strided/contiguous sum roundoff.
    threshold=max(abs(a.mean())-1e-12,0)
    p = (1 + np.sum(np.abs(null) >= threshold)) / (len(null)+1)
    return se, t, p


def write_csv(df, path):
    df.to_csv(path, index=False, float_format='%.8g')


def load_prices(companies, out):
    raw = pd.read_csv(EXTRACTS/'prices/daily_bars.csv', parse_dates=['date'])
    duplicates = raw.duplicated(['ticker', 'date'], keep=False)
    invalid = raw.close.isna() | (raw.close <= 0)
    issues = raw.loc[duplicates | invalid, ['ticker', 'date', 'close', 'volume']].copy()
    issues['issue'] = np.where(issues.close.isna() | (issues.close <= 0),
                               'nonpositive_or_missing_close', 'duplicate_ticker_date')
    write_csv(issues, out/'price_invalid_rows.csv')
    if duplicates.any():
        raise ValueError('Duplicate ticker/date bars require source review')
    clean = raw.loc[~invalid].copy()
    price = clean.pivot(index='date', columns='ticker', values='close').sort_index()
    volume = clean.pivot(index='date', columns='ticker', values='volume').reindex_like(price)
    returns = price.pct_change(fill_method=None)
    extreme = returns.stack().rename('price_return').reset_index()
    write_csv(extreme.loc[extreme.price_return.abs() > .5], out/'large_daily_moves.csv')
    coverage = []
    for c in companies.itertuples():
        s = price[c.ticker].dropna()
        train = price.loc[price.index < SPLIT, c.ticker].dropna()
        dv = (price[c.ticker]*volume[c.ticker]).loc[price.index < SPLIT].dropna()
        flags = []
        if len(train) < 400: flags.append('insufficient_training_history')
        if dv.median() < 1e6: flags.append('training_median_dollar_volume_below_1m')
        if len(train) and train.median() < 1: flags.append('training_median_price_below_1')
        if 'warrant' in str(c.name).lower(): flags.append('warrant_not_common_stock')
        if len(s) and s.index.min() > pd.Timestamp('2022-02-01'):
            flags.append('no_early_2022_bars_current_ticker_or_new_listing')
        coverage.append(dict(ticker=c.ticker, name=c.name, valid_bars=len(s),
                             first_date=s.index.min(), last_date=s.index.max(),
                             training_bars=len(train), training_median_dollar_volume=dv.median(),
                             training_median_close=train.median(), flags=';'.join(flags),
                             pair_training_eligible=not any(x in flags for x in
                             ['insufficient_training_history', 'training_median_dollar_volume_below_1m',
                              'training_median_price_below_1', 'warrant_not_common_stock'])))
    coverage = pd.DataFrame(coverage)
    write_csv(coverage, out/'price_quality_and_coverage.csv')
    return price, volume, returns, coverage, len(raw), int(invalid.sum())


def prepare_fundamentals(out):
    f = pd.read_csv(EXTRACTS/'company_metrics/fundamentals_quarterly.csv',
                    dtype={'cik':str}, parse_dates=['period_end','available_date_conservative'])
    lineage = pd.read_csv(EXTRACTS/'company_metrics/quarterly_metric_sources.csv', dtype={'cik':str})
    lineage['cik'] = lineage.cik.str.zfill(10)
    f['cik'] = f.cik.str.zfill(10)
    quality = lineage.pivot(index=['cik','period_end'], columns=['basis','metric'], values='quality')
    quality.index = pd.MultiIndex.from_arrays([quality.index.get_level_values(0),
                                               pd.to_datetime(quality.index.get_level_values(1))])
    f = f.set_index(['cik','period_end'])
    strict = {}
    for metric in ['revenue','rd_expense','sales_marketing','stock_comp','gross_profit',
                   'cost_of_revenue','operating_income','operating_cash_flow','physical_asset_purchases']:
        q = quality.get(('quarter',metric), pd.Series(dtype=str)).reindex(f.index)
        strict[metric] = f['q_'+metric].where(q.isin(['reported','same_filing_difference']))
    revenue = strict['revenue'].where(strict['revenue'] > 0)
    for metric, name in [('rd_expense','rd_share_reported_q'),('sales_marketing','sm_share_reported_q'),
                         ('stock_comp','sbc_share_reported_q'),('operating_income','operating_margin_reported_q'),
                         ('operating_cash_flow','ocf_margin_reported_q'),
                         ('physical_asset_purchases','capex_share_reported_q')]:
        f[name] = strict[metric]/revenue
    gross = strict['gross_profit'].combine_first(revenue-strict['cost_of_revenue'])
    f['gross_margin_reported_q'] = gross/revenue
    f['revenue_growth_reported_yoy'] = np.nan
    for cik, group in f.groupby(level=0):
        for idx in group.index:
            end = idx[1]
            prev = group.index[(end-group.index.get_level_values(1)).days.to_numpy() >= 350]
            prev = [x for x in prev if (end-x[1]).days <= 380]
            if prev and pd.notna(revenue.loc[idx]):
                p = min(prev, key=lambda x: abs((end-x[1]).days-365))
                if pd.notna(revenue.loc[p]) and revenue.loc[p] > 0:
                    f.loc[idx,'revenue_growth_reported_yoy'] = revenue.loc[idx]/revenue.loc[p]-1
    assets = f.total_assets.where(f.total_assets > 0)
    f['goodwill_share_assets'] = f.goodwill/assets
    f['ppe_share_assets'] = f.ppe_net/assets
    f['lease_share_assets'] = f.operating_lease_rou/assets
    # Comparisons of recurring quarterly revenue with backlog/commitment stocks, not spending.
    f['rpo_to_annualized_reported_revenue'] = f.rpo/(4*revenue)
    f['obligations_to_annualized_reported_revenue'] = f.purchase_obligations/(4*revenue)
    f['log_reported_quarter_revenue'] = np.log(revenue)
    for field in ['rd_pct_rev','sm_pct_rev','sbc_pct_rev','gross_margin',
                  'physical_capex_pct_rev','fcf_physical_capex_margin']:
        f['exploratory_ttm_'+field] = f[field]
    features = [x for x in f.columns if x.endswith('_reported_q') or x.endswith('_reported_yoy') or
                x in ['goodwill_share_assets','ppe_share_assets','lease_share_assets',
                      'rpo_to_annualized_reported_revenue','obligations_to_annualized_reported_revenue',
                      'log_reported_quarter_revenue'] or x.startswith('exploratory_ttm_')]
    f = f.reset_index()
    write_csv(f[['cik','ticker','period_end','available_date_conservative']+features],
              out/'quarterly_research_features.csv')
    return f, features


def build_panel(price, volume, returns, companies, f, features, out):
    # Complete calendar months only, with an observed close in the last three market sessions.
    last = price.index.max()
    cutoffs = price.groupby(price.index.to_period('M')).apply(lambda g:g.index.max()).tolist()
    cutoffs = [d for d in cutoffs if d.to_period('M') < last.to_period('M')]
    closes = price.loc[cutoffs].copy()
    monthly = closes.pct_change(fill_method=None)
    future1 = closes.shift(-1)/closes-1
    future3 = closes.shift(-3)/closes-1
    company_lookup = companies.set_index('ticker')
    company_names = company_lookup.name.to_dict()
    company_ciks = company_lookup.cik.to_dict()
    financial_groups = {ticker:g.sort_values('period_end') for ticker,g in f.groupby('ticker')}
    rows=[]
    news = pd.read_csv(EXTRACTS/'company_news/news_articles.csv',
                       usecols=['ticker','article_id','published_utc','candidate_category'])
    news['date'] = pd.to_datetime(news.published_utc, utc=True).dt.tz_localize(None).dt.normalize()
    epss = pd.read_csv(EXTRACTS/'epss_monthly/company_epss_history.csv', parse_dates=['score_date'])
    epss_groups = {ticker:g.sort_values('score_date') for ticker,g in epss.groupby('ticker')}
    flags_path=ROOT/'data/packaged_software/output/tenk_text_flags.csv'
    flags=pd.read_csv(flags_path,parse_dates=['filing_date']) if flags_path.exists() else pd.DataFrame()
    flag_groups={ticker:g.sort_values('filing_date') for ticker,g in flags.groupby('ticker')} if len(flags) else {}
    flag_features={'exploratory_10k_ai_mentions_log':'artificial_intelligence',
                   'exploratory_10k_cloud_mentions_log':'cloud_provider_mention',
                   'exploratory_10k_going_concern':'substantial_doubt_going_concern',
                   'exploratory_10k_material_weakness':'material_weakness_identified'}
    dollar_volume=price*volume
    for i, cutoff in enumerate(cutoffs):
        past = price.loc[:cutoff].tail(60)
        liquidity = dollar_volume.loc[:cutoff].tail(60).median()
        eligible = (past.count() >= 50) & (liquidity >= 1e6) & (price.loc[cutoff] >= 1)
        n = news[(news.date > cutoff-pd.Timedelta(days=30)) & (news.date < cutoff.normalize())]
        counts = n.groupby('ticker').size()
        candidates = n[n.candidate_category.notna()].groupby('ticker').size()
        for ticker in price.columns:
            if 'warrant' in str(company_names[ticker]).lower(): continue
            if not eligible[ticker]: continue
            fg=financial_groups.get(ticker,f.iloc[:0])
            history=fg[(fg.available_date_conservative <= cutoff) &
                       (fg.period_end >= cutoff-pd.Timedelta(days=240))]
            row=dict(ticker=ticker,cik=company_ciks[ticker],month=cutoff,
                     forward_price_return_1m=future1.loc[cutoff,ticker],
                     forward_price_return_3m=future3.loc[cutoff,ticker],
                     outcome_end_1m=cutoffs[i+1] if i+1<len(cutoffs) else pd.NaT,
                     outcome_end_3m=cutoffs[i+3] if i+3<len(cutoffs) else pd.NaT,
                     news_attention_log=np.log1p(counts.get(ticker,0)),
                     announcement_candidate_share=(candidates.get(ticker,0)/counts[ticker]
                                                   if counts.get(ticker,0)>=5 else np.nan),
                     past_60d_volatility=returns.loc[:cutoff,ticker].tail(60).std()*np.sqrt(252),
                     median_dollar_volume_60d=liquidity[ticker])
            for feature in features: row[feature]=np.nan
            row['financial_period_end']=pd.NaT; row['financial_available_date']=pd.NaT
            if len(history):
                latest=history.iloc[-1]
                row.update({x:latest[x] for x in features})
                row['financial_period_end']=latest.period_end
                row['financial_available_date']=latest.available_date_conservative
            row['momentum_12m_skip_1m']=np.nan
            if i>=12:
                p0=closes.iloc[i-12][ticker]; p1=closes.iloc[i-1][ticker]
                if pd.notna(p0) and p0>0: row['momentum_12m_skip_1m']=p1/p0-1
            eg=epss_groups.get(ticker,epss.iloc[:0])
            e=eg[(eg.score_date < cutoff.normalize()) &
                 (eg.score_date >= cutoff-pd.Timedelta(days=45))]
            row['exploratory_epss_max']=e.iloc[-1].max_product_cve_epss if len(e) else np.nan
            row['exploratory_epss_high_cve_log']=np.log1p(e.iloc[-1].high_epss_cve_count) if len(e) else np.nan
            flag_history=flag_groups.get(ticker)
            latest_flag=None
            if flag_history is not None:
                flag_history=flag_history[(flag_history.filing_date < cutoff.normalize()) &
                                           (flag_history.filing_date >= cutoff-pd.Timedelta(days=450))]
                if len(flag_history): latest_flag=flag_history.iloc[-1]
            for field,source in flag_features.items():
                value=latest_flag[source] if latest_flag is not None else np.nan
                row[field]=(np.log1p(value) if field.endswith('_log') else float(value>0)) if pd.notna(value) else np.nan
            future=returns.loc[returns.index>cutoff,ticker].head(21)
            row['forward_21d_volatility']=future.std()*np.sqrt(252) if future.count()>=18 else np.nan
            row['volatility_outcome_end']=future.index.max() if future.count()>=18 else pd.NaT
            rows.append(row)
    panel=pd.DataFrame(rows)
    all_features=features+['news_attention_log','announcement_candidate_share','past_60d_volatility',
                          'momentum_12m_skip_1m','exploratory_epss_max','exploratory_epss_high_cve_log']+list(flag_features)
    # Cohort-relative return: equal-weight eligible companies with observable horizon outcomes.
    for h in [1,3]:
        field=f'forward_price_return_{h}m'
        panel[f'forward_cohort_excess_{h}m']=panel[field]-panel.groupby('month')[field].transform('mean')
    assert not (panel.financial_available_date > panel.month).any()
    write_csv(panel,out/'monthly_research_panel.csv')
    return panel,all_features


def signal_tests(panel,features,out):
    monthly=[]
    for feature in features:
        for target,endfield in [('forward_cohort_excess_1m','outcome_end_1m'),
                                ('forward_cohort_excess_3m','outcome_end_3m'),
                                ('forward_21d_volatility','volatility_outcome_end')]:
            for month,g in panel.groupby('month'):
                d=g[[feature,target,endfield]].dropna()
                if len(d)<MIN_CROSS_SECTION or d[feature].nunique()<2: continue
                if d[feature].nunique()<5 and d[feature].value_counts().min()<5: continue
                if d[feature].nunique()==2:
                    high=d.loc[d[feature]==d[feature].max(),target].mean()
                    low=d.loc[d[feature]==d[feature].min(),target].mean()
                else:
                    bottom,top=d[feature].quantile([.2,.8])
                    high=d.loc[d[feature]>=top,target].mean() if top>bottom else np.nan
                    low=d.loc[d[feature]<=bottom,target].mean() if top>bottom else np.nan
                outcome_end=d[endfield].max()
                sample='train' if month<SPLIT and outcome_end<SPLIT else ('test' if month>=SPLIT else 'purged')
                monthly.append(dict(feature=feature,target=target,month=month,n=len(d),
                                    rank_ic=spearman(d[feature],d[target]),high_minus_low=high-low,
                                    sample=sample,outcome_end=outcome_end))
    m=pd.DataFrame(monthly); summary=[]
    for (feature,target),g in m.groupby(['feature','target']):
        train=g[g['sample']=='train']; test=g[g['sample']=='test']
        se,t,p=uncertainty(test.rank_ic)
        direction=np.sign(train.rank_ic.mean()) if len(train) else np.nan
        summary.append(dict(feature=feature,target=target,train_months=len(train),test_months=len(test),
                            train_mean_rank_ic=train.rank_ic.mean(),test_mean_rank_ic=test.rank_ic.mean(),
                            test_ic_hac_se=se,test_ic_hac_t=t,test_block_sign_p=p,
                            train_high_minus_low=train.high_minus_low.mean(),
                            test_high_minus_low=test.high_minus_low.mean(),
                            test_spread_using_train_direction=direction*test.high_minus_low.mean(),
                            test_direction_consistency=(direction*test.rank_ic>0).mean(),
                            median_test_companies=test.n.median(),
                            evidence_tier='exploratory' if feature.startswith('exploratory_') else 'reported_or_price_metadata',
                            stable_direction=bool(len(train)>=12 and len(test)>=12 and
                                                  train.rank_ic.mean()*test.rank_ic.mean()>0)))
    s=pd.DataFrame(summary)
    s['test_bh_q']=bh_adjust(s.test_block_sign_p)
    s['passes_exploratory_fdr_10pct']=s.test_bh_q<=.10
    s=s.sort_values(['target','test_bh_q','feature'])
    write_csv(m,out/'monthly_signal_diagnostics.csv');write_csv(s,out/'feature_signal_summary.csv')
    return s,m


def metric_relationships(panel,features,out):
    rows=[]
    financial=[x for x in features if not x.startswith('exploratory_') and
               x not in ['news_attention_log','announcement_candidate_share','past_60d_volatility',
                         'momentum_12m_skip_1m']]
    for a,b in itertools.combinations(financial,2):
        correlations=[]; counts=[]
        for month,g in panel.groupby('month'):
            d=g[[a,b]].dropna()
            if len(d)>=MIN_CROSS_SECTION and d[a].nunique()>=5 and d[b].nunique()>=5:
                correlations.append((month,spearman(d[a],d[b])));counts.append(len(d))
        if len(correlations)<12: continue
        train=[v for date,v in correlations if date<SPLIT];test=[v for date,v in correlations if date>=SPLIT]
        d=panel[['ticker',a,b]].dropna()
        within=d[[a,b]]-d.groupby('ticker')[[a,b]].transform('mean')
        rows.append(dict(metric_a=a,metric_b=b,months=len(correlations),median_companies=np.median(counts),
                         mean_monthly_cross_section_rank_corr=np.mean([v for _,v in correlations]),
                         train_mean_rank_corr=np.mean(train) if train else np.nan,
                         test_mean_rank_corr=np.mean(test) if test else np.nan,
                         pooled_within_company_rank_corr=spearman(within[a],within[b]),
                         interpretation='association; repeated observations and shared denominators; no causal test'))
    r=pd.DataFrame(rows).sort_values('mean_monthly_cross_section_rank_corr',key=lambda s:s.abs(),ascending=False)
    write_csv(r,out/'fundamental_metric_relationships.csv')
    return r


def pairs_analysis(price,returns,coverage,panel,out):
    eligible=coverage.loc[coverage.pair_training_eligible,'ticker'].tolist()
    train=returns.loc[returns.index<SPLIT,eligible]
    test=returns.loc[returns.index>=SPLIT,eligible]
    # Leave-one-out industry factor, coefficients estimated only in 2022-24.
    sums=returns[eligible].sum(axis=1,min_count=1); counts=returns[eligible].count(axis=1)
    residual=returns[eligible].copy()*np.nan;betas={}
    for ticker in eligible:
        market=(sums-returns[ticker])/(counts-1)
        x=pd.DataFrame({'r':returns[ticker],'m':market}).dropna()
        fit=x[x.index<SPLIT]
        if len(fit)<400:continue
        coef=np.linalg.lstsq(np.column_stack([np.ones(len(fit)),fit.m]),fit.r,rcond=None)[0]
        residual[ticker]=returns[ticker]-coef[0]-coef[1]*market;betas[ticker]=coef[1]
    raw_train=train.corr(min_periods=400);raw_test=test.corr(min_periods=200)
    res_train=residual.loc[residual.index<SPLIT].corr(min_periods=400)
    res_test=residual.loc[residual.index>=SPLIT].corr(min_periods=200)
    names=coverage.set_index('ticker').name.to_dict()
    # Training-window fundamental profiles, not future company metrics.
    fields=['rd_share_reported_q','sm_share_reported_q','gross_margin_reported_q',
            'operating_margin_reported_q','goodwill_share_assets','ppe_share_assets']
    profiles=panel[panel.month<SPLIT].groupby('ticker')[fields].median()
    profiles=(profiles-profiles.median())/(profiles.quantile(.75)-profiles.quantile(.25)).replace(0,np.nan)
    profile_values=profiles.reindex(eligible).to_numpy()
    observed_train=train.notna().to_numpy(dtype=np.int64)
    observed_test=test.notna().to_numpy(dtype=np.int64)
    overlap_train=observed_train.T@observed_train
    overlap_test=observed_test.T@observed_test
    log_values=np.log(price.reindex(columns=eligible).to_numpy())
    train_dates=np.asarray(price.index<SPLIT)
    rows=[]
    for ai,bi in itertools.combinations(range(len(eligible)),2):
        a,b=eligible[ai],eligible[bi]
        ntrain=int(overlap_train[ai,bi]);ntest=int(overlap_test[ai,bi])
        c=raw_train.loc[a,b]
        if not np.isfinite(c) or ntrain<400:continue
        row=dict(ticker_a=a,ticker_b=b,name_a=names[a],name_b=names[b],train_overlap_days=ntrain,
                 test_overlap_days=ntest,train_return_corr=c,test_return_corr=raw_test.loc[a,b],
                 train_sector_residual_corr=res_train.loc[a,b],test_sector_residual_corr=res_test.loc[a,b],
                 train_sector_beta_a=betas.get(a),train_sector_beta_b=betas.get(b))
        difference=profile_values[ai]-profile_values[bi]
        difference=difference[np.isfinite(difference)]
        row['fundamental_profile_metrics']=len(difference)
        row['train_fundamental_distance']=np.sqrt((difference**2).mean()) if len(difference)>=3 else np.nan
        # A training-fitted log spread is only a diagnostic: no formal cointegration claim.
        row.update(train_log_hedge_beta=np.nan,train_spread_ar1=np.nan,train_half_life_days=np.nan,
                   test_spread_std_vs_train=np.nan,test_spread_mean_shift_in_train_sd=np.nan)
        if c>=.45 and ntest>=200:
            observed=np.isfinite(log_values[:,ai]) & np.isfinite(log_values[:,bi])
            tr=log_values[observed & train_dates][:,[ai,bi]]
            te=log_values[observed & ~train_dates][:,[ai,bi]]
            coef=np.linalg.lstsq(np.column_stack([np.ones(len(tr)),tr[:,1]]),tr[:,0],rcond=None)[0]
            spread=tr[:,0]-coef[0]-coef[1]*tr[:,1];s_test=te[:,0]-coef[0]-coef[1]*te[:,1]
            phi=np.linalg.lstsq(np.column_stack([np.ones(len(spread)-1),spread[:-1]]),spread[1:],rcond=None)[0][1]
            row.update(train_log_hedge_beta=coef[1],train_spread_ar1=phi,
                       train_half_life_days=-np.log(2)/np.log(phi) if 0<phi<1 else np.nan,
                       test_spread_std_vs_train=s_test.std(ddof=1)/spread.std(ddof=1),
                       test_spread_mean_shift_in_train_sd=(s_test.mean()-spread.mean())/spread.std(ddof=1))
        rows.append(row)
    result=pd.DataFrame(rows)
    result['training_correlation_candidate']=(result.train_return_corr>=.5)&(result.train_sector_residual_corr>=.2)
    result['survives_holdout_correlation']=(result.test_overlap_days>=200)&(result.test_return_corr>=.4)&(result.test_sector_residual_corr>=.2)
    result=result.sort_values('train_sector_residual_corr',ascending=False)
    write_csv(result,out/'all_pair_diagnostics.csv')
    shortlist=result[result.training_correlation_candidate].head(25)
    write_csv(shortlist,out/'training_selected_pairs.csv')
    return result,shortlist,len(eligible)


def charts(signals,relationships,shortlist,price,out):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(15,6),layout='constrained')
    s=signals[(signals.target=='forward_cohort_excess_1m') & (signals.train_months>=12) &
              (signals.test_months>=12) & ~signals.feature.str.startswith('exploratory_')].copy()
    s=s.sort_values('train_mean_rank_ic',key=lambda v:v.abs(),ascending=False).head(10)
    y=np.arange(len(s));axes[0].barh(y-.17,s.train_mean_rank_ic,height=.32,label='2022-24 discovery')
    axes[0].barh(y+.17,s.test_mean_rank_ic,height=.32,label='2025-26 temporal holdout')
    axes[0].set_yticks(y, [x.replace('_reported_q','').replace('_',' ') for x in s.feature],fontsize=9)
    axes[0].axvline(0,color='gray',lw=.7);axes[0].invert_yaxis();axes[0].legend(fontsize=8)
    axes[0].set_title('Metric rank vs next-month price return');axes[0].set_xlabel('Mean monthly Spearman correlation')
    p=shortlist.head(10);y=np.arange(len(p))
    axes[1].barh(y-.17,p.train_sector_residual_corr,height=.32,label='2022-24 discovery')
    axes[1].barh(y+.17,p.test_sector_residual_corr,height=.32,label='2025-26 temporal holdout')
    axes[1].set_yticks(y,[a+' / '+b for a,b in zip(p.ticker_a,p.ticker_b)])
    axes[1].invert_yaxis();axes[1].legend(fontsize=8);axes[1].set_title('Pairs after removing software-sector movement')
    axes[1].set_xlabel('Daily residual-return correlation')
    fig.savefig(out/'signals_and_pairs.png',dpi=160);plt.close(fig)
    r=relationships.head(10).iloc[::-1]
    fig,ax=plt.subplots(figsize=(12,6),layout='constrained')
    ax.barh(range(len(r)),r.mean_monthly_cross_section_rank_corr,color='#365d8d')
    ax.set_yticks(range(len(r)),[a.replace('_reported_q','').replace('_',' ')+' / '+b.replace('_reported_q','').replace('_',' ')
                              for a,b in zip(r.metric_a,r.metric_b)],fontsize=8)
    ax.set_title('Fundamental relationships across companies');ax.set_xlabel('Mean monthly Spearman correlation')
    ax.axvline(0,color='gray',lw=.7);fig.savefig(out/'metric_relationships.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    risk=signals[(signals.target=='forward_21d_volatility') & (signals.test_months>=12) &
                 (signals.train_months>=12) & ~signals.feature.str.startswith('exploratory_')]
    risk=risk.sort_values('train_mean_rank_ic',key=lambda x:x.abs(),ascending=False).head(7)
    y=np.arange(len(risk));ax=axes[0,0]
    ax.barh(y-.17,risk.train_mean_rank_ic,height=.32,label='2022-24')
    ax.barh(y+.17,risk.test_mean_rank_ic,height=.32,label='2025-26')
    ax.set_yticks(y,[x.replace('_reported_q','').replace('_',' ') for x in risk.feature],fontsize=8)
    ax.invert_yaxis();ax.axvline(0,color='gray',lw=.7);ax.legend(fontsize=8)
    ax.set_title('Metrics vs next 21-day volatility');ax.set_xlabel('Mean monthly rank correlation')
    for ax,(a,b) in zip([axes[0,1],axes[1,0],axes[1,1]],[('PAYC','PCTY'),('QLYS','TENB'),('CDNS','SNPS')]):
        logs=np.log(price[[a,b]]).dropna();train=logs[logs.index<SPLIT]
        coef=np.linalg.lstsq(np.column_stack([np.ones(len(train)),train[b]]),train[a],rcond=None)[0]
        train_spread=train[a]-coef[0]-coef[1]*train[b]
        z=(logs[a]-coef[0]-coef[1]*logs[b]-train_spread.mean())/train_spread.std()
        ax.plot(z.index,z,lw=1,color='#365d8d');ax.axvline(SPLIT,color='#cc7a19',ls='--',lw=1)
        ax.axhline(0,color='gray',lw=.6);ax.axhline(2,color='gray',ls=':',lw=.6);ax.axhline(-2,color='gray',ls=':',lw=.6)
        ax.set_title(a+' / '+b+' fixed training hedge');ax.set_ylabel('Spread / training standard deviation')
        ax.tick_params(axis='x',labelrotation=25,labelsize=8)
    fig.savefig(out/'risk_and_pair_spreads.png',dpi=160);plt.close(fig)


def table(df,columns,n=8):
    d=df[columns].head(n)
    lines=['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']
    for row in d.itertuples(index=False,name=None):
        lines.append('| '+' | '.join(f'{v:.3f}' if isinstance(v,(float,np.floating)) and pd.notna(v) else str(v) for v in row)+' |')
    return '\n'.join(lines)


def inventory_and_snapshot(companies,f,out):
    """Review remaining stored datasets without assigning today's attributes to the past."""
    inventory=[]
    directories=[ROOT/'data/packaged_software/output']+[p for p in EXTRACTS.iterdir() if p.is_dir() and p.name!='_cache']
    current_files={'company_factors.csv','ticker_details.csv','company_identity.csv','company_lei.csv',
                   'company_gleif_parents.csv','company_gleif_children.csv','company_auditors.csv'}
    aggregates={'8k_item_by_company.csv','item_105_by_company.csv','company_summary.csv','filing_signals.csv',
                'kev_by_company.csv','federal_register_by_company.csv','sec_enforcement_by_company.csv',
                'warn_ca_by_company.csv'}
    for folder in directories:
        for p in folder.glob('*.csv'):
            try:
                frame=pd.read_csv(p,low_memory=False)
                date_fields=[c for c in frame if c in ['date','filed','filed_date','filing_date','publication_date',
                            'published_utc','available_date_conservative','score_date','date_added','notice_date','start_date']]
                numeric=[c for c in frame.select_dtypes(include='number') if c not in ['cik','sic','sic_code']]
                interpretation=('current_snapshot_not_historical_predictor' if p.name in current_files else
                                'full_window_aggregate_not_historical_predictor' if p.name in aggregates else
                                'dated_records_require_source_and_mapping_review' if date_fields else
                                'no_verified_publication_timestamp')
                if p.name=='contract_awards.csv':interpretation='award_start_date_not_public_availability_or_supplier_spending'
                if p.name=='financial_gaps_annual.csv':interpretation='reported_annual_values_use_filed_date_not_fiscal_year_end'
                inventory.append(dict(path=str(p.relative_to(ROOT)),rows=len(frame),columns=len(frame.columns),
                                      company_count=frame.ticker.nunique() if 'ticker' in frame else np.nan,
                                      date_columns=';'.join(date_fields),numeric_columns=';'.join(numeric),
                                      interpretation=interpretation))
            except pd.errors.EmptyDataError:
                inventory.append(dict(path=str(p.relative_to(ROOT)),rows=0,interpretation='empty'))
    write_csv(pd.DataFrame(inventory),out/'stored_data_inventory.csv')
    p=ROOT/'data/packaged_software/output/ticker_details.csv'
    if not p.exists():return pd.DataFrame()
    details=pd.read_csv(p,usecols=['ticker','total_employees','market_cap'])
    latest=f.sort_values('period_end').groupby('ticker').tail(1)
    snapshot=details.merge(latest,on='ticker',how='left')
    cols=['market_cap','total_employees','ttm_revenue','rd_share_reported_q',
          'sm_share_reported_q','gross_margin_reported_q','operating_margin_reported_q',
          'goodwill_share_assets','ppe_share_assets','revenue_growth_reported_yoy']
    rows=[]
    for a,b in itertools.combinations(cols,2):
        d=snapshot[[a,b]].replace([np.inf,-np.inf],np.nan).dropna()
        if len(d)>=25:
            rows.append(dict(metric_a=a,metric_b=b,companies=len(d),spearman_corr=spearman(d[a],d[b]),
                             interpretation='latest snapshot and mixed accounting dates; descriptive only, no historical return test'))
    result=pd.DataFrame(rows).sort_values('spearman_corr',key=lambda x:x.abs(),ascending=False)
    write_csv(result,out/'latest_snapshot_metric_relationships.csv')
    return result


def conditional_relationships(panel,features,out):
    """Monthly partial rank associations after size, volatility and momentum controls."""
    rows=[]
    controls=['past_60d_volatility','log_reported_quarter_revenue','momentum_12m_skip_1m']
    targets={'forward_cohort_excess_1m':'outcome_end_1m','forward_21d_volatility':'volatility_outcome_end'}
    for feature in features:
        if feature in controls:continue
        for target,endfield in targets.items():
            for date,g in panel.groupby('month'):
                d=g[[feature,target,endfield]+controls].replace([np.inf,-np.inf],np.nan).dropna()
                if len(d)<25 or d[feature].nunique()<2:continue
                if d[feature].nunique()<5 and d[feature].value_counts().min()<5:continue
                x=d[controls].rank(pct=True).to_numpy()
                x=np.column_stack([np.ones(len(x)),x])
                a=d[feature].rank(pct=True).to_numpy();b=d[target].rank(pct=True).to_numpy()
                ra=a-x@np.linalg.lstsq(x,a,rcond=None)[0];rb=b-x@np.linalg.lstsq(x,b,rcond=None)[0]
                corr=np.corrcoef(ra,rb)[0,1] if ra.std()>1e-10 and rb.std()>1e-10 else np.nan
                sample='train' if date<SPLIT and d[endfield].max()<SPLIT else ('test' if date>=SPLIT else 'purged')
                rows.append(dict(feature=feature,target=target,month=date,sample=sample,n=len(d),partial_rank_corr=corr))
    diagnostics=pd.DataFrame(rows);summary=[]
    for (feature,target),g in diagnostics.groupby(['feature','target']):
        tr=g[g['sample']=='train'];te=g[g['sample']=='test'];se,t,p=uncertainty(te.partial_rank_corr)
        summary.append(dict(feature=feature,target=target,train_months=len(tr),test_months=len(te),
                            train_mean_partial_rank_corr=tr.partial_rank_corr.mean(),
                            test_mean_partial_rank_corr=te.partial_rank_corr.mean(),
                            test_hac_se=se,test_hac_t=t,test_block_sign_p=p,median_test_companies=te.n.median(),
                            controls=';'.join(controls)))
    summary=pd.DataFrame(summary);summary['test_bh_q']=bh_adjust(summary.test_block_sign_p)
    summary=summary.sort_values(['target','test_bh_q'])
    write_csv(diagnostics,out/'monthly_conditional_diagnostics.csv')
    write_csv(summary,out/'conditional_signal_summary.csv')
    return summary


def add_research_findings(out,signals,relationships,shortlist,conditional):
    one=signals[(signals.target=='forward_cohort_excess_1m') & (signals.test_months>=12)]
    three=signals[(signals.target=='forward_cohort_excess_3m') & (signals.test_months>=12)]
    risk=signals[(signals.target=='forward_21d_volatility') & signals.feature.isin(
        ['past_60d_volatility','operating_margin_reported_q','log_reported_quarter_revenue',
         'rd_share_reported_q','exploratory_ttm_sbc_pct_rev'])]
    pair_examples=shortlist[shortlist.apply(lambda row:(row.ticker_a,row.ticker_b) in
                              [('PAYC','PCTY'),('QLYS','TENB'),('CRM','NOW'),('CDNS','SNPS')],axis=1)]
    focused=relationships[relationships.apply(lambda row:(row.metric_a,row.metric_b) in
                        [('rd_share_reported_q','sbc_share_reported_q'),
                         ('sm_share_reported_q','sbc_share_reported_q'),
                         ('rd_share_reported_q','revenue_growth_reported_yoy'),
                         ('rd_share_reported_q','operating_margin_reported_q')],axis=1)]
    increment=conditional[conditional.target=='forward_21d_volatility']
    findings=f'''## Findings

**Risk is more predictable here than return direction.** Among tests with at least 12 holdout months,
{int((one.test_bh_q<=.10).sum())} next-month and {int((three.test_bh_q<=.10).sum())} three-month return tests
pass the exploratory 10% false-discovery threshold. R&D spending, AI/cloud mentions and EPSS do not establish
a usable directional return signal in this sample. AI announcement candidate-share tests have only four
useful holdout months and are underpowered; absence of evidence is not evidence of no effect.

Selected volatility associations (mean monthly rank correlations):

{table(risk,['feature','train_mean_rank_ic','test_mean_rank_ic','test_bh_q','test_months'])}

Higher past volatility predicts higher next-month volatility. Higher operating margins and revenue size
accompany lower future volatility. R&D intensity and stock-compensation intensity accompany higher future
volatility. The stock-compensation TTM input has unverified cross-filing accounting flags.
After controlling for past volatility, size and momentum, {int((increment.test_bh_q<=.10).sum())} volatility
tests pass 10% FDR in the conditional family. These controls reduce the case for independent new signals.
The two multiple-testing families are corrected separately ({len(signals)} main tests, {len(conditional)} conditional tests).

Selected fundamental relationships:

{table(focused,['metric_a','metric_b','mean_monthly_cross_section_rank_corr','test_mean_rank_corr','months'])}

R&D and sales/marketing intensity accompany stock-compensation intensity. R&D has a modest positive
association with current YoY revenue growth. The negative relationship between expenses and operating margin
partly reflects the accounting identity and common revenue denominator; it is not independent evidence that
cutting R&D improves the business. These are contemporaneous comparisons, not forecasts of next year's growth.

Pairs to investigate from the discovery-selected list:

{table(pair_examples,['ticker_a','ticker_b','train_return_corr','test_return_corr','test_sector_residual_corr','test_spread_std_vs_train','test_spread_mean_shift_in_train_sd'])}

PAYC/PCTY and QLYS/TENB retained substantial residual correlation and relatively similar spread scale in
the holdout. CRM/NOW retained correlation but its spread mean shifted. CDNS/SNPS retained strong correlation,
yet its spread standard deviation grew about 3.18 times and its mean shifted 5.76 training standard deviations.
That makes a fixed mean-reversion hedge much less convincing. Correlated returns alone do not establish cointegration.
No transaction-cost, short-borrow, execution or portfolio backtest was performed.

'''
    report=out/'REPORT.md'
    content=report.read_text(encoding='utf-8')
    if '## Findings\n' not in content:
        content=content.replace('## Price and coverage audit\n',findings+'## Price and coverage audit\n',1)
    report.write_text(content,encoding='utf-8')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'data/processed/company_signal_research')
    args=ap.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    companies=pd.read_csv(ROOT/'data/packaged_software/packaged_software_companies.csv',dtype={'cik':str})
    companies.cik=companies.cik.str.zfill(10)
    price,volume,returns,coverage,nraw,invalid=load_prices(companies,out)
    print('Price audit finished:',nraw,'rows;',invalid,'invalid closes',flush=True)
    f,features=prepare_fundamentals(out);panel,features=build_panel(price,volume,returns,companies,f,features,out)
    print('Monthly point-in-time panel:',len(panel),'rows',flush=True)
    signals,monthly=signal_tests(panel,features,out)
    relationships=metric_relationships(panel,features,out)
    pairs,shortlist,neligible=pairs_analysis(price,returns,coverage,panel,out)
    snapshot=inventory_and_snapshot(companies,f,out)
    conditional=conditional_relationships(panel,features,out)
    charts(signals,relationships,shortlist,price,out)
    passing=signals[(signals.target=='forward_cohort_excess_1m') & signals.stable_direction &
                    signals.passes_exploratory_fdr_10pct]
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
             [EXTRACTS/'prices/daily_bars.csv',EXTRACTS/'company_metrics/fundamentals_quarterly.csv',
              EXTRACTS/'company_metrics/quarterly_metric_sources.csv',EXTRACTS/'company_news/news_articles.csv',
              EXTRACTS/'epss_monthly/company_epss_history.csv',
              ROOT/'data/packaged_software/packaged_software_companies.csv',
              ROOT/'data/packaged_software/output/tenk_text_flags.csv',
              ROOT/'data/packaged_software/output/ticker_details.csv'] if p.exists()}
    manifest=dict(universe_companies=len(companies),raw_price_rows=nraw,invalid_close_rows_excluded=invalid,
                  price_start=str(price.index.min().date()),price_end=str(price.index.max().date()),
                  monthly_panel_rows=len(panel),monthly_panel_companies=panel.ticker.nunique(),
                  monthly_panel_end=str(panel.month.max().date()),feature_count=len(features),signal_tests=len(signals),
                  conditional_tests=len(conditional),
                  pair_eligible_companies=neligible,pair_tests=len(pairs),training_selected_pairs=len(shortlist),
                  training_end='2024-12-31',test_start='2025-01-01',random_seed=SEED,source_sha256=sources,
                  limitations=['Current surviving universe; historical ticker aliases not spliced into prices',
                   'Price returns split-adjusted only, dividends omitted',
                   'No formal cointegration test or costs/borrow/capital backtest',
                   'Exploratory temporal holdout examined across all features; not an untouched final test',
                   'TTM and EPSS exploratory features preserve unverified accounting/mapping limitations',
                   'AI/news candidates unreviewed; ticker association does not establish internal adoption',
                   'No direct cloud-spend estimate; missing public spending stays unavailable',
                   'Block-sign p-values are exploratory and assume symmetric blocks of three observed monthly diagnostics'])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    forecast=signals[(signals.target=='forward_cohort_excess_1m') & (signals.train_months>=12) & (signals.test_months>=12)]
    forecast=forecast.sort_values('train_mean_rank_ic',key=lambda v:v.abs(),ascending=False)
    report=f'''# Packaged software signal research

Stored universe: {len(companies)} companies. Prices: {price.index.min().date()} to {price.index.max().date()}.
Analysis uses complete months through {panel.month.max().date()}. Discovery: 2022-24. Temporal holdout: 2025 onward.

## Price and coverage audit

{nraw:,} stored bars; {invalid} nonpositive/missing closes excluded. {neligible} liquid companies with at least
400 training observations qualify for pair screening. Monthly feature tests include {panel.ticker.nunique()}
companies at some point, subject to trailing 60-day dollar volume >= $1m, price >= $1 and at least 50 observed bars.
Warrants are excluded. No missing prices are forward-filled. Short current-ticker histories, missing 2022 data,
large daily moves and low liquidity are recorded in the audit tables. Corporate-action/symbol gaps were not stitched.

Massive aggregates are split-adjusted, not dividend-adjusted: these are **price returns**, not total returns.
Source: [Massive adjustment documentation](https://massive.com/knowledge-base/article/is-massives-stock-data-adjusted-for-splits-or-dividends).

## Metrics and next-month returns

Top features below are ordered by absolute discovery-period correlation, not selected using holdout returns.
Rank IC measures each month's cross-company Spearman correlation with the next month's cohort-relative price return.
Positive means higher metric values accompanied higher subsequent returns. Quintile spreads are descriptive gross
high-minus-low returns, not a portfolio backtest. Cohort excess subtracts an equal-weight software cohort return;
it is not beta-adjusted alpha. Month-end entry uses the close, with signals already public before that close.

{table(forecast,['feature','train_mean_rank_ic','test_mean_rank_ic','test_high_minus_low','test_bh_q','test_months'])}

{len(passing)} one-month tests have consistent train/test direction and exploratory FDR q <= 0.10 across all
{len(signals)} feature/target tests. This screen includes exploratory TTM/EPSS metrics; inspect evidence_tier.
Three-month return windows overlap, so interpretation relies on HAC diagnostics and blocks of three observed monthly
sign randomization rather than independent-observation p-values. All features/targets are included in BH correction.
The holdout has been inspected and cannot serve as a fresh final validation set after selecting these results.

## Fundamental relationships

{table(relationships,['metric_a','metric_b','mean_monthly_cross_section_rank_corr','train_mean_rank_corr','test_mean_rank_corr','pooled_within_company_rank_corr'])}

These are associations. Repeated monthly financial observations, common revenue denominators and firm size
can create correlations. Within-company columns remove each firm's mean but do not prove causality.
Direct quarter flows are retained only when reported or derived within the same filing. Missing values stay blank.
Quarterly ratios avoid the largely unverified cross-filing TTM basis. RPO/revenue and obligations/revenue compare
backlog/commitment stocks to annualized quarterly revenue; they are not cloud spending.

`conditional_signal_summary.csv` tests partial rank relationships after controlling for trailing volatility,
revenue size and prior 12-month momentum (skipping the last month). It reports both temporal windows and corrects
across all conditional tests. These are incremental associations, not causal effects. Conditional coverage is
smaller because all controls must be observed; the momentum control is unavailable in the first 12 months.
`latest_snapshot_metric_relationships.csv` examines current employees, market cap and latest financial metrics
as descriptive associations only. `stored_data_inventory.csv` audits all available CSV datasets and distinguishes
dated source records from current snapshots and full-window aggregates. Government award start dates do not establish
public availability or the software company's own purchases, so those totals are not treated as historical buy signals.

## Training-selected company pairs

{table(shortlist,['ticker_a','ticker_b','train_return_corr','test_return_corr','train_sector_residual_corr','test_sector_residual_corr','test_spread_std_vs_train','test_spread_mean_shift_in_train_sd'])}

Pairs require discovery raw correlation >= 0.50 and residual correlation >= 0.20, then are ranked solely by
discovery residual correlation. Residuals subtract each stock's training-fitted exposure to a leave-one-out
equal-weight liquid software cohort. Holdout coefficients are frozen. Correlation makes a research pair,
not a profitable mean-reversion trade. Log-price hedge coefficients and AR(1) half-lives are diagnostics only:
no formal cointegration test is performed. A shifted/widened holdout spread weakens a fixed hedge relationship.
The complete pair table retains failed holdout correlations; the shortlist does not silently remove them.

## Coverage limits and reproduction

Financial features use the latest accounting period already available by month-end, never period end alone,
and expire after 240 days. Availability is conservative but does not establish exact historical accounting basis.
Current universe survivorship and symbol/entity histories remain limitations. EPSS uses retrospective vendor mappings
and changing model versions; news metadata can be revised and announcement candidates are unreviewed. Zero news
records mean none retrieved in this provider window, not proof of no announcements. Cloud bills, AI contract values,
hardware bills and employee seats are not inferred from mentions. Sparse land/hosting facts remain source disclosures
and are not promoted into cross-company signals without adequate standardized coverage.

Run from the repository root:

```powershell
.\\venv\\Scripts\\python.exe data/packaged_software/analyze_company_signals.py
```

See `feature_signal_summary.csv`, `fundamental_metric_relationships.csv`, `training_selected_pairs.csv`,
`all_pair_diagnostics.csv` and `monthly_research_panel.csv` for exact results and sample sizes.
The manifest records source hashes and assumptions. Source CSVs are unchanged.
'''
    (out/'REPORT.md').write_text(report,encoding='utf-8')
    add_research_findings(out,signals,relationships,shortlist,conditional)
    print(json.dumps({k:v for k,v in manifest.items() if k not in ['source_sha256','limitations']},indent=2),flush=True)


if __name__=='__main__':
    main()
