"""Publish measured coverage and distinguish reviewed evidence from candidates."""
import hashlib
import json
import re
from pathlib import Path
import pandas as pd
from extract_infrastructure_evidence import HERE, OUT, BASE
from extract_company_metrics import next_day
from review_infrastructure_sources import source_text


def reviewed_candidate_commitments(registry):
    """Publish only individually reviewed amounts, checked against pinned source bytes."""
    candidates=pd.read_csv(OUT/'cloud_commitment_amount_candidates.csv',dtype={'cik':str}).fillna('')
    records=[]
    for review in registry.get('additional_cloud_commitment_reviews',[]):
        selected=candidates[candidates.evidence_id.eq(review['evidence_id']) &
                            candidates.ticker.eq(review['ticker']) &
                            candidates.amount_usd_candidate.eq(review['amount_usd'])]
        if len(selected)!=1: raise ValueError('Reviewed cloud amount missing or ambiguous')
        row=selected.iloc[0].to_dict()
        text,digest=source_text(row['local_path'])
        if digest!=review['source_sha256']: raise ValueError('Reviewed source has changed')
        match=re.search(review['source_pattern'],text)
        if not match: raise ValueError('Reviewed cloud clause missing from source')
        records.append({**{k:row[k] for k in ['cik','ticker','name','filed_date','source_url','local_path']},
                        'record_id':'review-'+row['evidence_id'],'amount_usd':review['amount_usd'],
                        'available_date_conservative':next_day(row['filed_date']),
                        'metric':review['metric'],'measure_type':review['measure_type'],
                        'source_clause':match.group(),'source_context':text[max(0,match.start()-350):match.end()+450],
                        'source_sha256':digest,'contract_start':review.get('contract_start',''),
                        'contract_end':review.get('contract_end',''),'actual_cash_paid_usd':'',
                        'scope_note':review['scope_note']})
    return pd.DataFrame(records)


