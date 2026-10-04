"""Apply seven source-reviewed public-float overrides; preserve original API values."""
import hashlib
import html
import re
from pathlib import Path
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=HERE/'extracts'
OUT=BASE/'gap_recovery'
# Individually checked against the explicit dollar amounts on original 10-K covers.
REVIEWED={('GEG','2022-12-30'):36204379,('GEG','2023-12-29'):33475978,
          ('GEG','2024-12-31'):26595541,('HUBS','2022-06-30'):13710448147,
          ('HUBS','2023-06-30'):25412807293,('HUBS','2024-06-30'):29007475839,
          ('SSTI','2022-06-30'):246884476}


def main():
    data=pd.read_csv(HERE/'output/xbrl_gaps_annual.csv',dtype={'cik':str})
    index=pd.read_csv(BASE/'sec/filings_index.csv')
    reviews=[]
    data['original_api_value']=data.value
    data['override_status']='no_override'
    data['source_url']=''
    data['available_date_conservative']=(pd.to_datetime(data.filed)+pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    for row in data[data.validation.str.startswith('check')].itertuples():
        docs=index[(index.accession==row.accession)&index.document_role.eq('primary')]
        file=docs.iloc[0] if len(docs) else None
        raw=(ROOT/file.local_path).read_text(encoding='utf-8',errors='replace') if file is not None else ''
        match=re.search(r'<ix:nonfraction\b[^>]*name=["\']dei:EntityPublicFloat["\'][^>]*>.*?</ix:nonfraction\s*>',raw,re.I|re.S)
        url=f"https://www.sec.gov/Archives/edgar/data/{int(row.cik)}/{row.accession.replace('-','')}/{file.primary_document}" if file is not None else ''
        status='unresolved_heuristic_alert_do_not_rescale'
        corrected=None
        excerpt=''
        if match:
            visible=html.unescape(re.sub(r'<[^>]+>',' ',match.group()))
            excerpt=' '.join(html.unescape(re.sub(r'<[^>]+>',' ',raw[max(0,match.start()-1700):match.end()+1100])).split())
            expected=REVIEWED.get((row.ticker,row.period_end))
            if expected is not None:
                displayed=float(visible.strip().replace(',',''))
                if displayed!=expected or row.value!=expected*1000 or not re.search(r'scale=["\']3["\']',match.group()):
                    raise ValueError(f'Reviewed source has changed: {row.ticker} {row.period_end}')
                corrected=expected
                status='reviewed_cover_page_dollars_override_inconsistent_XBRL_scale'
                data.loc[row.Index,'value']=expected
                data.loc[row.Index,'validation']='reviewed: explicit cover-page dollar amount; raw XBRL was 1000x this value'
                data.loc[row.Index,'override_status']=status
        data.loc[row.Index,'source_url']=url
        reviews.append({'ticker':row.ticker,'period_end':row.period_end,'original_api_value':row.value,
                        'reviewed_value':corrected,'status':status,'filed':row.filed,'accession':row.accession,
                        'source_url':url,'local_path':file.local_path if file is not None else '',
                        'source_sha256':hashlib.sha256((ROOT/file.local_path).read_bytes()).hexdigest() if file is not None else '',
                        'visible_cover_excerpt':excerpt})
    OUT.mkdir(exist_ok=True)
    pd.DataFrame(reviews).to_csv(OUT/'public_float_review.csv',index=False)
    data.to_csv(OUT/'xbrl_gaps_annual_reviewed.csv',index=False)
    print(f'Reviewed {len(REVIEWED)} source-confirmed overrides; {len(reviews)-len(REVIEWED)} alerts remain unresolved. Raw extract preserved.')


if __name__=='__main__':
    main()
