"""Review histories preceding reported listing dates for ticker reuse."""
import json
import urllib.parse
from pathlib import Path
import pandas as pd
from recover_dataset_gaps import get_json
from sec_common import env_value

HERE=Path(__file__).resolve().parent
OUT=HERE/'extracts/company_coverage'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cache=OUT/'listing_reference_cache'; cache.mkdir(exist_ok=True)
    prices=pd.read_csv(HERE/'extracts/gap_recovery/daily_bars_with_verified_aliases.csv')
    companies=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str).set_index('ticker')
    details=pd.read_csv(HERE/'output/ticker_details.csv',dtype=str).set_index('ticker')
    key=env_value('MASSIVE_API_KEY')
    reviews=[]; excluded=[]
    def reference(symbol,date):
        url=f'https://api.massive.com/v3/reference/tickers/{urllib.parse.quote(symbol)}?date={date}'
        file=cache/f'{symbol}_{date}.json'
        d=json.loads(file.read_text()) if file.exists() else get_json(url,key)
        file.write_text(json.dumps(d),encoding='utf-8')
        return d.get('results',{}),url
    def target_prefix(group,issuer,first_identity):
        ordered=group.sort_values('date'); dates=ordered.date.tolist(); urls=[]
        def matches(i):
            try:
                d,url=reference(ordered.iloc[i].source_ticker,dates[i]); urls.append(url)
                cik=str(d.get('cik','')).lstrip('0')
                return cik==issuer or (not cik and bool(first_identity.get('share_class_figi')) and d.get('share_class_figi')==first_identity.get('share_class_figi'))
            except Exception:
                return False
        lo,hi=0,len(dates)-1
        while hi-lo>1:
            mid=(lo+hi)//2
            if matches(mid): lo=mid
            else: hi=mid
        # Extra anchors test the assumed single transition before retaining a prefix.
        anchors=sorted(set([0,lo]+[round(lo*i/8) for i in range(1,8)]))
        if not all(matches(i) for i in anchors):
            return ordered.iloc[:0],urls
        return ordered.iloc[:lo+1],urls
    for ticker,group in prices.groupby('ticker'):
        first=group.sort_values('date').iloc[0]
        listing=details.loc[ticker,'list_date']
        references=[]; urls=[]; error=''
        try:
            for symbol,date in [(first.source_ticker,first.date),(ticker,group.date.max())]:
                url=f'https://api.massive.com/v3/reference/tickers/{urllib.parse.quote(symbol)}?date={date}'
                urls.append(url); file=cache/f'{symbol}_{date}.json'
                r,_=reference(symbol,date); references.append(r)
        except Exception as e:
            error=f'{type(e).__name__}:{getattr(e,"code","")}'
        status='prelisting_history_requires_review'; count=0
        if len(references)==2:
            a,b=references; issuer=companies.loc[ticker,'cik'].lstrip('0')
            old=str(a.get('cik','')).lstrip('0'); new=str(b.get('cik','')).lstrip('0')
            if new and new!=issuer:
                status='latest_price_issuer_differs_from_target_CIK_history_quarantined'
                bad=group.copy(); bad['exclusion_reason']=status
                if old==issuer:
                    prefix,checks=target_prefix(group,issuer,a); urls.extend(checks)
                    if len(prefix):
                        bad=bad.drop(prefix.index)
                        status='historical_target_issuer_prefix_retained_later_ticker_reuse_quarantined'
                excluded.append(bad); count=len(bad); prices=prices.drop(bad.index)
            elif isinstance(listing,str) and ((a.get('type') and b.get('type') and a['type']!=b['type']) or (old and new==issuer and old!=issuer)):
                status='different_security_or_issuer_before_listing_quarantined'
                bad=group[group.date<listing].copy(); bad['exclusion_reason']=status
                excluded.append(bad); count=len(bad)
                prices=prices.drop(bad.index)
            elif a.get('share_class_figi') and a.get('share_class_figi')==b.get('share_class_figi'):
                status='provider_issuer_and_share_identity_match' if old==issuer and new==issuer else 'same_share_class_issuer_fields_incomplete_requires_SEC_review'
            elif old==issuer and new==issuer:
                status='issuer_matches_share_class_or_corporate_action_requires_review'
            else:
                status='issuer_identity_fields_missing_requires_review'
        reviews.append({'ticker':ticker,'first_price_date':first.date,'list_date':listing,'status':status,
                        'old_name':references[0].get('name','') if references else '',
                        'new_name':references[1].get('name','') if len(references)==2 else '',
                        'old_cik':references[0].get('cik','') if references else '',
                        'new_cik':references[1].get('cik','') if len(references)==2 else '',
                        'excluded_bars':count,'error':error,'sources':';'.join(urls)})
    pd.DataFrame(reviews).to_csv(OUT/'price_listing_review.csv',index=False)
    if excluded:
        pd.concat(excluded,ignore_index=True).to_csv(OUT/'price_identity_exclusions.csv',index=False)
    else:
        pd.DataFrame(columns=list(prices.columns)+['exclusion_reason']).to_csv(OUT/'price_identity_exclusions.csv',index=False)
    prices.to_csv(OUT/'daily_bars_reviewed.csv',index=False)
    print(pd.DataFrame(reviews).status.value_counts().to_dict())
    print(f'{sum(r["excluded_bars"] for r in reviews)} bars quarantined; {len(prices)} retained')


if __name__=='__main__':
    main()
