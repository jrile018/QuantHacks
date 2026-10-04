"""Publish actual before/after coverage and remaining recovery work."""
import json
import datetime as dt
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
BASE=HERE/'extracts'
OUT=BASE/'gap_recovery'


def main():
    old=pd.read_csv(BASE/'company_metrics/fundamentals_quarterly.csv',dtype={'cik':str})
    new=pd.read_csv(BASE/'company_metrics_recovered/fundamentals_quarterly.csv',dtype={'cik':str})
    fields=['ttm_revenue','rd_pct_rev','sm_pct_rev','sbc_pct_rev','gross_margin','fcf_physical_capex_margin',
            'ttm_general_and_administrative','ttm_selling_general_and_administrative','ttm_advertising_expense',
            'ttm_restructuring_charges','deferred_revenue_noncurrent','long_term_debt_noncurrent','long_term_debt_current']
    previous=old.set_index(['cik','period_end'])
    updated=new.set_index(['cik','period_end'])
    rows=[]
    for field in fields:
        a=previous[field] if field in previous else pd.Series(index=previous.index,dtype=float)
        b=updated[field]
        aligned=a.reindex(b.index)
        rows.append({'metric':field,'previous_nonmissing_rows':int(a.notna().sum()),'new_nonmissing_rows':int(b.notna().sum()),
                     'new_companies_with_value':int(new.loc[new[field].notna(),'ticker'].nunique()),
                     'previously_missing_values_recovered':int((aligned.isna() & b.notna()).sum()),
                     'values_now_blank_or_excluded':int((b.reindex(a.index).isna() & a.notna()).sum())})
    coverage=pd.DataFrame(rows)
    coverage.to_csv(OUT/'financial_coverage_changes.csv',index=False)
    before_facts=pd.read_csv(BASE/'company_metrics/reported_financial_facts.csv',usecols=['fact_id'])
    facts=pd.read_csv(BASE/'company_metrics_recovered/reported_financial_facts.csv',usecols=['fact_id'])
    provenance=pd.read_csv(BASE/'company_metrics_recovered/quarterly_metric_sources.csv')
    old_prov=pd.read_csv(BASE/'company_metrics/quarterly_metric_sources.csv')
    common=old_prov.set_index(['cik','period_end','metric','basis'])
    current=provenance.set_index(['cik','period_end','metric','basis'])
    aligned=common.quality.reindex(current.index)
    improved=int(((aligned=='cross_filing_basis_unverified')&(current.quality=='reported')).sum())
    price=pd.read_csv(OUT/'daily_bars_with_verified_aliases.csv')
    pricecoverage=price.groupby('ticker').agg(bars=('date','size'),first_date=('date','min'),last_date=('date','max'))
    pricecoverage.to_csv(OUT/'restored_price_coverage.csv')
    mappings=pd.read_csv(OUT/'alias_mapping_review.csv')
    accepted=mappings.loc[mappings.mapping_status!='not_verified_do_not_stitch','ticker'].tolist()
    restored=price.loc[price.history_source.eq('verified_former_symbol')]
    matched=0
    for symbol, group in restored.groupby('source_ticker'):
        cache=next((OUT/'alias_cache').glob(f'{symbol}_2022-01-01_*.json'))
        bars={dt.datetime.fromtimestamp(b['t']/1000,dt.timezone.utc).date().isoformat():b for b in json.loads(cache.read_text()).get('results',[])}
        for r in group.itertuples(index=False):
            b=bars[r.date]
            matched+=all(float(getattr(r,k))==float(b[v]) for k,v in [('open','o'),('high','h'),('low','l'),('close','c'),('volume','v')])
    if matched!=len(restored) or price.duplicated(['ticker','date']).any() or not price.close.gt(0).all():
        raise ValueError('Restored price validation failed')
    manifest=json.loads((BASE/'company_metrics_recovered/manifest.json').read_text())
    manifest['quarterly_rows']=len(new)
    manifest['financial_run_end']='2026-10-03'
    manifest['overlapping_calendar_observations_excluded']=len(pd.read_csv(BASE/'company_metrics_recovered/quarter_calendar_review.csv'))
    (BASE/'company_metrics_recovered/manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    audit=json.loads((HERE.parents[1]/'data/processed/dataset_audit_recovered/checks.json').read_text())
    evidence=pd.read_csv(BASE/'company_metrics_recovered/disclosure_evidence.csv')
    tagged=pd.read_csv(BASE/'company_metrics_recovered/filing_tagged_asset_and_cloud_facts.csv')
    result={'reported_fact_rows_before':len(before_facts),'reported_fact_rows_after':len(facts),
            'new_fact_ids':len(set(facts.fact_id)-set(before_facts.fact_id)),
            'quarterly_rows_before':len(old),'quarterly_rows_after':len(new),
            'existing_unverified_derivations_replaced_with_reported_values':improved,
            'reported_annual_TTM_observations':int(provenance.method.eq('reported_annual_ttm').sum()),
            'accepted_price_alias_companies':accepted,'restored_valid_price_bars':int(price.history_source.eq('verified_former_symbol').sum()),
            'restored_bars_matching_cached_OHLCV':matched,'usable_price_rows':len(price),
            'companies_starting_by_2022_01_31':int((pricecoverage.first_date<='2022-01-31').sum()),
            'companies_with_95pct_maximum_bars':int((pricecoverage.bars>=.95*pricecoverage.bars.max()).sum()),
            'disclosure_candidates':len(evidence),'disclosure_companies':int(evidence.ticker.nunique()),
            'tagged_asset_cloud_fact_rows':len(tagged),'filings_scanned':manifest.get('filings_scanned'),
            'filings_missing':manifest.get('filings_missing'),'source_audit':audit}
    (OUT/'recovery_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    queue=[
        ('historical_prices','partially_recovered',f"{result['restored_valid_price_bars']} valid bars restored for {len(accepted)} verified share histories; other aliases still need issuer/class evidence"),
        ('financial_standard_tags','expanded','Additional distinct G&A, SG&A, advertising, restructuring, deferred revenue and debt metrics extracted without substituting unlike tags'),
        ('annual_TTM','partially_verified',f'{improved} existing unverified derived values replaced by directly reported values; other cross-filing calculations remain flagged'),
        ('quarter_calendars','overlap_removed','Earlier-available non-overlapping quarters selected; later overlapping comparatives preserved for review; no transition quarters fabricated'),
        ('SEC_archive_paths','repaired','Legacy index paths normalized to the moved archive; missing exhibit retry returned 404'),
        ('December_2024_EPSS','source_unavailable','Bulk and dated API retried; FIRST API returns 422. No substitute date or interpolation used'),
        ('EPSS_company_mappings','requires_entity_product_research','Unmapped companies and absent CVEs remain missing; no automatic name-based vendor attribution'),
        ('cloud_AI_spending','disclosure_candidates_only','Rescanned public filings; amounts, seats and internal adoption require semantic/source confirmation'),
        ('public_float_scale','7_source_reviewed_6_unresolved','Seven cover-page dollar amounts confirmed inconsistent XBRL scaling; corrected supplemental table retains raw API values and source excerpts. Six alerts remain unresolved'),
        ('historical_universe','not_resolved','Current 168-company universe is not historical membership; company snapshots are not backfilled historical observations')]
    pd.DataFrame(queue,columns=['gap','status','detail']).to_csv(OUT/'remaining_gap_queue.csv',index=False)
    table='\n'.join(f"| {r['metric']} | {r['previous_nonmissing_rows']} | {r['new_nonmissing_rows']} | {r['new_companies_with_value']} | {r['previously_missing_values_recovered']} |" for r in rows)
    report=f'''# First dataset gap-recovery pass

Raw price and original company-metrics datasets remain intact. New financial tables are in `../company_metrics_recovered/`. The usable price history is `daily_bars_with_verified_aliases.csv`; rejected aliases are retained as candidates only.

## Actual improvements

- Reported financial facts: {len(before_facts):,} → {len(facts):,}; {result['new_fact_ids']:,} new source fact IDs. All {audit['reported_facts_matching_SEC_cache']:,} reported facts match their cached SEC source records. This is extraction verification, not independent accounting verification.
- {improved:,} existing unverified derived values replaced by directly reported values. {result['reported_annual_TTM_observations']:,} annual TTM observations now use direct annual reports, with original filing availability. Ratios reject mismatched annual windows.
- Quarterly rows: {len(old):,} → {len(new):,}, after removing overlapping periods from the sequential panel. Excluded observations remain in reported facts and the calendar-review table. This selection follows earliest disclosure availability and is not a fully versioned restatement database.
- {result['restored_valid_price_bars']:,} valid historical bars restored for {', '.join(accepted)} using matching provider issuer CIK and common-share FIGI, with adjacent dates and no large transition discontinuity. January 2022 price coverage: 135 → {result['companies_starting_by_2022_01_31']}. Near-full coverage: 130 → {result['companies_with_95pct_maximum_bars']}. These checks do not independently verify every corporate action. CXAI's matched share identity has a roughly 20x price discontinuity, so its predecessor bars are excluded pending split/corporate-action review. Prices are split-adjusted and exclude dividends.
- 60 invalid original price bars excluded from the usable table and retained in an exclusion file. Other rejected or unavailable alias histories remain separate; no guessed share-class matches.
- Filing-index paths repaired after the archive move. {manifest.get('filings_scanned',0):,} eligible documents scanned; {manifest.get('filings_missing',0)} missing. Extracted {len(evidence):,} disclosure candidates across {evidence.ticker.nunique()} companies and {len(tagged):,} tagged asset/cloud facts. These remain unreviewed candidates, not confirmed spending or deployments.

## Metric coverage

Counts refer to observed quarterly rows, not a complete theoretical calendar panel. Previous counts refer specifically to the original quarterly table; some added metrics already existed in separate annual supplements. Newly recovered values are counted on aligned issuer/period keys; rows excluded for calendar consistency can reduce aggregate totals.

| Metric | Previous rows | Current rows | Companies with any value | Previously missing values recovered |
|---|---:|---:|---:|---:|
{table}

## Remaining gaps

Seven public-float records (GEG, HUBS, SSTI) were reviewed against explicit dollar amounts on original 10-K cover pages and corrected in `xbrl_gaps_annual_reviewed.csv`. Original API values, source URLs, file hashes and excerpts are retained in `public_float_review.csv`. Six scale alerts remain unresolved; no arbitrary rescaling was applied to them.

QUBT's missing June 2023 exhibit still returns HTTP 404. December 1, 2024 EPSS remains unavailable (dated API 422); no interpolation or neighboring date was substituted. Unmapped EPSS vendors, sparse spending disclosures, ambiguous entity matches and incomplete historical universe membership require further source review. Cross-filing financial calculations remain quality-flagged; raw price equality and fact equality do not verify their interpretation. Most AI/cloud narrative candidates lack a disclosed, attributable spending amount.

See `remaining_gap_queue.csv`, `financial_coverage_changes.csv`, `alias_mapping_review.csv`, and the recovered audit for exact coverage and review status. Existing research/backtests have not been rerun or silently switched to these new tables.
'''
    (OUT/'REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='source_audit'},indent=2))


if __name__=='__main__':
    main()
