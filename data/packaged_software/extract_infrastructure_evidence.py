"""Supplement public infrastructure observations without imputing private bills.

Preserves reporting periods, filing dates, dimensions and original inline values.
Custom concepts and narrative candidates require semantic review before modeling.
"""
import hashlib
import html
import json
import re
from pathlib import Path
import pandas as pd
from extract_company_metrics import HIDDEN_BLOCK, HTML_TAG

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE / 'extracts'
OUT = BASE / 'infrastructure_evidence'

STANDARD = {
    'Land': ('land_asset_balance', 'asset_balance'),
    'BuildingsAndImprovementsGross': ('buildings_gross_asset_balance', 'asset_balance'),
    'MachineryAndEquipmentGross': ('machinery_equipment_gross_asset_balance', 'asset_balance'),
    'PaymentsToAcquireMachineryAndEquipment': ('machinery_equipment_cash_purchases', 'cash_outflow'),
    'PaymentsToAcquireBuildings': ('building_cash_purchases', 'cash_outflow'),
    'PaymentsToAcquireLand': ('land_cash_purchases', 'cash_outflow'),
    'PaymentsToAcquirePropertyPlantAndEquipment': ('total_PPE_cash_purchases_not_hardware_only', 'cash_outflow'),
    'HostingArrangementServiceContractImplementationCostCapitalizedBeforeAccumulatedAmortization': ('hosting_implementation_gross_asset', 'asset_balance'),
    'HostingArrangementServiceContractImplementationCostCapitalizedAfterAccumulatedAmortization': ('hosting_implementation_net_asset', 'asset_balance'),
    'HostingArrangementServiceContractImplementationCostExpenseAmortization': ('hosting_implementation_amortization_not_cloud_bill', 'expense'),
}
MEMBERS = {
    'LandMember': 'land', 'BuildingMember': 'buildings',
    'BuildingAndBuildingImprovementsMember': 'buildings_improvements',
    'LandAndBuildingMember': 'land_and_buildings_combined',
    'LandBuildingsAndImprovementsMember': 'land_buildings_improvements_combined',
    'ComputerEquipmentMember': 'computer_equipment', 'TechnologyEquipmentMember': 'technology_equipment',
    'OfficeEquipmentMember': 'office_equipment', 'EquipmentMember': 'equipment',
    'MachineryAndEquipmentMember': 'machinery_equipment',
}
MONEY = re.compile(r'\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)\b', re.I)
CLOUD = re.compile(r'\b(?:cloud|hosting|Amazon Web Services|Microsoft Azure|Google Cloud)\b', re.I)
COMMIT = re.compile(r'\b(?:commit\w*|obligations?|minimum|non.cancel\w*)\b', re.I)


def classify(tag, dimensions, period_start):
    namespace, concept = tag.split(':', 1)
    if namespace == 'us-gaap' and concept in STANDARD:
        return (*STANDARD[concept], 'standard_concept_scope_preserved')
    members = [v.split(':')[-1] for v in json.loads(dimensions or '{}').values()]
    if namespace == 'us-gaap' and concept in ('PropertyPlantAndEquipmentGross', 'PropertyPlantAndEquipmentNet'):
        selected = [MEMBERS[v] for v in members if v in MEMBERS]
        if len(selected) == 1:
            return (selected[0] + ('_gross_asset_balance' if concept.endswith('Gross') else '_net_asset_balance'),
                    'asset_balance', 'standard_concept_and_dimension_scope_preserved')
    if re.search(r'Cloud|Hosting', concept) and not re.search(r'Revenue|Tax|SellingPrice|NumberOf|CreativeCloud|DocumentCloud', concept):
        if re.search(r'Accrued|Liabilit|IncurredButNotYetPaid', concept):
            return ('cloud_hosting_accrued_or_unpaid', 'liability_balance', 'custom_concept_requires_context_review')
        if 'Prepaid' in concept:
            return ('cloud_hosting_prepaid', 'prepaid_asset_balance', 'custom_concept_requires_context_review')
        if re.search(r'Implementation|Capitalized|Unamortized|NetBookValue', concept):
            return ('cloud_implementation_cost_or_asset', 'duration_measure' if period_start else 'asset_balance', 'custom_concept_requires_context_review')
        if re.search(r'Expense|Costs|Fees|ServicesCurrent', concept):
            # A duration concept can describe a change in expense rather than total expense.
            return ('cloud_hosting_reported_measure_scope_unresolved', 'duration_measure' if period_start else 'instant_measure', 'custom_concept_requires_context_review')
    if namespace != 'us-gaap' and re.search(r'Computer|Hardware|Server|Land|Building', concept) and re.search(r'Gross|Net|Purchase|Payment', concept) and not re.search(r'Revenue|Tax|Share|Stock|BusinessCombination', concept):
        return ('physical_asset_custom_measure_scope_unresolved', 'duration_measure' if period_start else 'instant_measure', 'custom_concept_requires_context_review')
    return None


def split_sentences(text):
    # Decimal points and abbreviated dollars must not split dollar amounts.
    return re.split(r'(?<=[.!?])\s+(?=[A-Z(])', text)


