"""Audit financial lineage and publish a conservative metric-level layer, without changing raw data."""
import hashlib
import json
import math
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import pandas as pd
from extract_company_metrics import RATIOS

HERE=Path(__file__).resolve().parent
BASE=HERE/'extracts'
SRC=BASE/'company_metrics_expanded'
OUT=BASE/'financial_quality'


def close(a,b): return math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=1e-6)
def days(a,b): return (date.fromisoformat(b)-date.fromisoformat(a)).days
def tomorrow(day): return (date.fromisoformat(day)+timedelta(days=1)).isoformat()


def quarter_from_refs(refs,end):
    candidates=[f for f in refs if f['period_end']==end and f['period_start']]
    direct=[f for f in candidates if 80<=days(f['period_start'],end)<=100]
    if direct:
        f=min(direct,key=lambda x:(x['filed_date'],x['fact_id']))
        return float(f['value']),f['period_start'],False
    for current in sorted(candidates,key=lambda x:(x['filed_date'],x['fact_id'])):
        priors=[f for f in refs if f['tag']==current['tag'] and f['unit']==current['unit'] and
                f['period_start']==current['period_start'] and 80<=days(f['period_end'],end)<=100]
        if priors:
            prior=min(priors,key=lambda f:(f['accession']!=current['accession'],f['filed_date'],f['fact_id']))
            return float(current['value'])-float(prior['value']),tomorrow(prior['period_end']),prior['accession']!=current['accession']
    raise ValueError('quarter inputs cannot be reconstructed')


def calculate(row,refs):
    method=row['method']; end=row['period_end']
    if method in ['reported_quarter','reported_instant','reported_annual_ttm']:
        if len(refs)!=1: raise ValueError('reported observation must reference one fact')
        f=refs[0]
        if f['period_end']!=end: raise ValueError('reported fact period differs')
        if method=='reported_quarter' and not 80<=days(f['period_start'],end)<=100: raise ValueError('invalid quarter duration')
        if method=='reported_annual_ttm' and not 350<=days(f['period_start'],end)<=380: raise ValueError('invalid annual duration')
        return float(f['value']),f['period_start'],False
    if method=='ytd_difference':
        if len(refs)!=2: raise ValueError('YTD difference requires two inputs')
        prior,current=sorted(refs,key=lambda f:f['period_end'])
        if current['period_end']!=end or current['period_start']!=prior['period_start'] or current['tag']!=prior['tag']:
            raise ValueError('incompatible YTD periods or tags')
        if not 80<=days(prior['period_end'],end)<=100: raise ValueError('YTD difference is not a quarter')
        return float(current['value'])-float(prior['value']),tomorrow(prior['period_end']),current['accession']!=prior['accession']
    if method=='four_consecutive_quarters':
        ends=sorted({f['period_end'] for f in refs if f['period_end']<=end})[-4:]
        if len(ends)!=4 or ends[-1]!=end or any(not 80<=days(a,b)<=100 for a,b in zip(ends,ends[1:])):
            raise ValueError('TTM quarter boundaries incomplete')
        qs=[quarter_from_refs(refs,e) for e in ends]
        if any(abs(days(tomorrow(a),q[1]))>3 for a,q in zip(ends,qs[1:])): raise ValueError('TTM quarter intervals not consecutive')
        return sum(q[0] for q in qs),qs[0][1],any(q[2] for q in qs)
    if method=='quarter_over_prior_year_quarter_minus_one':
        ends=[f['period_end'] for f in refs if 350<=days(f['period_end'],end)<=380]
        if not ends: raise ValueError('prior-year quarter missing')
        prior=min(set(ends),key=lambda e:abs(days(e,end)-365))
        current=quarter_from_refs(refs,end); previous=quarter_from_refs(refs,prior)
        if previous[0]<=0: raise ValueError('nonpositive growth denominator')
        return current[0]/previous[0]-1,current[1],current[2] or previous[2]
    raise ValueError('unhandled derivation method: '+method)


