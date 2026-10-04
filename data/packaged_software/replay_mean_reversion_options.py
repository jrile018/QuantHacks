"""Fixed long-call/long-put replay of equity pair signals using real historical NBBO.

No synthetic prices, no options parameter tuning, no portfolio Sharpe from sparse marks.
"""
import json
import hashlib
import urllib.parse
import urllib.error
from pathlib import Path
import numpy as np
import pandas as pd
from extract_company_news import NewsClient

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'data/packaged_software/extracts'
OUT=ROOT/'data/processed/mean_reversion'


def url(path,params):return 'https://api.massive.com'+path+'?'+urllib.parse.urlencode(params)


def quote_window(date,closing=False):
    start=pd.Timestamp(str(pd.Timestamp(date).date())+(' 15:55:00' if closing else ' 09:35:00'),tz='America/New_York')
    return start.value,(start+pd.Timedelta(minutes=5)).value


def quote(client,ticker,date,side,quantity=1,closing=False):
    start,end=quote_window(date,closing)
    data=client.page(url('/v3/quotes/'+urllib.parse.quote(ticker),
                          {'timestamp.gte':start,'timestamp.lt':end,'sort':'timestamp','order':'asc','limit':100}))
    for q in data.get('results',[]):
        bid=q.get('bid_price',-1);ask=q.get('ask_price',0);size=q.get(side+'_size',0)
        if bid>=0 and ask>0 and bid<=ask and size>=quantity and start<=q.get('sip_timestamp',0)<end:
            if side=='ask' and (bid<=0 or (ask-bid)/((ask+bid)/2)>.5):continue
            return q
    return None


def select_contract(client,ticker,kind,signal_date,entry_date):
    # Actual as-traded close is essential: split-adjusted equity bars can misidentify historical ATM strikes.
    s=str(pd.Timestamp(signal_date).date())
    data=client.page(url('/v2/aggs/ticker/'+urllib.parse.quote(ticker)+'/range/1/day/'+s+'/'+s,
                         {'adjusted':'false','limit':1}))
    if not data.get('results'):return None,'no_unadjusted_underlying_close'
    spot=data['results'][0]['c']
    e=pd.Timestamp(entry_date)
    params={'underlying_ticker':ticker,'as_of':s,'expired':'false','contract_type':kind,
            'expiration_date.gte':str((e+pd.Timedelta(days=90)).date()),
            'expiration_date.lte':str((e+pd.Timedelta(days=120)).date()),
            'strike_price.gte':spot*.95,'strike_price.lte':spot*1.05,'limit':1000}
    data=client.page(url('/v3/reference/options/contracts',params))
    if data.get('next_url'):return None,'contract_query_not_exhaustive'
    contracts=[c for c in data.get('results',[]) if c.get('shares_per_contract')==100 and not c.get('additional_underlyings')]
    if not contracts:return None,'no_standard_listed_contract'
    contract=min(contracts,key=lambda c:(c['expiration_date'],abs(c['strike_price']-spot),c['ticker']))
    contract['underlying_signal_close_unadjusted']=spot
    return contract,''


def narrative_outcome(summary):
    """Outcome sentences for the REPORT section, computed from the summary table, never fixed text."""
    signals=int(summary.signals.sum()) if len(summary) else 0
    entered=int(summary.entered.sum()) if len(summary) else 0
    closed=int(summary.closed.sum()) if len(summary) else 0
    unresolved=int(summary.unresolved_exits.sum()) if len(summary) else 0
    pnl=float(summary.closed_net_pnl_usd.sum()) if len(summary) else 0.0
    counts=f'Of {signals} signals across the variants, {entered} entered with valid quotes and {closed} closed with observed quotes.'
    exits=('No unresolved exits occurred in this run.' if unresolved==0 else
           f'{unresolved} entered trade(s) have unresolved exits, so coverage is incomplete and no complete performance claim is made.')
    if closed==0:pnl_text='No trades closed, so no P&L direction is claimed.'
    else:
        direction='made money' if pnl>0 else 'lost money' if pnl<0 else 'broke even'
        pnl_text=f'The closed subset {direction} in total ({"-" if pnl<0 else ""}${abs(pnl):,.2f} net of fees).'
    return f'{counts} {exits} {pnl_text}'


