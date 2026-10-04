"""Apply explicit source-reviewed scope corrections and publish reviewed evidence."""
import hashlib
import html
import json
import re
from pathlib import Path
import pandas as pd
from extract_infrastructure_evidence import OUT, BASE, HERE, ROOT, split_sentences
from extract_company_metrics import HTML_TAG, HIDDEN_BLOCK, next_day
from sec_common import env_value

# Each rule is anchored to an explicit reported clause. Different quantities stay separate.
RULES = [
 ('cloud_contract_minimum_total', r'committed to spend (?:an aggregate of |a minimum of )?\$\s*([\d,.]+)\s*(million|billion)\s+(?:on cloud services|between)', 'contract_total_not_period_expense'),
 ('cloud_remaining_obligations', r'our cloud infrastructure obligations are approximately\s*\$\s*([\d,.]+)\s*(million|billion)', 'remaining_commitment_not_cash_paid'),
 ('cloud_contract_minimum_total', r'Purchase commitments under the agreement total\s*\$\s*([\d,.]+)\s*(million|billion)\s+over five years', 'contract_total_not_period_expense'),
 ('cloud_contract_minimum_total', r'required to spend a minimum of\s*\$\s*([\d,.]+)\s*(million|billion)\s+over the term of the agreement', 'contract_total_not_period_expense'),
 ('cloud_contract_minimum_total', r'minimum spend commitment of\s*\$\s*([\d,.]+)\s*(million|billion)\s+over the contract period', 'contract_total_not_period_expense'),
 ('cloud_contract_minimum_total', r'(?:provides for|entered into an amended agreement[^.]{0,100}) a total purchase commitment of\s*\$\s*([\d,.]+)\s*(million|billion)\s+over a', 'contract_total_not_period_expense'),
 ('cloud_annual_minimum_commitment', r'cloud hosting provider pursuant to which we committed to spend\s*\$\s*([\d,.]+)\s*(million|billion)\s+in each of the next five years', 'annual_contract_minimum_not_actual_spend'),
 ('cloud_remaining_obligations', r'Other commitments consist of hosting costs, with a committed spend of\s*\$\s*([\d,.]+)\s*(million|billion)\s+remaining', 'remaining_commitment_not_cash_paid'),
 ('cloud_contract_minimum_total', r'entered into a\s*\$\s*([\d,.]+)\s*(million|billion)\s+purchase commitment for cloud infrastructure capacity', 'contract_total_not_period_expense'),
]


def source_text(path):
    raw=(ROOT/path).read_bytes()
    text=' '.join(html.unescape(HTML_TAG.sub(' ',HIDDEN_BLOCK.sub(' ',raw.decode('utf-8',errors='replace')))).split())
    return text,hashlib.sha256(raw).hexdigest()


def appian_spending(text):
    pattern=r'Spending under this agreement for the (three|six|nine|twelve)(?: and (three|six|nine|twelve))? months ended ([A-Z][a-z]+ \d{1,2}, \d{4}) totaled \$\s*([\d,.]+) million(?: and \$\s*([\d,.]+) million)?(?:, respectively)?'
    months={'three':3,'six':6,'nine':9,'twelve':12}
    for match in re.finditer(pattern,text):
        if bool(match[2])!=bool(match[5]):
            continue
        end=pd.Timestamp(match[3])
        if end.strftime('%Y-%m-%d')<'2022-01-01': continue
        for label,amount in [(match[1],match[4])]+([(match[2],match[5])] if match[2] else []):
            start=end.replace(day=1)-pd.DateOffset(months=months[label]-1)
            yield {'amount_usd':float(amount.replace(',',''))*1e6,'period_start':start.strftime('%Y-%m-%d'),
                   'period_end':end.strftime('%Y-%m-%d'),'source_clause':match.group(),
                   'measure_type':'reported_spending_under_AWS_agreement_cash_basis_not_specified'}
    annual=r'Spending under this agreement for the years? ended December 31, ([\d, and]+?) totaled (\$\s*[\d,.]+\s*million(?:,\s*(?:and\s*)?\$\s*[\d,.]+\s*million)*)(?:, respectively)?\.'
    for match in re.finditer(annual,text):
        years=re.findall(r'\b\d{4}\b',match[1])
        amounts=re.findall(r'\$\s*([\d,.]+)\s*million',match[2])
        if len(years)!=len(amounts): continue
        for year,amount in zip(years,amounts):
            if int(year)<2022: continue
            yield {'amount_usd':float(amount.replace(',',''))*1e6,'period_start':year+'-01-01','period_end':year+'-12-31',
                   'source_clause':match.group(),'measure_type':'reported_spending_under_AWS_agreement_cash_basis_not_specified'}


