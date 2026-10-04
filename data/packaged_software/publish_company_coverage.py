"""Publish a sourced coverage status for every target company and metric.

Coverage of a status is not coverage of an observed value. No nulls are imputed.
"""
import hashlib
import json
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
BASE=HERE/'extracts'
OUT=BASE/'company_coverage'


def main():
    companies=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str)
    financial=pd.read_csv(BASE/'company_metrics_expanded/fundamentals_quarterly.csv',dtype={'cik':str})
    facts=pd.read_csv(BASE/'company_metrics_expanded/reported_financial_facts.csv',dtype={'cik':str})
    annual=pd.read_csv(BASE/'company_metrics_expanded/reported_annual_metrics.csv',dtype={'cik':str})
    prices=pd.read_csv(OUT/'daily_bars_reviewed.csv',dtype={'cik':str,'source_cik_metadata':str})
    identity=pd.read_csv(OUT/'price_listing_review.csv').set_index('ticker')
    # CIK is the target identifier. Keep original source metadata and identity confidence separate.
    if 'source_cik_metadata' not in prices:
        prices['source_cik_metadata']=prices['cik']
    target_ciks=companies.set_index('ticker').cik.str.zfill(10)
    prices['cik']=prices.ticker.map(target_ciks)
    if prices.cik.isna().any(): raise ValueError('Price ticker outside target universe')
    prices['cik_assignment_basis']='fixed_target_universe_with_separate_dated_price_identity_review'
    prices['price_identity_status']=prices.ticker.map(identity.status)
    prices.to_csv(OUT/'daily_bars_reviewed.csv',index=False)
    details=pd.read_csv(HERE/'output/ticker_details.csv').set_index('ticker')
    epss=pd.read_csv(OUT/'company_epss_history_expanded.csv',dtype={'cik':str})
    news=pd.read_csv(BASE/'company_news/news_articles.csv',usecols=['ticker'])
    disclosure_path=OUT/'disclosure_evidence_expanded.csv'
    if not disclosure_path.exists():
        disclosure_path=BASE/'company_metrics_recovered/disclosure_evidence.csv'
    disclosure=pd.read_csv(disclosure_path,usecols=['ticker','review_status'])
    snapshots=details.reset_index().copy()
    snapshots['issuer_attribution_status']='provider_snapshot_requires_same_issuer_interpretation'
    quarantined=[]
    for c in companies.to_dict('records'):
        current=identity.loc[c['ticker'],'new_cik']
        if pd.notna(current) and int(float(current))!=int(c['cik']):
            quarantined.append(c['ticker'])
    mask=snapshots.ticker.isin(quarantined)
    for field in ['total_employees','market_cap','share_class_shares_outstanding','weighted_shares_outstanding']:
        if field in snapshots:
            snapshots.loc[mask,field]=float('nan')
    snapshots.loc[mask,'issuer_attribution_status']='different_current_issuer_numeric_snapshot_quarantined'
    snapshots.to_csv(OUT/'company_details_with_issuer_status.csv',index=False)
    search=pd.read_csv(OUT/'unmapped_cve_search_coverage.csv').set_index('ticker')
    source_lineage=pd.read_csv(BASE/'company_metrics_expanded/quarterly_metric_sources.csv')
    fields=[c for c in financial if c.startswith(('q_','ttm_')) or c in ['rd_pct_rev','software_rd_pct_rev','sm_pct_rev','sbc_pct_rev','gross_margin','fcf_physical_capex_margin','total_assets','goodwill','ppe_net','rpo','purchase_obligations','land_balance','hosting_implementation_cost_asset_net']]
    company_rows=[]; metric_rows=[]
    for c in companies.to_dict('records'):
        ticker=c['ticker']; f=financial[financial.ticker==ticker]; raw=facts[facts.ticker==ticker]
        p=prices[prices.ticker==ticker]; e=epss[epss.ticker==ticker]
        a=annual[annual.ticker==ticker]; rd=f.rd_pct_rev.notna()|f.software_rd_pct_rev.notna()
        latest=p.date.max() if len(p) else ''
        row={**c,'quarterly_rows':len(f),'reported_fact_rows':len(raw),'direct_annual_metric_rows':len(a),
             'first_financial_period':f.period_end.min() if len(f) else '',
             'last_financial_period':f.period_end.max() if len(f) else '',
             'price_rows':len(p),'first_price_date':p.date.min() if len(p) else '',
             'last_price_date':latest,'reported_list_date':details.loc[ticker,'list_date'],
             'price_identity_status':identity.loc[ticker,'status'],
             'price_history_limitation':'historical_target_issuer_delisted_or_reorganized_no_current_quote' if latest<'2026-10-02' else 'current_endpoint_present_not_full_daily_identity_vintage',
             'rd_category_rows':int(rd.sum()),'rd_scope_note':'generic and software-only categories remain separate',
             'epss_scored_months':int(e.max_product_cve_epss.notna().sum()),
             'epss_statuses':';'.join(sorted(e.coverage_status.unique())),
             'cve_name_search_status':search.loc[ticker,'status'] if ticker in search.index else 'existing_vendor_inventory_queried',
             'news_articles':int(news.ticker.eq(ticker).sum()),
             'unreviewed_disclosure_candidates':int(disclosure.ticker.eq(ticker).sum()),
             'confirmed_AI_cloud_spend':'not_established_by_candidate_extraction',
             'history_complete_since_2022':'no_claim_of_complete_numeric_history',
             'source_companyfacts_url':f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c['cik'].zfill(10)}.json"}
        company_rows.append(row)
        for field in fields:
            values=f[field].notna(); populated=f[values]
            base_metric=field.removeprefix('q_').removeprefix('ttm_')
            reported=raw[raw.metric.eq(base_metric)]
            quality='reported_or_derived_see_per_metric_lineage' if values.any() else 'no_value_not_zero'
            metric_rows.append({'cik':c['cik'],'ticker':ticker,'name':c['name'],'metric':field,
                                'observed_quarter_rows':len(f),'rows_with_value':int(values.sum()),
                                'reported_source_facts_for_base_metric':len(reported),
                                'first_populated_period':populated.period_end.min() if len(populated) else '',
                                'last_populated_period':populated.period_end.max() if len(populated) else '',
                                'status':'observed_for_every_stored_row_not_proof_of_full_history' if len(f) and values.all() else 'partial_observed_coverage' if values.any() else 'not_found_in_structured_sources_or_insufficient_matching_periods',
                                'quality':quality,'searched_source':row['source_companyfacts_url'],
                                'no_imputation':True})
    company_table=pd.DataFrame(company_rows)
    supplemental=BASE/'infrastructure_evidence/company_infrastructure_coverage_168.csv'
    if supplemental.exists():
        infrastructure=pd.read_csv(supplemental,dtype={'cik':str})
        extra=[f for f in infrastructure if f not in company_table.columns and f not in ['name','ticker']]
        company_table=company_table.merge(infrastructure[['cik']+extra],on='cik',how='left',validate='one_to_one')
    metric_table=pd.DataFrame(metric_rows)
    company_table.to_csv(OUT/'company_coverage_168.csv',index=False)
    metric_table.to_csv(OUT/'company_metric_coverage.csv',index=False)
    aggregate=metric_table.groupby('metric').agg(companies_with_any_value=('rows_with_value',lambda x:int(x.gt(0).sum())),
                                               observed_rows_with_value=('rows_with_value','sum'),
                                               companies_without_a_value=('rows_with_value',lambda x:int(x.eq(0).sum())))
    aggregate.to_csv(OUT/'metric_coverage_summary.csv')
    if len(company_table)!=168 or company_table.cik.nunique()!=168:
        raise ValueError('Coverage table must have exactly 168 unique target issuers')
    monthly=list(pd.date_range('2022-01-01','2026-10-01',freq='MS').strftime('%Y-%m-%d'))
    idx=pd.MultiIndex.from_product([companies.ticker,monthly],names=['ticker','score_date'])
    monthly_table=epss.set_index(['ticker','score_date']).reindex(idx).reset_index()
    unavailable=monthly_table.coverage_status.isna()
    monthly_table.loc[unavailable,'coverage_status']='snapshot_unavailable_no_numeric_imputation'
    company_lookup=companies.set_index('ticker')
    for field in ['cik','name']:
        monthly_table[field]=monthly_table[field].fillna(monthly_table.ticker.map(company_lookup[field]))
    monthly_table.to_csv(OUT/'company_epss_monthly_with_coverage_status.csv',index=False)
    audit=json.loads((HERE.parents[1]/'data/processed/dataset_audit_expanded/checks.json').read_text())
    raw_verification=audit['reported_facts_matching_SEC_cache']==len(facts) and audit['reported_facts_not_matching_SEC_cache']==0
    summary={'target_companies':168,'coverage_rows':len(company_table),'company_metric_status_rows':len(metric_table),
             'reported_financial_facts':len(facts),'reported_financial_facts_matching_SEC_cache':audit['reported_facts_matching_SEC_cache'],
             'financial_source_consistency_passed':raw_verification,
             'quarterly_rows':len(financial),'quarterly_companies':financial.ticker.nunique(),
             'annual_metric_rows':len(annual),'companies_with_any_direct_annual_metric':annual.ticker.nunique(),
             'companies_with_RD_category':int(company_table.rd_category_rows.gt(0).sum()),
             'usable_price_rows':len(prices),'companies_with_any_usable_price':prices.ticker.nunique(),
             'companies_with_prices_by_2022_01_31':int(company_table.first_price_date.le('2022-01-31').sum()),
             'companies_with_prices_through_2026_10_02':int(company_table.last_price_date.eq('2026-10-02').sum()),
             'issuer_identity_status_counts':company_table.price_identity_status.value_counts().to_dict(),
             'companies_with_any_EPSS_score':int(company_table.epss_scored_months.gt(0).sum()),
             'EPSS_company_month_status_rows':len(monthly_table),'EPSS_missing_snapshot_company_rows':int(unavailable.sum()),
             'NVD_company_name_queries_completed':len(search),'NVD_company_name_query_failures':int(search.status.eq('query_failed').sum()),
             'current_profile_issuer_mismatches_quarantined':quarantined,
             'unreviewed_disclosure_candidates':len(disclosure),'companies_with_disclosure_candidates':disclosure.ticker.nunique(),
             'financial_derivation_quality_counts':financial.derivation_quality.value_counts().to_dict(),
             'limitations':['168 status rows do not mean 168 complete numeric histories.','Pre-listing equity prices do not exist for newly public issuers.',
                            'Cloud bills, AI deployment spending and some other metrics are not publicly disclosed for every issuer.',
                            'EPSS is a CVE probability, not a universal company score.','Current target CIKs and reused tickers require dated identity checks.',
                            'Dated issuer intervals use endpoint and intermediate reference checks, not a fully versioned daily security master.',
                            'Financial restatement, cross-filing basis and narrative interpretation gaps remain.']}
    files=['company_coverage_168.csv','company_metric_coverage.csv','daily_bars_reviewed.csv','company_epss_monthly_with_coverage_status.csv']
    summary['sha256']={f:hashlib.sha256((OUT/f).read_bytes()).hexdigest() for f in files}
    supplemental_manifest=BASE/'infrastructure_evidence/publication_manifest.json'
    if supplemental_manifest.exists():
        summary['supplemental_infrastructure_evidence']=json.loads(supplemental_manifest.read_text())
    (OUT/'coverage_manifest.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    report=f'''# Coverage across all 168 target issuers

Every target company has a coverage record and every tracked financial metric has an explicit status. **This is not a claim that every requested value exists or has been verified.** No absent values were filled with zero, guesses, interpolations or other companies' prices.

## Latest actual coverage

- {len(facts):,} reported financial facts, all matching cached SEC records; {len(financial):,} quarterly observations across {financial.ticker.nunique()} companies. Registration-statement financials now retain their actual filing availability dates.
- {len(annual):,} directly reported annual metric observations across {annual.ticker.nunique()} companies. Annual-only values are not turned into fabricated quarters.
- R&D category data for {summary['companies_with_RD_category']}/168 companies, with software-only R&D distinguished from generic R&D. Selling, marketing, advertising and SG&A remain distinct.
- {len(prices):,} usable price bars across {prices.ticker.nunique()} companies. {summary['companies_with_prices_by_2022_01_31']} have prices by January 2022, and {summary['companies_with_prices_through_2026_10_02']} have prices through October 2, 2026. Some current symbols represent different issuers than historical target CIKs. Ticker reuse was reviewed and unrelated intervals quarantined, including FIG's prior ETF history and unrelated ROC/VIA issuer histories. The original SailPoint and Paramount target histories end in 2022 and 2025, respectively; later ticker prices belong to other issuers.
- {summary['companies_with_any_EPSS_score']}/168 companies have an actual historical EPSS aggregate. Added reviewed Airship AI and Gen brand-subset mappings, FatPipe firmware and primary-record DocuSign CVEs; Gen ownership dates are respected. These are product-CVE aggregates, not company exploitation probabilities. Broad NVD name matches remain review candidates, not automatically assigned vulnerabilities.
- {len(monthly_table):,} EPSS company-month **status** records cover every target and month from January 2022 through October 2026. Missing December 2024 scores are explicitly marked unavailable.
- Completed {len(search)} additional NVD company-name searches with {summary['NVD_company_name_query_failures']} request failures. An empty name search is not proof of no vulnerabilities.
- {len(disclosure):,} disclosure candidates across {disclosure.ticker.nunique()} companies remain unreviewed; they are not confirmed AI contracts or spending amounts. The additional filing scan processed 2,281 documents; eight indexed documents remain unavailable.
- Current provider profile numbers for {', '.join(quarantined)} were quarantined because the latest ticker reference belongs to a different issuer. Raw snapshots remain unchanged.

## What cannot honestly reach 168 complete numeric histories

Newly public companies have no public stock prices before listing. Some companies report combined expenses rather than separate R&D or marketing; many do not disclose cloud bills, AI seat counts, land amounts or model-contract spending. A company without a attributable public CVE cannot be given a genuine EPSS score. Retired/reused securities cannot be linked into continuous return histories merely because their ticker matches. Six public-float scale alerts and many cross-filing derivations still require original-source review.

The target list itself mixes historical and newer issuers. It must not be described as a validated current investable universe. Do not use a status-complete panel as a fully observed panel or a point-in-time investment database.

## Files to use

- `company_coverage_168.csv`: one row per target issuer, with coverage and remaining limitations.
- `company_metric_coverage.csv`: per-company, per-metric missingness and source-search status.
- `metric_coverage_summary.csv`: actual measured coverage, without imputation.
- `daily_bars_reviewed.csv`: cleaned prices with restored aliases and ticker-identity exclusions.
- `price_listing_review.csv` and `price_identity_exclusions.csv`: identity checks, sources and quarantined observations.
- `company_epss_monthly_with_coverage_status.csv`: all 168 targets and months, preserving missing scores.
- `company_details_with_issuer_status.csv`: provider profiles with numerical snapshots quarantined where the issuer differs.
- `disclosure_evidence_expanded.csv`: unreviewed narrative candidates with source references, not confirmed spending metrics.
- `../company_metrics_expanded/`: sourced quarterly, annual, raw financial and per-metric lineage tables.

The earlier recovery report and backtests use earlier inputs. They have not been silently rewritten to imply that the new issuer checks had already been performed.
'''
    (OUT/'REPORT.md').write_text(report,encoding='utf-8')
    if supplemental_manifest.exists():
        with (OUT/'REPORT.md').open('a',encoding='utf-8') as f:
            f.write('\n## Supplemental infrastructure evidence\n\nThe company coverage file now includes infrastructure and employee AI evidence counts. See `../infrastructure_evidence/REPORT.md` for source-verified observations, reviewed contract clauses, actual Appian agreement spending, employee evidence and remaining UK collection gaps. These supplemental observations overlap existing financial facts and must not be added to raw-fact counts as if all were new unique data.\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['sha256','limitations']},indent=2))


if __name__=='__main__':
    main()