def main():
    companies=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str)
    registry=json.loads((HERE/'infrastructure_review_registry.json').read_text())
    facts=pd.read_csv(OUT/'infrastructure_observations_with_scope_review.csv',dtype={'cik':str}).fillna('')
    clauses=pd.read_csv(OUT/'cloud_contract_clauses.csv',dtype={'cik':str})
    wanted=set(registry['cloud_clause_records_reviewed'])
    if not wanted.issubset(set(clauses.record_id)): raise ValueError('Reviewed clause no longer present')
    reviewed=clauses[clauses.record_id.isin(wanted)].copy()
    reviewed=pd.concat([reviewed,reviewed_candidate_commitments(registry)],ignore_index=True)
    reviewed['status']='source_context_reviewed_reported_commitment_not_spending'
    reviewed.to_csv(OUT/'reviewed_cloud_contract_observations.csv',index=False)
    evidence=pd.read_csv(BASE/'company_coverage/disclosure_evidence_expanded.csv',dtype=str).fillna('')
    events=[]; outside=[]
    company_lookup=companies.set_index('ticker')
    for event in registry['external_events']:
        if event['ticker'] not in company_lookup.index:
            outside.append({**event,'exclusion_reason':'outside_fixed_168_company_universe'})
            continue
        c=company_lookup.loc[event['ticker']].to_dict()
        events.append({**c,**event,'source_type':'company_announcement_or_supplier_case_study',
                       'observed_date':registry['review_date'],'available_date_conservative':next_day(registry['review_date']),
                       'date_policy':'reported_publication_date_preserved_but_current_web_page_has_no_verified_archival_vintage',
                       'status':'source_reviewed_reported_event_not_independent_contract_or_outcome_verification',
                       'paid_enterprise_contract_confirmed':False})
    for item in registry['SEC_employee_evidence_reviewed']:
        row=evidence[evidence.evidence_id.eq(item['evidence_id'])].iloc[0].to_dict()
        if row['ticker']!=item['ticker']: raise ValueError('Employee evidence issuer mismatch')
        events.append({**{k:row[k] for k in ['cik','ticker','name','source_url','filed_date','local_path','evidence_id']},**item,
                       'source_type':'SEC_filing','publication_date':row['filed_date'],
                       'available_date_conservative':next_day(row['filed_date']),'observed_date':registry['review_date'],
                       'date_policy':'immutable_filing_date_next_day','status':'source_reviewed_reported_event_not_independent_contract_or_outcome_verification',
                       'paid_enterprise_contract_confirmed':False,'spend_usd':None,'licensed_seats':None})
    event_table=pd.DataFrame(events)
    pd.DataFrame(outside).to_csv(OUT/'outside_universe_references.csv',index=False)
    event_table.to_csv(OUT/'reviewed_employee_AI_evidence.csv',index=False)
    properties=[]
    for item in registry['property_events']:
        c=company_lookup.loc[item['ticker']].to_dict()
        properties.append({**c,**item,'status':'reported_property_event_not_spending_or_legal_title_verification',
                           'observed_date':registry['review_date'],'available_date_conservative':next_day(registry['review_date']),
                           'historical_vintage':'current_web_sources_not_archivally_verified'})
    pd.DataFrame(properties).to_csv(OUT/'reviewed_property_events.csv',index=False)
    pd.DataFrame(registry['registry_matches']).to_csv(OUT/'UK_registry_number_matches.csv',index=False)
    uk=pd.read_csv(OUT/'UK_subsidiary_registry_queue.csv',dtype=str)
    rows=[]
    pure_land=facts.metric.isin(['land_asset_balance','land_gross_asset_balance','land_net_asset_balance'])
    computer=facts.metric.isin(['computer_equipment_gross_asset_balance','computer_equipment_net_asset_balance'])
    expenses=facts.measure_type.eq('reported_segment_expense')
    for c in companies.to_dict('records'):
        f=facts[facts.ticker.eq(c['ticker'])]
        rows.append({**c,'source_tagged_observations':len(f),
                     'computer_equipment_balance_rows':int((computer & facts.ticker.eq(c['ticker'])).sum()),
                     'land_only_balance_rows':int((pure_land & facts.ticker.eq(c['ticker'])).sum()),
                     'reviewed_hosting_expense_rows':int((expenses & facts.ticker.eq(c['ticker'])).sum()),
                     'cloud_prepaid_or_accrued_rows':int(f.measure_type.isin(['liability_balance','prepaid_asset_balance','accounts_payable_component_not_total_expense']).sum()),
                     'reviewed_cloud_commitment_rows':int(reviewed.ticker.eq(c['ticker']).sum()),
                     'reviewed_employee_AI_evidence_rows':int(event_table.ticker.eq(c['ticker']).sum()),
                     'UK_subsidiary_name_candidates':int(uk.parent_ticker.eq(c['ticker']).sum()),
                     'public_cloud_bill_status':'no_complete_cloud_invoice_history',
                     'employee_AI_contract_value_status':'not_disclosed_in_reviewed_evidence',
                     'numeric_missingness':'not_found_is_not_zero'})
    coverage=pd.DataFrame(rows)
    coverage.to_csv(OUT/'company_infrastructure_coverage_168.csv',index=False)
    spending=pd.read_csv(OUT/'reported_cloud_agreement_spending_first_filed.csv',dtype={'cik':str})
    numerical=json.loads((OUT/'numeric_source_validation.json').read_text())
    if numerical['failures'] or numerical['reported_observations']!=len(facts): raise ValueError('Numeric source verification incomplete')
    summary={'target_companies':len(coverage),'tagged_observations':len(facts),'companies_with_tagged_observations':facts.cik.nunique(),
             'numeric_source_matches':numerical['observations_matching_original_inline_values_units_periods_dimensions_and_source_hash'],
             'companies_with_computer_equipment_balances':facts[computer].cik.nunique(),
             'companies_with_separate_land_balances':facts[pure_land].cik.nunique(),
             'reviewed_hosting_expense_rows':int(expenses.sum()),'companies_with_reviewed_hosting_expenses':facts[expenses].ticker.unique().tolist(),
             'reviewed_cloud_commitment_records':len(reviewed),'companies_with_reviewed_cloud_commitments':reviewed.ticker.nunique(),
             'reported_cloud_agreement_spend_periods_first_filed':len(spending),
             'employee_AI_evidence_records':len(event_table),'companies_with_employee_AI_evidence':event_table.ticker.nunique(),
             'UK_subsidiary_name_candidates':len(uk),'UK_parent_candidates':uk.parent_cik.nunique(),
             'UK_API_collection_status':json.loads((OUT/'companies_house/manifest.json').read_text())['status'],
             'property_event_records':len(properties),'period_start_requested':'2022-01-01','review_date':registry['review_date'],
             'limitations':['No complete 168-company spending panel.', 'Balances, expense, cash purchases and commitments are distinct.',
                            'Custom observations without explicit review retain unresolved semantics.', 'Supplier outcomes are reported claims, not audited productivity effects.',
                            'Web publication dates without archival proof are not automatically used as historical availability dates.',
                            'Subsidiary and property registry collection remains partial.']}
    paths=['company_infrastructure_coverage_168.csv','infrastructure_observations_with_scope_review.csv','reviewed_cloud_contract_observations.csv','reported_cloud_agreement_spending_first_filed.csv','reviewed_employee_AI_evidence.csv']
    summary['sha256']={p:hashlib.sha256((OUT/p).read_bytes()).hexdigest() for p in paths}
    (OUT/'publication_manifest.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    report=f'''# Infrastructure and employee AI evidence

Public evidence collection across the fixed 168 target companies, reviewed October 3, 2026. This is a supplemental sourced extract; the existing fundamentals and raw files remain intact.

## Actual observations

- {len(facts):,} tagged observations across {facts.cik.nunique()} companies. All match their original cached inline XBRL values, units, periods, dimensions and source hashes.
- Computer-equipment balances for {summary['companies_with_computer_equipment_balances']} companies and separate land balances for {summary['companies_with_separate_land_balances']} companies. These are asset balances, not expenditure. Combined land/building categories remain separate.
- {int(expenses.sum())} source-scoped hosting expense observations for AvePoint and ZoomInfo, including periods since 2022 with actual later filing dates preserved. Datadog cloud amounts described as included in accounts payable are not treated as total expense. ServiceTitan's instant cloud-hosting figures are accrued liabilities.
- {len(spending)} distinct directly reported Appian AWS spending periods since 2022, including annual spending of $33.1m in 2022, $36.6m in 2023, $41.2m in 2024 and $53.3m in 2025. The source says spending under the agreement; a cash-accounting basis is not assumed. Overlapping quarter/YTD/annual periods must not be added together.
- {len(reviewed)} reviewed cloud commitment observations for {reviewed.ticker.nunique()} companies. Additional individually reviewed candidates are checked against pinned source hashes and exact clauses. The broader {len(clauses)}-clause extraction remains a candidate set; review does not imply complete contract inventories or the earliest historical disclosure of each contract.
- {len(event_table)} source-reviewed internal AI evidence records for {event_table.ticker.nunique()} target companies. They distinguish named deployments, general employee use, training/governance and AI-enabled learning. None establishes a paid contract amount or a target-company license count. Jamf's supplier case study is retained only as an outside-universe reference; Jamf is not in the fixed 168-company list and is excluded from coverage counts.
- Adobe's 2023 office-tower opening is recorded with a municipal project/parcel reference. Neither project area nor a permit is converted into construction cost or land purchase spending.
- {len(uk)} UK subsidiary name candidates across {uk.parent_cik.nunique()} parents, and two Companies House name/number matches. These are not verified ownership or spending records. The API collector reports `{summary['UK_API_collection_status']}`; no UK accounts or numerical accounts metrics have been collected in this pass.

## Dates and interpretation

SEC observations retain the filing date and next-day availability. Older-period values disclosed later remain late-available. Current website evidence without an archived publication snapshot uses the first observed date conservatively; a reported original publication date is stored separately. A vendor case study is evidence of a reported deployment, not independent confirmation of savings or productivity.

No missing amounts were imputed. Annual figures were not fabricated into quarters. Private cloud bills, unreported AI costs and many property transactions remain unavailable. Unreviewed custom tags and amount candidates must not be fed into spending models as confirmed metrics.

## Main files

- `company_infrastructure_coverage_168.csv`: one status record for every target.
- `infrastructure_observations_with_scope_review.csv`: original numbers and reviewed scope corrections, with source hashes, URLs and contexts.
- `reviewed_cloud_contract_observations.csv`: reviewed commitments, separated from expenses.
- `reported_cloud_agreement_spending_first_filed.csv`: directly reported Appian agreement spending with exact periods.
- `reviewed_employee_AI_evidence.csv`: source-reviewed employee evidence and date limitations.
- `reviewed_property_events.csv`: property events with no invented costs.
- `UK_subsidiary_registry_queue.csv`: candidate legal entities, requiring registry/ownership review.
'''
    (OUT/'REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['sha256','limitations']},indent=2))


if __name__=='__main__':
    main()