def main():
    OUT.mkdir(exist_ok=True)
    companies = pd.read_csv(HERE / 'packaged_software_companies.csv', dtype=str)
    index = pd.read_csv(BASE / 'sec/filings_index.csv', dtype=str).fillna('')
    lookup = {(r.cik, r.accession, r.primary_document): r for r in index.itertuples()}
    tagged = pd.read_csv(BASE / 'company_coverage/tagged_asset_cloud_facts_expanded.csv', dtype=str).fillna('')
    selected = []
    docs = {}
    for r in tagged.to_dict('records'):
        result = classify(r['tag'], r['dimensions'], r['period_start'])
        if not result or r['numeric_status'] != 'parsed_reported_inline_xbrl' or r['unit'] not in ('iso4217:USD', 'USD'):
            continue
        filename = r['source_url'].split('/')[-1]
        filing = lookup.get((r['cik'], r['accession'], filename))
        if filing is None:
            continue
        selected.append({**r, 'metric': result[0], 'measure_type': result[1], 'semantic_status': result[2],
                         'local_path': filing.local_path,
                         'observation_id': hashlib.sha256('|'.join(r[k] for k in ['cik','tag','context_id','accession','raw_value']).encode()).hexdigest()[:24]})
        docs.setdefault(filing.local_path, []).append(selected[-1])
    # Only a small source window is retained. Raw files remain authoritative.
    for i,(path, rows) in enumerate(docs.items(),1):
        content=(ROOT / path).read_bytes()
        raw=content.decode('utf-8',errors='replace')
        digest=hashlib.sha256(content).hexdigest()
        for r in rows:
            pattern = re.compile(r'<ix:nonfraction\b(?=[^>]*\bname=[\"\']' + re.escape(r['tag']) + r'[\"\'])(?=[^>]*\bcontextref=[\"\']' + re.escape(r['context_id']) + r'[\"\'])[^>]*>.*?</ix:nonfraction\s*>', re.I | re.S)
            match = pattern.search(raw)
            r['source_element_found'] = match is not None
            r['source_sha256'] = digest
            r['source_context_excerpt'] = ' '.join(html.unescape(HTML_TAG.sub(' ', raw[max(0,match.start()-850):match.end()+300])).split()) if match else ''
        if i==1 or i%200==0: print(f'Source windows {i}/{len(docs)}',flush=True)
    frame = pd.DataFrame(selected)
    frame.to_csv(OUT / 'reported_infrastructure_observations.csv', index=False)
    keys = ['cik','tag','unit','period_start','period_end','dimensions','value']
    frame.sort_values(['filed_date','accession']).drop_duplicates(keys).to_csv(OUT / 'infrastructure_observations_first_filed.csv', index=False)
    evidence = pd.read_csv(BASE / 'company_coverage/disclosure_evidence_expanded.csv', dtype=str).fillna('')
    candidates=[]; seen=set()
    for r in evidence[evidence.category.eq('cloud')].to_dict('records'):
        for sentence in split_sentences(r['excerpt']):
            if not CLOUD.search(sentence) or not COMMIT.search(sentence):
                continue
            normalized=' '.join(sentence.split())
            for money in MONEY.finditer(sentence):
                key=(r['cik'],normalized,money.start())
                if key in seen: continue
                seen.add(key)
                multiplier={'million':1e6,'billion':1e9,'thousand':1e3}[money[2].lower()]
                candidates.append({**{k:r[k] for k in ['cik','ticker','name','filed_date','source_url','local_path','evidence_id']},
                                   'sentence':sentence, 'amount_usd_candidate':float(money[1].replace(',',''))*multiplier,
                                   'raw_amount':money.group(),'status':'unreviewed_amount_scope_not_a_confirmed_cloud_bill'})
    pd.DataFrame(candidates).to_csv(OUT / 'cloud_commitment_amount_candidates.csv', index=False)
    coverage=[]
    for c in companies.to_dict('records'):
        f=frame[frame.cik.eq(c['cik'])]
        coverage.append({**c,'tagged_observations':len(f),'tagged_source_element_matches':int(f.source_element_found.sum()),
                         'standard_scoped_observations':int(f.semantic_status.str.startswith('standard_').sum()),
                         'custom_observations_requiring_review':int(f.semantic_status.str.startswith('custom_').sum()),
                         'land_balance_observations':int(f.metric.eq('land_gross_asset_balance').sum()+f.metric.eq('land_asset_balance').sum()),
                         'computer_equipment_observations':int(f.metric.eq('computer_equipment_gross_asset_balance').sum()+f.metric.eq('computer_equipment_net_asset_balance').sum()),
                         'cloud_hosting_observations':int(f.metric.str.startswith('cloud_').sum()),
                         'status':'reported_observations_found_not_complete_spend' if len(f) else 'no_selected_tagged_observation_not_zero'})
    pd.DataFrame(coverage).to_csv(OUT / 'infrastructure_coverage_168.csv',index=False)
    result={'target_companies':len(coverage),'tagged_observations':len(frame),'companies_with_observations':frame.cik.nunique(),
            'source_elements_not_found':int((~frame.source_element_found).sum()),'cloud_amount_candidates':len(candidates),
            'standard_scoped_companies':frame[frame.semantic_status.str.startswith('standard_')].cik.nunique(),
            'limitations':['Custom concept semantics and narrative amounts require review.', 'Assets, liabilities, expenses and purchases remain separate.',
                           'No private invoices or undisclosed amounts inferred.','Source scope is previously indexed SEC filings since 2022; no complete-history claim.']}
    (OUT / 'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
