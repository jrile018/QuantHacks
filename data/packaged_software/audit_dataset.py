"""Read-only coverage and cached-source consistency audit; no source data repairs."""
import csv
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'data/packaged_software/extracts'
OUT = ROOT / 'data/processed/dataset_audit'


def main():
    global OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--metrics', type=Path, default=BASE / 'company_metrics')
    ap.add_argument('--output', type=Path, default=OUT)
    args = ap.parse_args()
    OUT = args.output
    metrics = args.metrics
    OUT.mkdir(parents=True, exist_ok=True)
    checks = {}
    issues = []
    prices = pd.read_csv(BASE / 'prices/daily_bars.csv')
    checks['price_rows'] = len(prices)
    checks['price_duplicate_keys'] = int(prices.duplicated(['ticker', 'date']).sum())
    checks['invalid_closes'] = int((prices.close.isna() | (prices.close <= 0)).sum())
    matched = mismatched = missing = 0
    for ticker, group in prices.groupby('ticker'):
        candidates = list((BASE / '_cache/prices').glob(f'{ticker}_*.json'))
        if len(candidates) != 1:
            issues.append({'category': 'price_cache', 'ticker': ticker, 'detail': f'{len(candidates)} candidate caches'})
            missing += len(group)
            continue
        raw = json.loads(candidates[0].read_text(encoding='utf-8'))
        bars = {datetime.fromtimestamp(r['t']/1000, timezone.utc).date().isoformat(): r for r in raw.get('results', [])}
        for r in group.itertuples(index=False):
            b = bars.get(r.date)
            if b is None:
                missing += 1
            elif all(float(getattr(r, field)) == float(b[key]) for field, key in [('open','o'),('high','h'),('low','l'),('close','c'),('volume','v')]):
                matched += 1
            else:
                mismatched += 1
                issues.append({'category':'price_source_mismatch', 'ticker':ticker, 'detail':r.date})
    checks.update(price_rows_matching_cached_ohlcv=matched, price_rows_mismatching_cached_ohlcv=mismatched, price_rows_missing_cached_source=missing)
    facts = pd.read_csv(metrics / 'reported_financial_facts.csv', dtype=str).fillna('')
    checks['reported_fact_rows'] = len(facts)
    checks['duplicate_fact_ids'] = int(facts.fact_id.duplicated().sum())
    matched = missing = 0
    for ticker, group in facts.groupby('ticker'):
        raw = json.loads((BASE / 'sec' / ticker / 'companyfacts.json').read_text(encoding='utf-8'))
        source_keys = set()
        for taxonomy, concepts in raw.get('facts', {}).items():
            for tag, concept in concepts.items():
                for unit, observations in concept.get('units', {}).items():
                    for f in observations:
                        source_keys.add((taxonomy,tag,unit,f.get('start',''),f.get('end',''),f.get('filed',''),f.get('accn',''),f.get('form',''),float(f['val'])))
        for r in group.itertuples(index=False):
            key = (r.taxonomy,r.tag,r.unit,r.period_start,r.period_end,r.filed_date,r.accession,r.form,float(r.value))
            if key in source_keys:
                matched += 1
            else:
                missing += 1
                issues.append({'category':'SEC_fact_missing_cached_source','ticker':ticker,'detail':r.fact_id})
    checks.update(reported_facts_matching_SEC_cache=matched, reported_facts_not_matching_SEC_cache=missing)
    lineage = pd.read_csv(metrics / 'quarterly_metric_sources.csv', dtype=str).fillna('')
    fact_ids = set(facts.fact_id)
    checks['lineage_rows'] = len(lineage)
    checks['lineage_missing_fact_references'] = sum(fid not in fact_ids for ids in lineage.source_fact_ids for fid in ids.split(';') if fid)
    fundamentals = pd.read_csv(metrics / 'fundamentals_quarterly.csv')
    checks['quarterly_rows'] = len(fundamentals)
    checks['duplicate_company_periods'] = int(fundamentals.duplicated(['cik','period_end']).sum())
    checks['derivation_quality_counts'] = fundamentals.derivation_quality.value_counts().to_dict()
    overlaps = []
    for ticker, group in fundamentals.groupby('ticker'):
        group = group.sort_values('period_end')
        gaps = pd.to_datetime(group.period_end).diff().dt.days
        for i in group.index[gaps < 70]:
            r = group.loc[i]
            overlaps.append({'category':'close_spaced_quarter_end_review','ticker':ticker,'detail':r.period_end})
    issues.extend(overlaps)
    checks['close_spaced_period_ends_under_70_days'] = len(overlaps)
    coverage = []
    for field in fundamentals.columns:
        if field.startswith(('q_','ttm_')) or field in ['rd_pct_rev','sm_pct_rev','sbc_pct_rev','gross_margin','fcf_physical_capex_margin','total_assets','goodwill','ppe_net','rpo','purchase_obligations','land_balance','hosting_implementation_cost_asset_net']:
            nonblank = fundamentals[field].notna()
            coverage.append({'metric':field,'observed_rows':len(fundamentals),'nonmissing_rows':int(nonblank.sum()),'companies_with_any_value':int(fundamentals.loc[nonblank,'ticker'].nunique()),'observed_row_coverage_pct':round(100*nonblank.mean(),2)})
    pd.DataFrame(coverage).to_csv(OUT / 'metric_coverage.csv',index=False)
    pricecov = prices.groupby('ticker').agg(bars=('date','size'),first_date=('date','min'),last_date=('date','max'))
    pricecov.to_csv(OUT / 'price_coverage.csv')
    checks['price_companies_starting_by_2022_01_31'] = int((pricecov.first_date <= '2022-01-31').sum())
    checks['price_companies_with_at_least_95pct_max_bars'] = int((pricecov.bars >= .95*pricecov.bars.max()).sum())
    manifest = json.loads((BASE / 'epss_monthly/manifest.json').read_text())
    checks['epss_snapshot_errors'] = manifest.get('errors',[])
    filings = pd.read_csv(BASE / 'sec/filings_index.csv')
    checks['filing_index_rows'] = len(filings)
    checks['filing_status_counts'] = filings.status.value_counts().to_dict()
    for r in filings[filings.status.eq('failed')].itertuples(index=False):
        issues.append({'category':'filing_download_failed','ticker':r.ticker,'detail':f'{r.filing_date} {r.accession} {r.primary_document}'})
    pd.DataFrame(issues,columns=['category','ticker','detail']).to_csv(OUT / 'review_flags.csv',index=False)
    checks['audited_at_utc'] = datetime.now(timezone.utc).isoformat()
    checks['scope_limitation'] = 'Cache consistency verifies extraction, not issuer truth, point-in-time availability, entity attribution, or accounting derivations.'
    (OUT / 'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks,indent=2))


if __name__ == '__main__':
    main()
