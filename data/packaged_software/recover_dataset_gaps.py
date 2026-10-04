"""Recover public-source gaps without overwriting raw or established research data.

Historical alias bars are candidates, never automatically joined across corporate
actions. SEC-observed symbols can refer to other share classes or predecessors.
"""
import argparse
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path
import pandas as pd
from sec_common import SecClient, env_value

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE / 'extracts'
OUT = BASE / 'gap_recovery'
# Common-share alias candidates only. These remain subject to entity/class review.
ALIASES = {'XYZ':'SQ', 'CMRC':'BIGC', 'GTM':'ZI', 'CCC':'CCCS',
           'GEN':'NLOK', 'CCLD':'MTBC', 'MRDN':'GMGI', 'AIFF':'WAVD',
           'QXL':'VBIX', 'PDYN':'STRC', 'GXAI':'NFTG', 'CXAI':'KINZ', 'AISP':'BYTS'}


def get_json(url, key):
    request = urllib.request.Request(url, headers={'Authorization': f'Bearer {key}', 'User-Agent':'QuantHacks-gap-recovery/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def prepare_prices():
    p = pd.read_csv(BASE / 'prices/daily_bars.csv')
    valid = (p[['open','high','low','close']].notna().all(axis=1)
             & p[['open','high','low','close']].gt(0).all(axis=1)
             & p.high.ge(p[['open','close','low']].max(axis=1))
             & p.low.le(p[['open','close']].min(axis=1)))
    p.loc[~valid].assign(exclusion_reason='invalid_OHLC').to_csv(OUT/'excluded_price_bars.csv',index=False)
    clean = p.loc[valid].copy()
    clean.to_csv(OUT/'daily_bars_clean.csv',index=False)
    coverage = []
    for ticker, g in p.groupby('ticker'):
        cg = clean[clean.ticker.eq(ticker)]
        coverage.append({'ticker':ticker,'raw_bars':len(g),'valid_bars':len(cg),
                         'invalid_bars':len(g)-len(cg),'first_date':g.date.min(),
                         'historical_alias_candidate':ALIASES.get(ticker,''),
                         'history_status':'missing_early_history_requires_IPO_or_symbol_review' if g.date.min()>'2022-01-31' else 'starts_in_Jan_2022'})
    pd.DataFrame(coverage).to_csv(OUT/'price_gap_queue.csv',index=False)
    return {'raw_price_rows':len(p),'valid_price_rows':len(clean),'excluded_price_rows':int((~valid).sum())}


def retry_filings(log):
    path = BASE/'sec/filings_index.csv'
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    client = SecClient()
    changed = False
    for r in rows:
        local = Path(r['local_path'])
        legacy = Path('data/extracts/sec')
        if local.is_relative_to(legacy):
            local = (BASE/'sec'/local.relative_to(legacy)).relative_to(ROOT)
        target = (ROOT/local).resolve()
        if not target.is_relative_to((BASE/'sec').resolve()):
            raise ValueError('SEC document path escapes cache')
        if r['local_path'] != local.as_posix():
            r['local_path'] = local.as_posix()
            changed = True
        if r['status'] != 'failed' and target.exists():
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{r['accession'].replace('-','')}/{r['primary_document']}"
        try:
            raw = client.get(url)
            if len(raw)<100 or b'<html' not in raw.lower():
                raise ValueError('Expected a filing HTML document')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            r['status']='downloaded'
            changed=True
            log.append({'source':'SEC','ticker':r['ticker'],'status':'recovered','url':url})
        except Exception as e:
            log.append({'source':'SEC','ticker':r['ticker'],'status':'still_unavailable','error':type(e).__name__,'http_status':getattr(e,'code',None),'url':url})
    if changed:
        backup = OUT/'filings_index_before_retry.csv'
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        temporary = path.with_suffix('.csv.tmp')
        with temporary.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)


def recover_aliases(log):
    key = env_value('MASSIVE_API_KEY')
    observed=pd.read_csv(HERE/'news_ticker_aliases.csv',dtype=str)
    if not key:
        raise ValueError('MASSIVE_API_KEY is missing')
    observed = pd.read_csv(HERE/'news_ticker_aliases.csv',dtype=str)
    p = pd.read_csv(BASE/'prices/daily_bars.csv')
    universe = pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str).set_index('ticker')
    rows=[]
    cache=OUT/'alias_cache'
    cache.mkdir(exist_ok=True)
    for ticker, alias in ALIASES.items():
        evidence=observed[(observed.ticker==ticker)&(observed.alias==alias)]
        if evidence.empty:
            continue
        first=p.loc[p.ticker==ticker,'date'].min()
        if not isinstance(first,str) or first<='2022-01-31':
            continue
        end=(dt.date.fromisoformat(first)-dt.timedelta(days=1)).isoformat()
        url=f'https://api.massive.com/v2/aggs/ticker/{urllib.parse.quote(alias)}/range/1/day/2022-01-01/{end}?adjusted=true&sort=asc&limit=50000'
        file=cache/f'{alias}_2022-01-01_{end}.json'
        try:
            raw=json.loads(file.read_text()) if file.exists() else get_json(url,key)
            file.write_text(json.dumps(raw),encoding='utf-8')
            for b in raw.get('results',[]):
                rows.append({'cik':universe.loc[ticker,'cik'],'ticker':ticker,'source_ticker':alias,
                             'date':dt.datetime.fromtimestamp(b['t']/1000,dt.timezone.utc).date().isoformat(),
                             'open':b.get('o'),'high':b.get('h'),'low':b.get('l'),'close':b.get('c'),'volume':b.get('v'),
                             'mapping_status':'SEC_observed_symbol_entity_class_and_corporate_action_review_required',
                             'source_api':url,'symbol_evidence_url':evidence.iloc[0].evidence_url})
            log.append({'source':'Massive','ticker':ticker,'alias':alias,'status':'candidate_history_retrieved','rows':len(raw.get('results',[])),'url':url})
        except Exception as e:
            log.append({'source':'Massive','ticker':ticker,'alias':alias,'status':'request_failed','error':type(e).__name__,'http_status':getattr(e,'code',None)})
    pd.DataFrame(rows,columns=['cik','ticker','source_ticker','date','open','high','low','close','volume','mapping_status','source_api','symbol_evidence_url']).to_csv(OUT/'historical_alias_price_candidates.csv',index=False)