def main():
    companies=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str)
    frame=pd.read_csv(OUT/'reported_infrastructure_observations.csv',dtype={'cik':str}).fillna('')
    # Datadog explicitly says these values are included in accounts payable.
    correction=frame.tag.eq('ddog:CloudHostingAndInfrastructureExpenses')
    frame.loc[correction,'metric']='cloud_costs_included_in_accounts_payable_reported_with_duration_context'
    frame.loc[correction,'measure_type']='accounts_payable_component_not_total_expense'
    frame.loc[correction,'semantic_status']='source_reviewed_accounts_payable_footnote'
    frame.loc[frame.tag.eq('ttan:CloudHostingCosts'),'metric']='cloud_hosting_accrued_balance'
    frame.loc[frame.tag.eq('ttan:CloudHostingCosts'),'measure_type']='liability_balance'
    frame.loc[frame.tag.eq('ttan:CloudHostingCosts'),'semantic_status']='source_reviewed_accrued_expenses_table'
    for tag,metric in [('avpt:CloudAndServerHostingServicesExpense','reported_cloud_and_server_hosting_expense'),('zi:HostingAndInfrastructureExpense','reported_hosting_and_infrastructure_expense')]:
        mask=frame.tag.eq(tag)
        frame.loc[mask,'metric']=metric
        frame.loc[mask,'measure_type']='reported_segment_expense'
        frame.loc[mask,'semantic_status']='source_reviewed_single_segment_expense_table_scope_preserved'
    frame.to_csv(OUT/'infrastructure_observations_with_scope_review.csv',index=False)
    candidates=pd.read_csv(BASE/'company_coverage/disclosure_evidence_expanded.csv',dtype=str).fillna('')
    clouds=candidates[candidates.category.eq('cloud') & candidates.excerpt.str.contains('million|billion',case=False) & candidates.excerpt.str.contains('commit|minimum|oblig',case=False)]
    paths=clouds.drop_duplicates('local_path').to_dict('records')
    existing={r['local_path'] for r in paths}
    index=pd.read_csv(BASE/'sec/filings_index.csv',dtype=str).fillna('')
    appian=companies.set_index('ticker').loc['APPN'].to_dict()
    for r in index[index.ticker.eq('APPN') & index.document_role.eq('primary') & index.form.isin(['10-K','10-Q'])].to_dict('records'):
        if r['local_path'] not in existing:
            paths.append({**r,'name':appian['name'],'filed_date':r['filing_date'],
                          'source_url':f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{r['accession'].replace('-','')}/{r['primary_document']}"})
            existing.add(r['local_path'])
    records=[]; seen=set(); spending=[]; spend_seen=set()
    for row in paths:
        text,digest=source_text(row['local_path'])
        if row['ticker']=='APPN':
            for item in appian_spending(text):
                key=(row['accession'],item['period_start'],item['period_end'],item['amount_usd'])
                if key in spend_seen: continue
                spend_seen.add(key)
                spending.append({**{k:row[k] for k in ['cik','ticker','name','filed_date','source_url','local_path']},**item,
                                 'available_date_conservative':next_day(row['filed_date']),'source_sha256':digest,
                                 'status':'source_reviewed_reported_spending_clause_exact_periods'})
        for metric,pattern,scope in RULES:
            for match in re.finditer(pattern,text,re.I):
                fragment=text[max(0,match.start()-400):match.end()+300]
                if not re.search(r'cloud|hosting|Amazon Web Services',fragment,re.I): continue
                # Broad purchase agreements may mix other goods. Never allocate such totals to cloud.
                if metric=='cloud_contract_minimum_total' and row['ticker'] not in ['INTA','APPN','ASAN','SNOW','U','COUR']:
                    continue
                value=float(match[1].replace(',',''))*({'million':1e6,'billion':1e9}[match[2].lower()])
                key=(row['cik'],metric,value,fragment)
                if key in seen: continue
                seen.add(key)
                records.append({**{k:row[k] for k in ['cik','ticker','name','filed_date','source_url','local_path']},
                                'available_date_conservative':next_day(row['filed_date']),'metric':metric,
                                'amount_usd':value,'measure_type':scope,'source_clause':match.group(),
                                'source_context':fragment,'source_sha256':digest,
                                'status':'rule_extracted_explicit_clause_pending_record_review',
                                'contract_start':'','contract_end':'','actual_cash_paid_usd':'',
                                'record_id':hashlib.sha256('|'.join(map(str,key)).encode()).hexdigest()[:24]})
    pd.DataFrame(records).to_csv(OUT/'cloud_contract_clauses.csv',index=False)
    pd.DataFrame(spending).to_csv(OUT/'reported_cloud_agreement_spending.csv',index=False)
    if spending:
        pd.DataFrame(spending).sort_values('filed_date').drop_duplicates(['cik','period_start','period_end','amount_usd']).to_csv(OUT/'reported_cloud_agreement_spending_first_filed.csv',index=False)
    subsidiaries=pd.read_csv(HERE/'output/subsidiaries.csv',dtype=str).fillna('')
    uk=subsidiaries[subsidiaries.jurisdiction.str.fullmatch('United Kingdom|England|England and Wales|Scotland|Wales',case=False)]
    uk=uk[uk.subsidiary_name.str.len().between(4,100)].sort_values('filing_date').drop_duplicates(['parent_cik','subsidiary_name'],keep='last').copy()
    uk['registry_match_status']='legal_entity_name_and_parent_ownership_require_registry_review'
    uk['accounts_collection_status']='API_key_present_not_yet_fetched' if env_value('COMPANIES_HOUSE_API_KEY') else 'missing_COMPANIES_HOUSE_API_KEY'
    uk['subsidiary_values_may_be_added_to_parent']=False
    uk.to_csv(OUT/'UK_subsidiary_registry_queue.csv',index=False)
    data={'cloud_explicit_clause_records':len(records),'cloud_clause_companies':len({r['ticker'] for r in records}),
          'reported_cloud_agreement_spending_records':len(spending),
          'UK_subsidiary_candidates':len(uk),'UK_parent_company_candidates':uk.parent_cik.nunique(),
          'scope_review_corrections':{'Datadog_accounts_payable_component':int(correction.sum()),'ServiceTitan_accrued_hosting':int(frame.tag.eq('ttan:CloudHostingCosts').sum())}}
    (OUT/'review_manifest.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps(data,indent=2))


if __name__=='__main__':
    main()
