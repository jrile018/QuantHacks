"""Reparse retained source elements and contexts for every infrastructure number."""
import hashlib
import json
import math
import re
import sys
import pandas as pd
from extract_infrastructure_evidence import OUT, ROOT
from extract_company_metrics import FilingText, INLINE_BLOCK, RESOURCE_BLOCK, parse_relevant_filing


def main():
    frame=pd.read_csv(OUT/'reported_infrastructure_observations.csv',dtype=str).fillna('')
    failures=[]; matched=0; fallback_count=0
    previous=None
    if '--retry-failed' in sys.argv:
        previous=json.loads((OUT/'numeric_source_validation.json').read_text())
        matched=previous['observations_matching_original_inline_values_units_periods_dimensions_and_source_hash']
        frame=frame[frame.observation_id.isin([r['observation_id'] for r in previous['failures']])]
    groups=list(frame.groupby('local_path',sort=False))
    for i,(path,rows) in enumerate(groups,1):
        content=(ROOT/path).read_bytes(); raw=content.decode('utf-8',errors='replace')
        digest=hashlib.sha256(content).hexdigest()
        parser=FilingText()
        wanted={(r.tag.lower(),r.context_id.lower()) for r in rows.itertuples()}
        for block in INLINE_BLOCK.finditer(raw):
            head=block.group().split('>',1)[0]
            tag=re.search(r'\bname=[\"\']([^\"\']+)',head,re.I)
            ctx=re.search(r'\bcontextref=[\"\']([^\"\']+)',head,re.I)
            if tag and ctx and (tag[1].lower(),ctx[1].lower()) in wanted:
                parser.feed(block.group())
        contexts={f['attrs'].get('contextref','') for f in parser.inline}
        units={f['attrs'].get('unitref','') for f in parser.inline}
        for block in RESOURCE_BLOCK.finditer(raw):
            head=block.group().split('>',1)[0]
            identifier=re.search(r'\bid=[\"\']([^\"\']+)',head,re.I)
            if identifier and identifier[1] in contexts|units:
                parser.feed(block.group())
        if previous is not None:
            parser,_=parse_relevant_filing(raw)
        facts={(f['tag'],f['context_id'],f['raw_value']):f for f in parser.tagged_facts()}
        full_facts=None
        for r in rows.to_dict('records'):
            f=facts.get((r['tag'],r['context_id'],r['raw_value']))
            # Optimized fragment parsing can omit nested markup or context resources.
            # Retry the retained full document before calling an observation a mismatch.
            if f is None and previous is None:
                if full_facts is None:
                    full_parser,_=parse_relevant_filing(raw)
                    full_facts={(v['tag'],v['context_id'],v['raw_value']):v for v in full_parser.tagged_facts()}
                f=full_facts.get((r['tag'],r['context_id'],r['raw_value']))
                if f is not None: fallback_count+=1
            valid=f is not None and digest==r['source_sha256']
            if valid:
                valid=all(f[k]==r[k] for k in ['unit','period_start','period_end','dimensions'])
                valid=valid and isinstance(f['value'],(int,float)) and math.isclose(float(r['value']),f['value'],rel_tol=1e-12,abs_tol=1e-6)
            if valid: matched+=1
            else: failures.append({'observation_id':r['observation_id'],'ticker':r['ticker'],'source_path':path})
        if i==1 or i%300==0: print(f'Numeric source verification {i}/{len(groups)}',flush=True)
    result={'reported_observations':previous['reported_observations'] if previous else len(frame),'observations_matching_original_inline_values_units_periods_dimensions_and_source_hash':matched,
            'full_document_parser_fallback_observations':len(frame) if previous else fallback_count,
            'failures':failures,'interpretation':'Verifies extraction fidelity. Custom-concept semantics and historical issuer/corporate-action interpretation remain separate checks.'}
    (OUT/'numeric_source_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='failures'},indent=2))
    if failures: raise ValueError(f'{len(failures)} source mismatches')


if __name__=='__main__':
    main()