def validate_aliases(log):
    """Join only common shares with matching issuer and share-class FIGI at both dates."""
    candidates = pd.read_csv(OUT/'historical_alias_price_candidates.csv',dtype={'cik':str})
    current = pd.read_csv(OUT/'daily_bars_clean.csv')
    key = env_value('MASSIVE_API_KEY')
    observed=pd.read_csv(HERE/'news_ticker_aliases.csv',dtype=str)
    reviews=[]
    accepted=[]
    for ticker, g in candidates.groupby('ticker'):
        alias=g.source_ticker.iloc[0]
        start=g.date.min()
        first=current.loc[current.ticker.eq(ticker),'date'].min()
        urls=[]
        details=[]
        error=''
        try:
            for symbol, date in [(alias,start),(ticker,first)]:
                url=f'https://api.massive.com/v3/reference/tickers/{urllib.parse.quote(symbol)}?date={date}'
                urls.append(url)
                file=OUT/'alias_cache'/f'reference_{symbol}_{date}.json'
                d=json.loads(file.read_text()) if file.exists() else get_json(url,key)
                file.write_text(json.dumps(d),encoding='utf-8')
                details.append(d.get('results',{}))
        except Exception as e:
            error=f'{type(e).__name__}:{getattr(e,"code","")}'
        verified=False
        verification_basis=''
        if len(details)==2:
            a,b=details
            issuer=str(g.cik.iloc[0]).lstrip('0')
            ciks=[str(d.get('cik','')).lstrip('0') for d in details]
            symbols=observed[observed.cik.str.lstrip('0').eq(issuer)]
            sec_symbols={alias,ticker}.issubset(set(symbols.alias))
            identity=(all(c==issuer for c in ciks) or
                      (sec_symbols and any(c==issuer for c in ciks) and all(not c or c==issuer for c in ciks)))
            verified=(a.get('type')=='CS' and b.get('type')=='CS' and identity
                      and bool(a.get('share_class_figi')) and a.get('share_class_figi')==b.get('share_class_figi'))
            verification_basis='provider_CIK_and_common_share_FIGI_match' if all(c==issuer for c in ciks) else 'SEC_symbols_provider_CIK_and_common_share_FIGI_match'
        gap=(dt.date.fromisoformat(first)-dt.date.fromisoformat(g.date.max())).days
        if gap>7:
            verified=False
            error=error or 'gap_at_symbol_transition_exceeds_7_calendar_days'
        old_close=float(g.sort_values('date').iloc[-1]['close'])
        new_close=float(current.loc[current.ticker.eq(ticker)].sort_values('date').iloc[0]['close'])
        transition_ratio=new_close/old_close if old_close>0 else 0
        if not .5 <= transition_ratio <= 2:
            verified=False
            error=error or 'price_discontinuity_requires_split_or_corporate_action_review'
        reviews.append({'ticker':ticker,'alias':alias,'candidate_bars':len(g),
                        'mapping_status':verification_basis if verified else 'not_verified_do_not_stitch',
                        'old_cik':details[0].get('cik','') if details else '',
                        'new_cik':details[1].get('cik','') if len(details)==2 else '',
                        'old_share_class_figi':details[0].get('share_class_figi','') if details else '',
                        'new_share_class_figi':details[1].get('share_class_figi','') if len(details)==2 else '',
                        'transition_gap_days':gap,'transition_close_ratio':transition_ratio,
                        'error':error,'reference_sources':';'.join(urls)})
        if verified:
            valid=(g[['open','high','low','close']].gt(0).all(axis=1)
                   & g.high.ge(g[['open','close','low']].max(axis=1))
                   & g.low.le(g[['open','close']].min(axis=1)))
            restored=g.loc[valid].copy()
            restored['history_source']='verified_former_symbol'
            accepted.append(restored)
    current['source_ticker']=current.ticker
    current['history_source']='current_symbol'
    combined=pd.concat([current]+accepted,ignore_index=True).sort_values(['ticker','date'])
    if combined.duplicated(['ticker','date']).any():
        raise ValueError('Duplicate ticker/date in restored price history')
    combined.to_csv(OUT/'daily_bars_with_verified_aliases.csv',index=False)
    pd.DataFrame(reviews).to_csv(OUT/'alias_mapping_review.csv',index=False)
    log.append({'source':'Massive_reference','status':'alias_validation_complete','accepted_companies':sum(r['mapping_status']!='not_verified_do_not_stitch' for r in reviews),'restored_bars':sum(len(g) for g in accepted)})


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--network',action='store_true')
    ap.add_argument('--validate-aliases',action='store_true')
    args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    counts=prepare_prices()
    log=[]
    if args.validate_aliases:
        validate_aliases(log)
    elif args.network:
        retry_filings(log)
        recover_aliases(log)
    prior = OUT/'manifest.json'
    if args.validate_aliases and prior.exists():
        log = json.loads(prior.read_text()).get('requests',[]) + log
    result={'run_at':dt.datetime.now(dt.timezone.utc).isoformat(),**counts,'requests':log,
            'limitations':['No missing values imputed.','Alias bars are review candidates, not stitched investment returns.','Raw source price data preserved.']}
    (OUT/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