def main():
    OUT.mkdir(exist_ok=True)
    facts=pd.read_csv(SRC/'reported_financial_facts.csv',dtype=str).fillna('')
    lineage=pd.read_csv(SRC/'quarterly_metric_sources.csv',dtype=str).fillna('')
    wide=pd.read_csv(SRC/'fundamentals_quarterly.csv',dtype={'cik':str}).fillna('')
    lookup=facts.set_index('fact_id').to_dict('index')
    for fid,f in lookup.items(): f['fact_id']=fid
    source_ok=set(); mismatches=[]; source_hashes={}
    for ticker,group in facts.groupby('ticker'):
        path=BASE/'sec'/ticker/'companyfacts.json'; body=path.read_bytes()
        source_hashes[ticker]=hashlib.sha256(body).hexdigest(); raw=json.loads(body)
        keys=set()
        for taxonomy,concepts in raw.get('facts',{}).items():
            for tag,concept in concepts.items():
                for unit,observations in concept.get('units',{}).items():
                    for f in observations:
                        keys.add((taxonomy,tag,unit,f.get('start',''),f.get('end',''),f.get('filed',''),f.get('accn',''),f.get('form',''),float(f['val'])))
        for f in group.to_dict('records'):
            key=(f['taxonomy'],f['tag'],f['unit'],f['period_start'],f['period_end'],f['filed_date'],f['accession'],f['form'],float(f['value']))
            if key in keys: source_ok.add(f['fact_id'])
            else: mismatches.append(f['fact_id'])
    results=[]
    for row in lineage.to_dict('records'):
        ids=row['source_fact_ids'].split(';'); refs=[lookup[i] for i in ids if i in lookup]
        reasons=[]; arithmetic=False; computed=None; start=''; cross=False
        if len(refs)!=len(ids): reasons.append('missing_source_reference')
        if not all(i in source_ok for i in ids): reasons.append('source_mismatch')
        if any(f['cik']!=row['cik'] or (row['basis']!='ratio' and f['metric']!=row['metric']) for f in refs): reasons.append('issuer_or_metric_mismatch')
        if refs and row['available_date_conservative']<tomorrow(max(f['filed_date'] for f in refs)): reasons.append('availability_before_source_filing')
        if refs and any(f['unit']!='USD' for f in refs): reasons.append('unit_scope_mismatch')
        try:
            computed,start,cross=calculate(row,refs)
            arithmetic=close(computed,row['value'])
            if not arithmetic: reasons.append('arithmetic_mismatch')
        except (ValueError,KeyError) as exc: reasons.append(str(exc))
        numerical_ok=not reasons
        if cross or row['quality']=='cross_filing_basis_unverified': reasons.append('cross_filing_accounting_basis_unresolved')
        results.append({**row,'recomputed_value':computed,'validated_period_start':start,
                        'source_arithmetic_date_checks_pass':numerical_ok,'eligible_for_conservative_layer':not reasons,
                        'review_reason':';'.join(reasons) or 'source_arithmetic_and_date_checks_pass_accounting_semantics_not_independently_audited'})
    gates=pd.DataFrame(results)
    gates.to_csv(OUT/'metric_validation.csv',index=False)
    gates[~gates.eligible_for_conservative_layer].to_csv(OUT/'metric_review_queue.csv',index=False)
    keyed={(r['cik'],r['period_end'],r['basis'],r['metric']):r for r in results}
    clean=[]; ratio_records=[]
    for raw in wide.to_dict('records'):
        row={k:raw[k] for k in ['cik','ticker','name','period_start','period_end']}; used=[]
        def get(basis,metric):
            r=keyed.get((raw['cik'],raw['period_end'],basis,metric))
            return r if r and r['eligible_for_conservative_layer'] else None
        for field,value in raw.items():
            if field in row or field in RATIOS or field in ['available_date_conservative','history_limitation','derivation_quality']: continue
            basis,metric=('quarter',field[2:]) if field.startswith('q_') else (('ttm',field[4:]) if field.startswith('ttm_') else ('instant',field))
            gate=get(basis,metric); row[field]=float(gate['value']) if gate else ''
            if gate: used.append(gate['available_date_conservative'])
        def ratio(name,numerator,denominator):
            inputs=[get(b,m) for b,m in list(numerator)+list(denominator)]
            ready=all(r is not None for r in inputs)
            duration=[r['validated_period_start'] for r in inputs if r and r['basis']=='ttm']
            if duration and any(abs(days(duration[0],s))>3 for s in duration): ready=False
            if ready:
                nv=sum(sign*float(inputs[i]['value']) for i,sign in enumerate(numerator.values()))
                dv=sum(sign*float(inputs[len(numerator)+i]['value']) for i,sign in enumerate(denominator.values()))
                ready=dv>0
            row[name]=nv/dv if ready else ''
            available=max(r['available_date_conservative'] for r in inputs) if ready else ''
            if ready: used.append(available)
            ratio_records.append({**{k:raw[k] for k in ['cik','ticker','name','period_end']},'metric':name,'value':row[name],
                                  'available_date_conservative':available,'eligible_for_conservative_layer':ready,
                                  'dependencies':';'.join(b+':'+m for b,m in list(numerator)+list(denominator)),
                                  'status':'passing_dependencies' if ready else 'missing_unresolved_or_incompatible_dependencies'})
        rev={('ttm','revenue'):1}
        for name,metric in [('rd_pct_rev','rd_expense'),('software_rd_pct_rev','software_rd_expense_excluding_acquired_in_process'),('sm_pct_rev','sales_marketing'),('sbc_pct_rev','stock_comp'),('physical_capex_pct_rev','physical_asset_purchases')]:
            ratio(name,{('ttm',metric):1},rev)
        gross={('ttm','gross_profit'):1} if get('ttm','gross_profit') else {('ttm','revenue'):1,('ttm','cost_of_revenue'):-1}
        ratio('gross_margin',gross,rev)
        ratio('fcf_physical_capex_margin',{('ttm','operating_cash_flow'):1,('ttm','physical_asset_purchases'):-1},rev)
        ratio('goodwill_to_assets',{('instant','goodwill'):1},{('instant','total_assets'):1})
        ratio('purchase_obligations_pct_ttm_rev',{('instant','purchase_obligations'):1},rev)
        growth=get('ratio','rev_growth_yoy_q'); row['rev_growth_yoy_q']=float(growth['value']) if growth else ''
        if growth: used.append(growth['available_date_conservative'])
        row['available_date_conservative']=max(used) if used else ''
        row['layer_status']='metric_checks_pass_not_full_historical_vintage_or_independent_accounting_audit'
        clean.append(row)
    reviewed=pd.DataFrame(clean); reviewed.to_csv(OUT/'fundamentals_quarterly_conservative.csv',index=False)
    pd.DataFrame(ratio_records).to_csv(OUT/'ratio_dependency_validation.csv',index=False)
    coverage=[]
    for field in wide.columns:
        if field.startswith(('q_','ttm_')) or field in RATIOS:
            original=wide[field].ne(''); retained=reviewed[field].ne('')
            coverage.append({'metric':field,'original_nonmissing_rows':int(original.sum()),'retained_nonmissing_rows':int(retained.sum()),
                             'retained_company_count':reviewed.loc[retained,'cik'].nunique(),'withheld_rows':int((original & ~retained).sum())})
    pd.DataFrame(coverage).to_csv(OUT/'coverage_before_after.csv',index=False)
    checks={'audited_at_utc':datetime.now(timezone.utc).isoformat(),'reported_facts':len(facts),'source_matches':len(source_ok),
            'source_mismatches':len(mismatches),'duplicate_fact_ids':int(facts.fact_id.duplicated().sum()),
            'duplicate_company_periods':int(wide.duplicated(['cik','period_end']).sum()),
            'lineage_rows':len(gates),'source_arithmetic_date_checks_pass':int(gates.source_arithmetic_date_checks_pass.sum()),
            'eligible_metric_observations':int(gates.eligible_for_conservative_layer.sum()),
            'withheld_metric_observations':int((~gates.eligible_for_conservative_layer).sum()),
            'reasons':gates.review_reason.value_counts().to_dict(),'quarterly_rows_preserved':len(reviewed),
            'target_companies':reviewed.cik.nunique(),'source_companyfacts_sha256':source_hashes,
            'limitation':'Conservative source/arithmetic/date gating, not independent accounting certification or proof of complete historical vintages.'}
    checks['output_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.csv')}
    (OUT/'audit.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    (OUT/'REPORT.md').write_text('# Financial quality review\n\n'+json.dumps({k:v for k,v in checks.items() if k not in ['source_companyfacts_sha256','output_sha256']},indent=2)+'\n\nRaw files are unchanged. Cross-filing uncertainty is withheld at metric level. Dependent ratios are rebuilt only from passing inputs with aligned TTM periods. This reduces coverage rather than imputing unreported values. Use long-form validation tables for metric-specific availability; the wide row date is the latest retained input date.\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in checks.items() if k not in ['source_companyfacts_sha256','output_sha256','reasons']},indent=2))


if __name__=='__main__': main()
