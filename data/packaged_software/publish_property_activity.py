"""Build a review queue and honest 168-company coverage for keyless property collection."""
import hashlib
import json
import re
import pandas as pd
from collect_public_property_activity import OUT, HERE, ROOT


def read(name):
    path=OUT/name
    if not path.exists() or path.stat().st_size<3: return pd.DataFrame()
    return pd.read_csv(path,dtype=str).fillna('')


def main():
    manifest=json.loads((OUT/'collection_manifest.json').read_text())
    for path in OUT.glob('*_collection_result.json'):
        manifest[path.name.replace('_collection_result.json','')]=json.loads(path.read_text())
    sources_checked=0
    for metadata in (OUT/'raw').glob('*.json'):
        record=json.loads(metadata.read_text())
        assert hashlib.sha256(metadata.with_suffix('.bin').read_bytes()).hexdigest()==record['sha256']
        sources_checked+=1
    sec=read('sec_property_activity_candidates.csv')
    if len(sec):
        sec['explicit_purchase_language_candidate']=sec.context.str.contains(r'\b(?:purchased|acquired|purchase agreement|purchase and sale|acquisition of)\b',case=False,regex=True)
        sec['review_priority']=sec.apply(lambda r: 1 if r.event_type_candidate=='data_center_activity' and r.explicit_purchase_language_candidate else (2 if r.explicit_purchase_language_candidate else 3),axis=1)
        sec.sort_values(['review_priority','ticker','filing_date']).to_csv(OUT/'sec_property_review_queue.csv',index=False)
    sj=read('san_jose_permit_candidates.csv'); nyc=read('nyc_acris_recorded_document_candidates_since_2022.csv')
    if len(sj):
        for path,group in sj.groupby('local_path'):
            raw=json.loads((ROOT/path).read_bytes())
            features={str(f['attributes']['OBJECTID']):f['attributes'] for f in raw['features']}
            for row in group.itertuples():
                assert features[row.permit_object_id]==json.loads(row.attributes_json)
    if len(nyc):
        for path,group in nyc.groupby('master_local_path'):
            originals={r['document_id']:r for r in json.loads((ROOT/path).read_bytes())}
            for row in group.itertuples():
                original=originals[row.document_id]
                assert original['doc_type']==row.doc_type and original['recorded_datetime']==row.recorded_datetime
                assert float(original.get('document_amt',0))==float(row.document_amt or 0)
    transfers=[]
    codes=read('nyc_document_control_codes.csv'); parties=read('reviewed_deed_supporting_parties.csv')
    if len(nyc) and len(codes) and len(parties):
        selected=nyc[nyc.document_id.eq('2025121600382004') & nyc.ticker.eq('TTWO')]
        if len(selected)!=1: raise ValueError('Reviewed Take-Two deed missing or ambiguous')
        deed=selected.iloc[0].to_dict()
        code=codes[codes.doc__type.eq('DEED')].iloc[0]
        buyer=parties[parties.party_type.eq('2')].iloc[0]
        if deed['doc_type']!='DEED' or code.party2_type!='GRANTEE/BUYER' or buyer['name']!='TAKE-TWO INTERACTIVE SOFTWARE, INC.':
            raise ValueError('Reviewed deed buyer role changed')
        original=[r for r in json.loads((ROOT/deed['master_local_path']).read_bytes()) if r['document_id']==deed['document_id']]
        if len(original)!=1 or original[0]['doc_type']!='DEED' or float(original[0]['document_amt'])!=6000000 or float(deed['document_amt'])!=6000000:
            raise ValueError('Reviewed deed amount does not match original city response')
        if deed['recorded_datetime'][:10]!='2025-12-16' or deed['document_date'][:10]!='2025-12-12':
            raise ValueError('Reviewed deed dates changed')
        parcels=read('nyc_acris_parcel_records.csv')
        parcel=parcels[parcels.document_id.eq(deed['document_id'])].iloc[0].to_dict()
        transfers.append({**deed,'status':'source_reviewed_recorded_deed_explicit_named_buyer',
                          'buyer_role':code.party2_type,'seller_name':parties[parties.party_type.eq('1')].iloc[0]['name'],
                          'recorded_document_amount_usd':deed['document_amt'],
                          'property_address':parcel['street_number']+' '+parcel['street_name'],
                          'unit':parcel['unit'],'borough':parcel['borough'],'block':parcel['block'],'lot':parcel['lot'],
                          'parcel_source_sha256':parcel['source_sha256'],
                          'party_role_code_source_sha256':code['sha256'],
                          'supporting_parties_source_sha256':buyer['sha256'],
                          'actual_cash_spent_usd':'','data_center_use_confirmed':False,
                          'interpretation':'Named buyer and recorded deed amount verified against structured city records. Deed image, acquisition accounting, title and data-center use not independently reviewed.'})
        pd.DataFrame(transfers).to_csv(OUT/'reviewed_recorded_property_transfers.csv',index=False)
    reviewed_permits=[]
    if len(sj):
        sj['permit_family']=sj.layer.map(lambda layer:'planning' if layer=='23' else 'building')
        sj['permit_identifier']=sj.attributes_json.map(lambda value:json.loads(value).get('FOLDERNUM',''))
        sj['parcel_identifier']=sj.attributes_json.map(lambda value:json.loads(value).get('APN',''))
        sj.drop_duplicates(['ticker','permit_family','permit_identifier','parcel_identifier']).to_csv(OUT/'san_jose_unique_permit_candidates.csv',index=False)
        dated=sj[sj.permit_issue_date.ge(manifest['period_start']) & sj.permit_issue_date.le(manifest['observed_date'])]
        dated.to_csv(OUT/'san_jose_permit_candidates_since_2022.csv',index=False)
        # Individually read public records: explicit corporate applicant and data-center use.
        for layer,oid,expected_folder in [('8','200443','2025-145276-CI'),('23','256296','144016')]:
            selected=sj[sj.layer.eq(layer)&sj.permit_object_id.eq(oid)&sj.ticker.eq('MSFT')]
            if len(selected)!=1: raise ValueError('Reviewed municipal permit missing or ambiguous')
            row=selected.iloc[0].to_dict(); attributes=json.loads(row['attributes_json'])
            raw=json.loads((ROOT/row['local_path']).read_bytes())
            original=[f['attributes'] for f in raw['features'] if str(f['attributes']['OBJECTID'])==oid]
            if original!=[attributes]: raise ValueError('Reviewed permit attributes do not match original municipal response')
            if attributes['APPLICANT'].strip().upper()!='MICROSOFT CORPORATION' or attributes['FOLDERNUM']!=expected_folder:
                raise ValueError('Reviewed applicant or permit changed')
            if layer=='8' and (attributes['SUBDESC']!='Data Center' or attributes['PERMITVALUE']!=385576931):
                raise ValueError('Reviewed permit use or declared value changed')
            reviewed_permits.append({**row,'status':'source_reviewed_explicit_Microsoft_applicant_data_center_permit',
                                     'address':attributes['ADDRESS'],'parcel_id':attributes['APN'],
                                     'permit_number':attributes['FOLDERNUM'],'work_description':attributes.get('FOLDERDESC',attributes['WORKDESC']),
                                     'reported_area_sqft':attributes.get('SQUAREFOOT',''),
                                     'ownership_purchase_confirmed':False,
                                     'interpretation':'Construction/adjustment permit; declared value is not cash spent or a land purchase price.'})
        pd.DataFrame(reviewed_permits).to_csv(OUT/'reviewed_data_center_permit_events.csv',index=False)
    targets=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str)
    rows=[]
    for company in targets.to_dict('records'):
        ticker=company['ticker']
        s=sec[sec.ticker.eq(ticker)] if len(sec) else sec
        j=sj[sj.ticker.eq(ticker)] if len(sj) else sj
        n=nyc[nyc.ticker.eq(ticker)] if len(nyc) else nyc
        rows.append({**company,'SEC_property_narrative_candidates':len(s),
                     'SEC_data_center_narrative_candidates':int(s.event_type_candidate.eq('data_center_activity').sum()) if len(s) else 0,
                     'San_Jose_permit_name_match_candidates':len(j),
                     'San_Jose_dated_permit_candidates_since_2022':int(j.permit_issue_date.ge(manifest['period_start']).sum()) if len(j) else 0,
                     'NYC_recorded_document_party_candidates_since_2022':len(n),
                     'reviewed_data_center_permit_events':sum(r['ticker']==ticker for r in reviewed_permits),
                     'reviewed_named_buyer_deed_records':sum(r['ticker']==ticker for r in transfers),
                     'confirmed_property_purchase_count':'','confirmed_data_center_purchase_spend_usd':'',
                     'coverage_status':'public_source_candidates_require_review' if len(s)+len(j)+len(n) else 'no_candidate_found_in_sources_searched_not_proof_of_no_activity',
                     'historical_completeness':'partial_source_coverage_not_complete_since_2022'})
    pd.DataFrame(rows).to_csv(OUT/'property_activity_coverage_168.csv',index=False)
    manifest['publication']={'target_status_rows':len(rows),'raw_public_response_hashes_verified':sources_checked,
                             'confirmed_property_purchase_metrics_published':0,
                             'reviewed_data_center_permit_events':len(reviewed_permits),
                             'reviewed_named_buyer_deed_records':len(transfers),
                             'permit_attribute_rows_matching_raw_responses':len(sj),
                             'recorded_document_candidate_rows_matching_raw_type_date_amount':len(nyc),
                             'candidate_companies_any_source':sum(r['coverage_status']=='public_source_candidates_require_review' for r in rows),
                             'SEC_review_queue_rows':len(sec)}
    manifest['output_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.csv')}
    (OUT/'collection_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    report=f'''# Keyless property and data-center activity collection

Requested period: {manifest['period_start']} onward. Public snapshots observed {manifest['observed_date']} (UTC). All 168 target companies have an explicit status row. No API keys used.

## Collection results

```
{json.dumps({k:v for k,v in manifest.items() if k not in ['output_sha256','publication']},indent=2)}
```

## Review files

- `property_activity_coverage_168.csv`: candidate counts by company; missing purchase prices stay blank.
- `sec_property_review_queue.csv`: SEC narrative candidates, with data-center and explicit purchase-language candidates prioritized. Filings retain their actual next-day availability. A reference to customer projects, risk factors, acquisitions of whole businesses or ordinary office leases is not automatically a property purchase by the issuer.
- `san_jose_permit_candidates.csv`: municipal permit attributes, parcel numbers, descriptions and dates. Declared permit values are estimates, not purchase prices or actual cash spending. Active, expired and selected planning layers have limited histories; planned, cancelled, completed or removed projects may be absent. Name matches require entity and site review.
- `nyc_acris_recorded_document_candidates_since_2022.csv`: parent-name matches joined to recorded document details. Mortgages, liens and leases are not purchases; document amounts and party roles require review. This pass does not comprehensively cover subsidiary buyers or locations outside NYC.
- `nyc_acris_parcel_records.csv`: supporting parcel identifiers for matching recorded documents.
- `reviewed_recorded_property_transfers.csv`: one source-reviewed Take-Two named-buyer deed at 1619 Broadway, unit 3, dated December 12, 2025 and recorded December 16, 2025, with a $6m recorded document amount. Buyer role is checked against the official document-code table and full document-party records. Data-center use, the deed image and actual accounting cash expenditure remain unverified.
- `reviewed_data_center_permit_events.csv`: two individually source-reviewed Microsoft data-center permits at 1657 Alviso-Milpitas Road. The February 18, 2026 construction permit reports 245,000 square feet and a declared permit value of $385,576,931; the December 8, 2025 record approves a major permit adjustment. They are not purchases or evidence of actual expenditure. Different parcel identifiers are preserved, not silently reconciled.
- `virginia_data_center_air_permits_since_2022.csv`: geographic data-center permit inventory, including operators outside our universe. No operator-to-parent mapping or purchase is inferred merely from site presence.
- `raw/`: retained public responses and request URLs, retrieval timestamps and SHA256 hashes. {sources_checked} cached public responses pass hash verification.

## Historical and ownership limits

Current municipal records retain their stated issue/recording dates, but use the observed snapshot date plus one day for conservative model availability. Historical issuance alone does not prove when the record was publicly accessible or that current attributes existed then. Revisions and ownership changes need dated source review. Subsidiary matching and linking office properties to data-center use remain unfinished. No missing values are zero-filled and no confirmed purchase-spending metrics are published from these candidates.
'''
    (OUT/'REPORT.md').write_text(report,encoding='utf-8')
    print(json.dumps(manifest['publication'],indent=2))


if __name__=='__main__': main()
