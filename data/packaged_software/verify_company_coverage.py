"""Verify published coverage, retained source prices and dated score caches."""
import json
import hashlib
from pathlib import Path
import pandas as pd
from expand_reviewed_epss import checked_scores

HERE = Path(__file__).resolve().parent
BASE = HERE / 'extracts'
OUT = BASE / 'company_coverage'


def main():
    targets = pd.read_csv(HERE / 'packaged_software_companies.csv', dtype=str)
    coverage = pd.read_csv(OUT / 'company_coverage_168.csv', dtype=str)
    assert len(coverage) == 168 and set(coverage.cik) == set(targets.cik)
    panel = pd.read_csv(OUT / 'company_epss_monthly_with_coverage_status.csv')
    assert len(panel) == 168 * 58
    assert not panel.duplicated(['ticker', 'score_date']).any()
    missing = panel.coverage_status.eq('snapshot_unavailable_no_numeric_imputation')
    assert panel.loc[missing, 'max_product_cve_epss'].isna().all()
    prices = pd.read_csv(OUT / 'daily_bars_reviewed.csv')
    source = pd.read_csv(BASE / 'gap_recovery/daily_bars_with_verified_aliases.csv')
    keys = ['ticker', 'date']
    fields = ['open', 'high', 'low', 'close', 'volume', 'vwap', 'transactions']
    assert not prices.duplicated(keys).any()
    joined = prices.merge(source[keys + fields], on=keys, how='left', suffixes=('', '_source'), validate='one_to_one', indicator=True)
    assert joined['_merge'].eq('both').all()
    for field in fields:
        assert (joined[field].eq(joined[field + '_source']) | (joined[field].isna() & joined[field + '_source'].isna())).all(), field
    assert prices.close.gt(0).all()
    identifiers=pd.read_csv(OUT/'daily_bars_reviewed.csv',usecols=['ticker','cik','price_identity_status'],dtype=str)
    assert identifiers.cik.notna().all()
    assert identifiers.cik.eq(identifiers.ticker.map(targets.set_index('ticker').cik.str.zfill(10))).all()
    assert identifiers.price_identity_status.notna().all()
    checked = 0
    for file in (OUT / 'epss_reviewed_cache').glob('*.json'):
        data = json.loads(file.read_text())
        checked_scores(data, file.name[:10], {r['cve'] for r in data.get('data', [])}, strict_cves=True)
        checked += len(data.get('data', []))
    details = pd.read_csv(OUT / 'company_details_with_issuer_status.csv')
    mismatches = details.issuer_attribution_status.eq('different_current_issuer_numeric_snapshot_quarantined')
    assert set(details.loc[mismatches, 'ticker']) == {'PARA', 'SAIL'}
    assert details.loc[mismatches, ['market_cap', 'total_employees']].isna().all().all()
    infra_dir=BASE/'infrastructure_evidence'
    infrastructure_checks={}
    if (infra_dir/'publication_manifest.json').exists():
        manifest=json.loads((infra_dir/'publication_manifest.json').read_text())
        for filename,digest in manifest['sha256'].items():
            assert hashlib.sha256((infra_dir/filename).read_bytes()).hexdigest()==digest,filename
        infrastructure=pd.read_csv(infra_dir/'company_infrastructure_coverage_168.csv',dtype=str)
        assert len(infrastructure)==168 and not infrastructure.cik.duplicated().any()
        merged=coverage.merge(infrastructure,on='cik',validate='one_to_one',suffixes=('_main','_supplement'))
        for field in ['source_tagged_observations','reviewed_cloud_commitment_rows','reviewed_employee_AI_evidence_rows','land_only_balance_rows','computer_equipment_balance_rows']:
            assert merged[field+'_main'].eq(merged[field+'_supplement']).all(),field
        contracts=pd.read_csv(infra_dir/'reviewed_cloud_contract_observations.csv')
        assert contracts.actual_cash_paid_usd.isna().all()
        assert not contracts.record_id.duplicated().any()
        assert set(contracts.ticker).issubset(set(targets.ticker))
        infrastructure_checks={'infrastructure_company_status_rows_verified':len(infrastructure),
                               'reviewed_cloud_commitment_records_verified':len(contracts),
                               'infrastructure_artifact_hashes_verified':len(manifest['sha256'])}
    result = {'target_status_rows_verified': len(coverage), 'monthly_status_rows_verified': len(panel),
              'retained_price_bars_unchanged_from_recovered_source': len(prices),
              'dated_EPSS_cached_rows_validated': checked,
              **infrastructure_checks,
              'scope': 'Internal source consistency and status validation, not independent vendor accuracy or full point-in-time verification.'}
    (OUT / 'publication_validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
