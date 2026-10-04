"""Audit canonical prices, EPSS and publication integrity. No source data repairs or score inflation."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
BASE=HERE/'extracts'
OUT=BASE/'quality_audit'


def normalize_cik(value):
    text=str(value).strip()
    if not re.fullmatch(r'\d+(?:\.0+)?',text): return None
    digits=text.split('.')[0].lstrip('0') or '0'
    return digits.zfill(10) if len(digits)<=10 and digits!='0' else None


def main():
    OUT.mkdir(exist_ok=True)
    targets=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str)
    company=pd.read_csv(BASE/'company_coverage/company_coverage_168.csv',dtype=str).fillna('')
    prices=pd.read_csv(BASE/'company_coverage/daily_bars_reviewed.csv',dtype={'cik':str}).sort_values(['ticker','date'])
    expected=targets.set_index('ticker').cik.map(normalize_cik).to_dict()
    invalid=(prices[['open','high','low','close']].isna().any(axis=1) |
             prices[['open','high','low','close']].le(0).any(axis=1) |
             prices.high.lt(prices[['open','close','low']].max(axis=1)-1e-8) |
             prices.low.gt(prices[['open','close','high']].min(axis=1)+1e-8) |
             prices.volume.isna() | prices.volume.lt(0))
    normalized=prices.cik.map(normalize_cik)
    missing_cik=normalized.isna()
    mismatch=normalized.notna() & normalized.ne(prices.ticker.map(expected))
    prices['close_to_prior_close_change']=prices.groupby('ticker').close.pct_change(fill_method=None)
    prices['elapsed_calendar_days']=prices.groupby('ticker').date.transform(lambda s:pd.to_datetime(s).diff().dt.days)
    calendar_index={day:i for i,day in enumerate(sorted(prices.date.unique()))}
    positions=prices.date.map(calendar_index)
    adjacent=positions.groupby(prices.ticker).diff().eq(1)
    prices['adjacent_observed_session']=adjacent
    prices['adjacent_observed_session_return']=prices.close_to_prior_close_change.where(adjacent)
    prices['return_interval_status']='adjacent_observed_universe_sessions_not_certified_exchange_calendar'
    prices.loc[~adjacent,'return_interval_status']='first_observation_or_nonadjacent_sessions_no_one_session_return'
    prices.to_csv(OUT/'prices_with_return_interval_checks.csv',index=False)
    extreme=prices.close_to_prior_close_change.abs().gt(.5)
    prices['price_integrity_status']='checks_pass_corporate_actions_total_return_and_daily_identity_history_not_fully_verified'
    prices.loc[extreme,'price_integrity_status']='large_return_requires_event_or_corporate_action_review_not_automatically_bad_data'
    prices.loc[invalid|mismatch,'price_integrity_status']='invalid_ohlcv_or_target_identity_mismatch'
    prices[extreme|invalid|mismatch].to_csv(OUT/'price_event_review_queue.csv',index=False)
    # Observed dates are a diagnostic, not an exchange calendar or proof of missing data.
    observed_dates=sorted(prices.date.unique()); gaps=[]; coverage=[]
    for ticker,g in prices.groupby('ticker'):
        first,last=g.date.min(),g.date.max()
        missing=sorted(set(d for d in observed_dates if first<=d<=last)-set(g.date))
        for day in missing: gaps.append({'ticker':ticker,'date':day,'status':'no_bar_on_date_observed_for_other_targets_halt_listing_calendar_or_data_review_needed'})
        status=company.loc[company.ticker.eq(ticker),'price_identity_status'].iloc[0]
        coverage.append({'ticker':ticker,'cik':expected[ticker],'price_rows':len(g),'first_date':first,'last_date':last,
                         'identity_status':status,'invalid_ohlcv_rows':int(invalid.loc[g.index].sum()),
                         'large_return_review_rows':int(extreme.loc[g.index].sum()),
                         'absent_dates_within_observed_universe_calendar':len(missing),
                         'total_return_certified':False})
    pd.DataFrame(coverage).to_csv(OUT/'price_quality_by_company.csv',index=False)
    pd.DataFrame(gaps,columns=['ticker','date','status']).to_csv(OUT/'price_absent_date_candidates.csv',index=False)
    epss=pd.read_csv(BASE/'company_coverage/company_epss_monthly_with_coverage_status.csv',dtype={'cik':str})
    probability_fields=['mean_product_cve_epss','median_product_cve_epss','max_product_cve_epss','score_coverage_fraction']
    invalid_epss=sum(int(((epss[f]<0)|(epss[f]>1)).sum()) for f in probability_fields)
    count_error=epss.scored_cve_count.gt(epss.eligible_cve_count)
    unavailable=epss.coverage_status.eq('snapshot_unavailable_no_numeric_imputation')
    imputation=epss.loc[unavailable,probability_fields].notna().any(axis=1)
    statuses=[]
    for ticker,g in epss.groupby('ticker'):
        statuses.append({'ticker':ticker,'cik':expected[ticker],'month_status_rows':len(g),
                         'months_with_numeric_score':int(g.max_product_cve_epss.notna().sum()),
                         'missing_snapshot_months':int(g.coverage_status.eq('snapshot_unavailable_no_numeric_imputation').sum()),
                         'historical_company_attribution_certified':False,
                         'use_status':'dated_CVE_probabilities_for_retrospective_research_current_mapping_is_not_historical_knowledge_proof'})
    pd.DataFrame(statuses).to_csv(OUT/'epss_quality_by_company.csv',index=False)
    hash_checks=[]
    for directory,manifest_name,key in [('company_coverage','coverage_manifest.json','sha256'),('infrastructure_evidence','publication_manifest.json','sha256'),('property_activity','collection_manifest.json','output_sha256'),('financial_quality','audit.json','output_sha256')]:
        manifest=json.loads((BASE/directory/manifest_name).read_text())
        for name,digest in manifest.get(key,{}).items():
            path=BASE/directory/name
            match=path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==digest
            hash_checks.append({'directory':directory,'filename':name,'hash_matches_published_manifest':match})
    pd.DataFrame(hash_checks).to_csv(OUT/'publication_hash_checks.csv',index=False)
    finance=json.loads((BASE/'financial_quality/audit.json').read_text())
    property_manifest=json.loads((BASE/'property_activity/collection_manifest.json').read_text())
    dividends=pd.read_csv(BASE/'backtest_inputs/dividends.csv')
    checks={'audited_at_utc':datetime.now(timezone.utc).isoformat(),'target_companies':len(targets),
            'price_rows':len(prices),'price_duplicate_keys':int(prices.duplicated(['ticker','date']).sum()),
            'invalid_ohlcv_rows':int(invalid.sum()),'price_target_CIK_mismatches':int(mismatch.sum()),
            'price_rows_missing_target_CIK':int(missing_cik.sum()),
            'weekend_price_rows':int(pd.to_datetime(prices.date).dt.dayofweek.ge(5).sum()),
            'large_close_change_review_rows':int(extreme.sum()),'absent_date_candidates':len(gaps),
            'nonadjacent_close_pairs_not_published_as_one_session_returns':int((~adjacent & prices.close_to_prior_close_change.notna()).sum()),
            'price_identity_status_counts':company.price_identity_status.value_counts().to_dict(),
            'dividend_rows':len(dividends),'dividend_duplicate_ids':int(dividends.id.duplicated().sum()),
            'dividend_companies':dividends.ticker.nunique(),'total_return_certified':False,
            'epss_month_status_rows':len(epss),'epss_duplicate_company_month_keys':int(epss.duplicated(['ticker','score_date']).sum()),
            'epss_out_of_range_probability_cells':invalid_epss,'epss_scored_count_exceeds_eligible_rows':int(count_error.sum()),
            'epss_missing_snapshot_rows_improperly_filled':int(imputation.sum()),
            'epss_numeric_scored_company_months':int(epss.max_product_cve_epss.notna().sum()),
            'historical_company_EPSS_attribution_certified':False,
            'publication_hash_checks':len(hash_checks),'publication_hash_failures':sum(not r['hash_matches_published_manifest'] for r in hash_checks),
            'financial_checks':{k:v for k,v in finance.items() if k not in ['source_companyfacts_sha256','output_sha256','reasons']},
            'property_checks':property_manifest['publication'],
            'unresolved_priority_items':['Financial accounting-basis review for withheld observations.',
                'Remaining price identity, adjustment, dividend completeness and extreme-event review.',
                'Historical availability of company-to-CVE mappings.',
                'Property/AI/cloud entity and event interpretation; candidates are not confirmed costs.'],
            'scope':'Current canonical financial, price, EPSS, infrastructure and property extracts. Other auxiliary networks, ownership, news and options data are not certified by this audit.'}
    (OUT/'audit.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    text='# Dataset quality audit\n\n'+json.dumps(checks,indent=2)+'\n\nChecks distinguish structural/source consistency from historical knowledge, accounting scope and independent verification. A flagged large return is a review candidate, not an automatic bad-data finding. Absent dates use the observed universe calendar, not a certified exchange calendar. Dividend data is partial and does not certify total-return coverage. Financial quality filtering reduces coverage; original files are unchanged.\n'
    (OUT/'REPORT.md').write_text(text,encoding='utf-8')
    print(json.dumps({k:v for k,v in checks.items() if k not in ['financial_checks','property_checks','price_identity_status_counts','unresolved_priority_items','scope']},indent=2))


if __name__=='__main__': main()