def main():
    source=pd.read_csv(OUT/'trades_oos.csv',parse_dates=['entry_date','exit_date','entry_signal_date'])
    source=source[(source.scenario=='base')&source.variant.isin(['correlated_pairs','cointegrated_pairs'])].copy()
    client=NewsClient(BASE/'_cache/options_replay')
    legs=[];records=[]
    for row in source.itertuples():
        a,b=row.tickers.split('/');kinds=['call','put'] if row.direction>0 else ['put','call']
        entry=[];status='';key=f'{row.variant}:{row.fold}:{row.trade_id}'
        for ticker,kind in zip([a,b],kinds):
            try:
                c,error=select_contract(client,ticker,kind,row.entry_signal_date,row.entry_date)
                if error:status=error;break
                q=quote(client,c['ticker'],row.entry_date,'ask')
                if q is None:status='no_usable_entry_ask';break
                quantity=min(int(10000/(q['ask_price']*100+.65)),int(q['ask_size']))
                if quantity<1:status='premium_exceeds_fixed_leg_budget';break
                entry.append((c,q,quantity))
            except urllib.error.HTTPError as exc:status=f'entry_http_{exc.code}';break
        if not status and len(entry)==2:
            if abs(entry[0][1]['sip_timestamp']-entry[1][1]['sip_timestamp'])>1e9:
                status='entry_quotes_more_than_one_second_apart'
        record=dict(source_trade_key=key,variant=row.variant,fold=row.fold,tickers=row.tickers,
                    equity_entry_date=row.entry_date,equity_exit_date=row.exit_date,
                    equity_trade_net_pnl=row.net_pnl,status=status or 'entered',premium_paid=0.0,net_pnl=np.nan)
        if not status:
            premium=sum(q['ask_price']*100*n for c,q,n in entry)
            fees=sum(.65*n for c,q,n in entry)
            record['premium_paid']=premium;record['entry_commission']=fees
            exit_value=0.;exit_fees=0.;closed=True
            for c,q,n in entry:
                try:
                    x=quote(client,c['ticker'],row.exit_date,'bid',n,closing=row.exit_reason=='scheduled_fold_close')
                except urllib.error.HTTPError as exc:x=None
                leg=dict(source_trade_key=key,contract=c['ticker'],kind=c['contract_type'],strike=c['strike_price'],
                         expiration_date=c['expiration_date'],quantity=n,underlying_signal_close_unadjusted=c['underlying_signal_close_unadjusted'],
                         entry_ask=q['ask_price'],entry_bid=q['bid_price'],entry_quote_timestamp=str(q['sip_timestamp']),
                         exit_bid=x['bid_price'] if x else np.nan,exit_ask=x['ask_price'] if x else np.nan,
                         exit_quote_timestamp=str(x['sip_timestamp']) if x else '',
                         exit_status='quoted' if x else 'unresolved_missing_exit_bid_or_depth')
                legs.append(leg)
                if x is None:closed=False
                else:exit_value+=x['bid_price']*100*n;exit_fees+=.65*n
            if closed:
                record.update(status='closed_with_observed_quotes',exit_value=exit_value,
                              net_pnl=exit_value-premium-fees-exit_fees,return_on_premium=(exit_value-premium-fees-exit_fees)/(premium+fees))
            else:record.update(status='entered_exit_unresolved',worst_case_long_premium_loss=-(premium+fees))
        records.append(record)
        print(key,record['status'],flush=True)
    frame=pd.DataFrame(records);pd.DataFrame(legs).to_csv(OUT/'options_replay_legs.csv',index=False)
    frame.to_csv(OUT/'options_replay_trades.csv',index=False)
    summaries=[]
    for variant,g in frame.groupby('variant'):
        closed=g[g.status=='closed_with_observed_quotes'];entered=g[g.status.isin(['closed_with_observed_quotes','entered_exit_unresolved'])]
        summaries.append(dict(variant=variant,signals=len(g),entered=len(entered),closed=len(closed),
                              unresolved_exits=int((g.status=='entered_exit_unresolved').sum()),
                              closed_net_pnl_usd=closed.net_pnl.sum(),closed_premium_paid_usd=closed.premium_paid.sum(),
                              closed_weighted_return_on_premium=closed.net_pnl.sum()/closed.premium_paid.sum() if len(closed) else np.nan,
                              closed_win_fraction=(closed.net_pnl>0).mean() if len(closed) else np.nan))
    summary=pd.DataFrame(summaries);summary.to_csv(OUT/'options_replay_summary.csv',index=False)
    manifest={'fixed_recipe':'long ATM call on equity long leg and long ATM put on equity short leg; never sell naked options',
              'contract_choice':'metadata as of prior signal date; earliest expiry 90-120 calendar days after entry, nearest strike to unadjusted prior close, standard 100-share contracts',
              'execution':'first valid entry ask at 09:35-09:40 New York, pair timestamps within one second; corresponding exit bid/depth; scheduled fold exits at 15:55-16:00',
              'size':'fixed maximum $10,000 premium per leg, capped at quoted ask size; $0.65/contract each side',
              'limitations':['Trade replay, not fully marked daily options portfolio; no options Sharpe or annual return',
                 'Missing entry quotes cancel both legs; missing exit quotes remain unresolved and never silently excluded from coverage',
                 'Closed-only return can have coverage bias; unresolved trades prevent a complete performance claim',
                 'Quotes are observed, fills assumed; 100-quote windows and displayed depth may miss executions',
                 'Equal-premium calls/puts are not delta neutral and inherit theta/vega exposure',
                 'No thresholds, expiries or strikes optimized on options returns',
                 'Equity exits determine exit dates; stock fills occur five minutes earlier than options replay',
                 'Expired-contract historical metadata may have revisions; no fully archived chain vintages'],
              'status_counts':frame.status.value_counts().to_dict(),'source':'Massive historical contracts, raw equity aggregates and option quotes',
              'equity_trade_source_sha256':hashlib.sha256((OUT/'trades_oos.csv').read_bytes()).hexdigest()}
    (OUT/'options_replay_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    report=OUT/'REPORT.md'
    if report.exists():
        outcome=narrative_outcome(summary)
        content=report.read_text(encoding='utf-8').split('\n## Options replay with historical quotes\n')[0]
        lines=['| Variant | Signals | Closed quoted trades | Return on premium paid |',
               '| --- | ---: | ---: | ---: |']
        for row in summary.itertuples():
            lines.append(f'| {row.variant} | {row.signals} | {row.closed} | {row.closed_weighted_return_on_premium:.2%} |')
        content+='\n## Options replay with historical quotes\n\n'+ '\n'.join(lines)+f'''

This fixed recipe buys an ATM call on the stock long leg and an ATM put on the stock short leg, with expiry
90-120 days after entry. Contract metadata is queried as of the prior signal date and ATM strikes use real
unadjusted historical stock closes. Entry quotes must have positive bid/ask, bounded relative spread and paired
timestamps within one second. Orders use observed asks, exit bids and displayed sizes, plus $0.65/contract each way.
Size is capped at $10,000 per leg and available quoted depth. Fixed recipe parameters are not optimized on options P&L.

{outcome}
The quote-qualified subset has coverage bias and is a small sample. It cannot establish the return of an
options portfolio. Missing entry quotes/listings or asynchronous quotes cancel the paired entry; missing exit
quotes remain unresolved instead of being removed from coverage. Calls/puts are equal-premium exposures, not a
delta-neutral hedge, and their performance includes theta and implied-volatility effects.
No annualized options return, Sharpe or drawdown is fabricated from sparse entry/exit observations.

See options_replay_trades.csv, options_replay_legs.csv and options_replay_manifest.json for actual prices,
quote timestamps, contracts, status reasons and sizing. The key returned 2025 historical quotes and historical
aggregate bars; the 2022 probe returned no quotes, so continuous quote coverage back to 2022 is not established.

```powershell
.\\venv\\Scripts\\python.exe data/packaged_software/replay_mean_reversion_options.py
```
'''
        report.write_text(content,encoding='utf-8')
    print(summary.to_string(index=False))


if __name__=='__main__':main()
