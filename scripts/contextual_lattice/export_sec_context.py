#!/usr/bin/env python3
"""Export a bounded, conservative SEC context from existing real cache only."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

CIKS = {'AAPL':'0000320193','MSFT':'0000789019','AMZN':'0001018724','GOOGL':'0001652044','META':'0001326801','NVDA':'0001045810','JPM':'0000019617','BAC':'0000070858','XOM':'0000034088','CVX':'0000093410','UNH':'0000731766','GD':'0000040533'}

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def write_csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8') as stream:
        w=csv.DictWriter(stream,fieldnames=fields);w.writeheader();w.writerows(rows)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=False)
    filings=[];coverage=[];hashes={};errors=[]
    for ticker,cik in CIKS.items():
        main_file=args.cache/f'sec_submissions_CIK{cik}.body'
        problems=[];payloads=[];identity=False;expected=[]
        try:
            data=json.loads(main_file.read_text(encoding='utf-8'))
            if str(data.get('cik','')).zfill(10)!=cik or ticker not in data.get('tickers',[]):
                raise ValueError('cached main CIK/ticker identity mismatch')
            identity=True;hashes[str(main_file)]=digest(main_file)
            payloads.append((main_file,data.get('filings',{}).get('recent',{})))
            expected=data.get('filings',{}).get('files',[])
            for page in expected:
                name=page.get('name','')
                if not name.startswith(f'CIK{cik}-submissions-') or '/' in name or '\\' in name:
                    problems.append('invalid referenced page name');continue
                path=args.cache/f'sec_submissions_page_{name}.body'
                try:
                    body=json.loads(path.read_text(encoding='utf-8'))
                    hashes[str(path)]=digest(path)
                    payloads.append((path,body))
                except Exception as exc:
                    problems.append(f'{name}: {type(exc).__name__}')
        except Exception as exc:
            problems.append(f'main: {type(exc).__name__}: {exc}')
        seen=set();dates=[];count=0
        for path,table in payloads:
            forms=table.get('form',[]);file_dates=table.get('filingDate',[]);accs=table.get('accessionNumber',[])
            if not(len(forms)==len(file_dates)==len(accs)):
                problems.append(f'{path.name}: unaligned submission columns');continue
            acceptance=table.get('acceptanceDateTime',[]);items=table.get('items',[])
            for index,form in enumerate(forms):
                if form!='8-K':continue
                accession=accs[index]
                if accession in seen:continue
                seen.add(accession);date=file_dates[index]
                try: datetime.strptime(date,'%Y-%m-%d')
                except ValueError: problems.append('invalid filingDate');continue
                dates.append(date);count+=1
                filings.append({'ticker':ticker,'cik':cik,'form':form,'filing_date':date,'acceptance_datetime':'','original_acceptance_datetime':acceptance[index] if index<len(acceptance) else '', 'accession':accession,'items':items[index] if index<len(items) else '', 'source_path':str(path),'source_sha256':hashes[str(path)],'clock_note':'conservative next calendar day availability; original acceptance retained but not trusted as first-public/receipt clock'})
        status='complete' if identity and not problems and count else 'partial' if count else 'unknown'
        coverage.append({'ticker':ticker,'status':status,'scope':'retrospective official SEC 8-K population; not complete news/earnings or historical live monitoring','first_filing_date':min(dates) if dates else '', 'last_filing_date':max(dates) if dates else '', 'count_8k':count,'referenced_pages':len(expected),'problems':' | '.join(problems)})
        if problems:errors.append({'ticker':ticker,'problems':problems})
    filings.sort(key=lambda r:(r['ticker'],r['filing_date'],r['accession']))
    write_csv(args.output/'filings.csv',filings,['ticker','cik','form','filing_date','acceptance_datetime','original_acceptance_datetime','accession','items','source_path','source_sha256','clock_note'])
    write_csv(args.output/'coverage.csv',coverage,['ticker','status','scope','first_filing_date','last_filing_date','count_8k','referenced_pages','problems'])
    receipt={'created_at_utc':datetime.now(timezone.utc).isoformat(),'source':'existing cache only; no network request','source_files_sha256':hashes,'filings':len(filings),'coverage':coverage,'errors':errors,'interpretation':'known SEC filing context, not news tone, surprise or proof of earliest publication'}
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'filings':len(filings),'complete_SEC_populations':sum(r['status']=='complete' for r in coverage),'errors':len(errors)}))
    return 0

if __name__=='__main__':raise SystemExit(main())
