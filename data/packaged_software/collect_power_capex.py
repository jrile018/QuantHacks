"""Public SEC capex/lease, FERC search and PJM capacity observations.

Daily replay availability is publication + one day, not an intraday receipt clock.
All underlying source bytes and queries are cached; candidates are never amounts.
Run --stage sec, filings, power or all. No changes to original SEC caches.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / 'extracts/power_capex'
SEC = HERE / 'extracts/sec'
sys.path.insert(0, str(HERE))
from sec_common import filing_documents

FORMS = {'10-K', '10-Q', '10-K/A', '10-Q/A', '20-F', '40-F', '6-K'}
VERSION = 'public-power-capex-v1'


def read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(path, rows, fields=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fields = fields or sorted({k for row in rows for k in row})
    with Path(path).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def next_day(day):
    return (dt.date.fromisoformat(day[:10]) + dt.timedelta(days=1)).isoformat()


def day_count(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def observation(cik, feature, value, end, available, refs, **extra):
    row = dict(cik=cik, feature=feature, value=value, period_end=end,
               available_date=available, evidence_ref=refs, unit='USD',
               quality_status='reported_standard_tag', scope='consolidated_issuer',
               period_start='', source_url='', source_sha256='', local_path='', **extra)
    row['observation_id'] = sha(json.dumps(row, sort_keys=True).encode())[:24]
    return row


def raw_facts(data, tags, asof):
    result = []
    for tag in tags:
        for f in data.get('facts', {}).get('us-gaap', {}).get(tag, {}).get('units', {}).get('USD', []):
            if f.get('form') in FORMS and f.get('filed') and f['filed'] <= asof and f.get('accn') and f.get('end'):
                result.append(dict(f, tag=tag))
    return result


def make_instant(c, feature, facts, digest, path):
    result = []
    # Do not aggregate different filings, durations or units.
    grouped = defaultdict(list)
    for f in facts:
        if not f.get('start'):
            grouped[(f['end'], f['filed'], f['accn'])].append(f)
    for (end, filed, accn), group in grouped.items():
        if end < '2020-01-01' or end > filed:
            continue
        totals = {float(f['val']) for f in group if not f['tag'].endswith(('Current', 'Noncurrent'))}
        current = {float(f['val']) for f in group if f['tag'].endswith('Current')}
        noncurrent = {float(f['val']) for f in group if f['tag'].endswith('Noncurrent')}
        if len(totals) > 1 or len(current) > 1 or len(noncurrent) > 1:
            continue
        components = next(iter(current)) + next(iter(noncurrent)) if len(current) == len(noncurrent) == 1 else None
        value = next(iter(totals)) if totals else components
        if value is None or value < 0:
            continue
        if totals and components is not None and abs(value-components) > max(1, .000001*abs(value)):
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(c['cik'])}/{accn.replace('-', '')}/{accn}-index.html"
        row = observation(c['cik'], feature, value, end, next_day(filed),
                          ';'.join(sorted({f['tag'] for f in group})) + ':' + accn)
        row.update(source_url=url, source_sha256=digest, local_path=str(path.relative_to(HERE)),
                   quality_status='reported_total_or_same_accession_current_plus_noncurrent')
        result.append(row)
    return result


def pick(rows, cutoff, max_age=400):
    eligible = [r for r in rows if r['available_date'] <= cutoff and 0 <= day_count(r['period_end'], cutoff) <= max_age]
    if not eligible:
        return None
    key = max((r['period_end'], r['available_date']) for r in eligible)
    matches = [r for r in eligible if (r['period_end'], r['available_date']) == key]
    if len({float(r['value']) for r in matches}) > 1:
        return None
    return sorted(matches, key=lambda r:r['evidence_ref'])[0]


def changes(rows, feature, lag, tolerance, suffix):
    result = []
    for current in rows:
        prior = pick([r for r in rows if abs(day_count(r['period_end'], current['period_end'])-lag) <= tolerance], current['available_date'], max_age=800)
        if not prior:
            continue
        for name, value, unit in [(feature + '_delta_' + suffix + '_usd', float(current['value'])-float(prior['value']), 'USD'),
                                   (feature + '_growth_' + suffix, float(current['value'])/float(prior['value'])-1 if float(prior['value']) > 0 else None, 'fraction')]:
            if value is None:
                continue
            row = observation(current['cik'], name, value, current['period_end'], current['available_date'],
                              current['observation_id'] + ';' + prior['observation_id'])
            row.update(unit=unit, quality_status='derived_comparable_period_change_not_new_lease_additions',
                       source_url=current['source_url'], source_sha256=current['source_sha256'], local_path=current['local_path'])
            result.append(row)
    return result


def sec_observations(companies, asof):
    observations, coverage, sources, exclusions = [], [], [], []
    instant_tags = {
        'operating_lease_liability_usd': ['OperatingLeaseLiability', 'OperatingLeaseLiabilityCurrent', 'OperatingLeaseLiabilityNoncurrent'],
        'finance_lease_liability_usd': ['FinanceLeaseLiability', 'FinanceLeaseLiabilityCurrent', 'FinanceLeaseLiabilityNoncurrent'],
        'operating_lease_rou_asset_usd': ['OperatingLeaseRightOfUseAsset'],
        'finance_lease_rou_asset_usd': ['FinanceLeaseRightOfUseAsset'],
        'operating_lease_undiscounted_payments_usd': ['OperatingLeaseLiabilityPaymentsDue'],
        'finance_lease_undiscounted_payments_usd': ['FinanceLeaseLiabilityPaymentsDue'],
    }
    for c in companies:
        path = SEC / c['ticker'] / 'companyfacts.json'
        body = path.read_bytes()
        digest = sha(body)
        data = json.loads(body)
        if str(data['cik']).zfill(10) != c['cik']:
            raise ValueError('Companyfacts issuer mismatch: ' + c['ticker'])
        sources.append(dict(cik=c['cik'], ticker=c['ticker'], source_sha256=digest, local_path=str(path.relative_to(HERE)),
                            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c['cik']}.json"))
        for feature, tags in instant_tags.items():
            selected=raw_facts(data,tags,asof)
            for f in selected:
                if f['end']>f['filed']:
                    exclusions.append(dict(cik=c['cik'],ticker=c['ticker'],feature=feature,tag=f['tag'],value=f['val'],
                                           period_end=f['end'],filed_date=f['filed'],accession=f['accn'],
                                           reason='source_instant_period_after_filing_date_unresolved'))
            rows = make_instant(c, feature, selected, digest, path)
            observations.extend(rows)
            coverage.append(dict(cik=c['cik'], ticker=c['ticker'], feature=feature, observations=len(rows), status='observed' if rows else 'not_reported_under_selected_standard_USD_tags'))
            if 'liability_usd' in feature:
                stem = feature.removesuffix('_usd')
                observations.extend(changes(rows, stem, 91, 16, 'qoq'))
                observations.extend(changes(rows, stem, 365, 16, 'yoy'))
        # Noncash additions are distinct from liabilities and cash capex. Preserve annual/quarter durations.
        for stem, tag in [('operating', 'RightOfUseAssetObtainedInExchangeForOperatingLeaseLiability'),
                          ('finance', 'RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability')]:
            for f in raw_facts(data, [tag], asof):
                if not f.get('start'):
                    continue
                days = day_count(f['start'], f['end'])
                bucket = 'quarter' if 80 <= days <= 100 else 'annual' if 350 <= days <= 380 else None
                if not bucket or f['end'] < '2021-01-01':
                    continue
                row = observation(c['cik'], stem+'_lease_noncash_additions_'+bucket+'_usd', f['val'], f['end'], next_day(f['filed']), tag+':'+f['accn'])
                row.update(period_start=f['start'], source_sha256=digest, local_path=str(path.relative_to(HERE)),
                           source_url=f"https://www.sec.gov/Archives/edgar/data/{int(c['cik'])}/{f['accn'].replace('-', '')}/{f['accn']}-index.html")
                observations.append(row)
    # Source/arithmetic/date checked capex from the existing conservative layer.
    metrics = read(HERE / 'extracts/financial_quality/metric_validation.csv')
    for r in metrics:
        if r['eligible_for_conservative_layer'].lower() != 'true' or r['metric'] not in {'physical_asset_purchases', 'ppe_net', 'ppe_gross'}:
            continue
        feature = 'capex_cash_' + r['basis'] + '_usd' if r['metric'] == 'physical_asset_purchases' else r['metric']+'_usd'
        row = observation(r['cik'], feature, float(r['value']), r['period_end'], r['available_date_conservative'], r['source_fact_ids'])
        row.update(period_start=r['validated_period_start'], quality_status=r['review_reason'],
                   local_path='extracts/financial_quality/metric_validation.csv')
        observations.append(row)
    # Ratios retain the layer's aligned dependency dates.
    for r in read(HERE / 'extracts/financial_quality/ratio_dependency_validation.csv'):
        if r['eligible_for_conservative_layer'].lower() == 'true' and r['metric'] == 'physical_capex_pct_rev':
            row = observation(r['cik'], 'capex_cash_ttm_to_revenue', float(r['value']), r['period_end'], r['available_date_conservative'], r['dependencies'])
            row.update(unit='fraction', quality_status=r['status'], local_path='extracts/financial_quality/ratio_dependency_validation.csv')
            observations.append(row)
    groups = defaultdict(list)
    for r in observations:
        if r['feature'] in {'capex_cash_quarter_usd','capex_cash_ttm_usd','ppe_net_usd'}:
            groups[(r['cik'], r['feature'])].append(r)
    for (_, feature), rows in groups.items():
        observations.extend(changes(rows, feature.removesuffix('_usd'), 365, 16, 'yoy'))
    write(OUT / 'sec_observations.csv', observations)
    write(OUT / 'sec_coverage.csv', coverage)
    write(OUT / 'sec_source_manifest.csv', sources)
    write(OUT / 'sec_fact_exclusions.csv', exclusions)
    print('SEC observations', len(observations), 'companies', len(companies), flush=True)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden, self.stack = [], 0, []

    def handle_starttag(self, tag, attrs):
        hide = tag in {'script','style','ix:hidden','ix:header'}
        if tag not in {'br','hr','img','input','meta','link','wbr','source'}:
            self.stack.append((tag, hide))
        self.hidden += int(hide)
        if tag in {'p','div','tr','br'} and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                self.hidden -= sum(int(h) for _, h in self.stack[i:])
                del self.stack[i:]
                break

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


CAPEX = re.compile(r'\b(?:capital expenditures?|capex|additions to property(?:,? plant)?(?: and equipment)?)\b', re.I)
FORWARD = re.compile(r'\b(?:expect(?:ed|s)?|anticipat\w*|plan(?:ned|s)?|guidance|forecast\w*|intend\w*)\b', re.I)
DATA_CENTER = re.compile(r'\b(?:data ?centers?|datacenters?|server infrastructure|AI infrastructure)\b', re.I)
PPA = re.compile(r'\b(?:power purchase agreements?|electricity supply agreements?)\b', re.I)
MONEY = re.compile(r'\$\s*\d[\d,.]*(?:\s*(?:million|billion|thousand))?', re.I)


def filing_scan(task):
    c, filed, form, path = task
    body = Path(path).read_bytes()
    parser = VisibleText()
    parser.feed(body.decode('utf-8', errors='replace'))
    text = re.sub(r'\s+', ' ', ''.join(parser.parts))
    # Decimal periods are not sentence boundaries.
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    candidates, counts = [], dict(capex_guidance_candidate_sentences=0,
                                  datacenter_capex_candidate_sentences=0, ppa_disclosure_candidate_sentences=0)
    for sentence in sentences:
        if len(sentence) > 2500:
            # Tables/long paragraphs are evidence candidates, not reliable sentences.
            pieces = [sentence[max(0,m.start()-220):m.start()+650] for m in CAPEX.finditer(sentence)]
            pieces += [sentence[max(0,m.start()-220):m.start()+650] for m in PPA.finditer(sentence)]
        else:
            pieces = [sentence]
        for excerpt in pieces:
            types = []
            if CAPEX.search(excerpt) and FORWARD.search(excerpt):
                types.append('capex_guidance_candidate_sentences')
            if CAPEX.search(excerpt) and DATA_CENTER.search(excerpt):
                types.append('datacenter_capex_candidate_sentences')
            if PPA.search(excerpt):
                types.append('ppa_disclosure_candidate_sentences')
            for category in types:
                counts[category] += 1
                candidates.append(dict(cik=c['cik'], ticker=c['ticker'], filed_date=filed,
                                       available_date=next_day(filed), form=form, category=category,
                                       excerpt=excerpt, numeric_mentions_unvalidated=';'.join(MONEY.findall(excerpt)),
                                       local_path=path, source_sha256=sha(body),
                                       review_status='candidate_not_verified_guidance_or_contract'))
    accn = Path(path).parent.name.split('_',1)[-1]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(c['cik'])}/{accn.replace('-', '')}/{Path(path).name}"
    obs=[]
    for feature, count in counts.items():
        r=observation(c['cik'], feature, count, filed, next_day(filed), accn)
        r.update(unit='candidate_sentences', source_url=url, source_sha256=sha(body), local_path=path,
                 scope='latest_scanned_filing_not_complete_company_inventory', quality_status='text_candidate_count_not_numeric_guidance')
        obs.append(r)
    for r in candidates:
        r['source_url']=url
        r['evidence_id']=sha((r['cik']+filed+r['category']+r['excerpt']).encode())[:24]
    return obs, candidates


def scan_filings(companies, asof):
    tasks = [(c, filed, form, str(path.relative_to(HERE))) for c in companies
             for filed, form, path in filing_documents(SEC/c['ticker'], ['10-K','10-Q','10-K_A','10-Q_A','20-F','40-F'])
             if '2022-01-01' <= filed <= asof]
    # Paths are resolved against HERE inside workers; do not depend on cwd.
    tasks = [(c,f,form,str(HERE/p)) for c,f,form,p in tasks]
    observations,candidates=[],[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i, (o,c) in enumerate(pool.map(filing_scan,tasks,chunksize=8),1):
            observations.extend(o)
            candidates.extend(c)
            if i%250==0:
                print('filings scanned',i,'/',len(tasks),flush=True)
    write(OUT/'filing_observations.csv', observations)
    write(OUT/'filing_candidates.csv', candidates)
    print('filings',len(tasks),'candidates',len(candidates),flush=True)


def cached_get(url, name):
    path=OUT/'public_sources'/name
    path.parent.mkdir(parents=True,exist_ok=True)
    metadata=path.with_suffix(path.suffix+'.source.json')
    same_url=metadata.exists() and json.loads(metadata.read_text(encoding='utf-8'))['source_url']==url
    if not path.exists() or not same_url or (name.endswith('.pdf') and not path.read_bytes().lstrip().startswith(b'%PDF')):
        r=requests.get(url,timeout=45)
        r.raise_for_status()
        if name.endswith('.pdf') and not r.content.lstrip().startswith(b'%PDF'):
            raise ValueError('URL did not return PDF bytes')
        path.write_bytes(r.content)
        metadata.write_text(json.dumps(dict(source_url=url,source_sha256=sha(r.content),retrieved_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())),encoding='utf-8')
    return path.read_bytes(), path


def ferc_payload(query, asof, page=0):
    end=dt.date.fromisoformat(asof)
    return dict(searchText=query, searchFullText=True, searchDescription=False,
                dateSearches=[dict(dateType='filed_date',startDate='2022/1/1',endDate=f'{end.year}/{end.month}/{end.day}')],
                availability=None,affiliations=[],categories=['Issuance','Submittal'],libraries=[],
                accessionNumber=None,eFiling=False,opinion=None,fedRegisterCite=None,
                fedCourtCaseNumber=None,fercCite=None,parentAccessionNumber=None,
                docketSearches=[],resultsPerPage=100,curPage=page,classTypes=[],
                orderNumber=None,sortBy='',groupBy='NONE',idolResultID='',allDates=False)


def company_search_name(c):
    if c['ticker']=='MSFT':
        return 'Microsoft Corporation'
    if c['ticker']=='ORCL':
        return 'Oracle Corporation" OR "Oracle America'
    name=re.sub(r'\s+(?:Class [ABCD] )?(?:Common|Ordinary) (?:Stock|Shares).*$', '',c['name'],flags=re.I)
    name=re.sub(r'\bCorp\.?$', 'Corporation', name)
    return name.replace('"','').replace(',','').rstrip('.').strip()


def ferc_search(task):
    c,asof=task
    name=company_search_name(c)
    query='("'+name+'") AND ("data center" OR "large load" OR "power purchase" OR "interconnection")'
    endpoint='https://elibrary.ferc.gov/eLibraryWebAPI/api/Search/AdvancedSearch'
    hits=[]
    status='completed_candidate_search_not_direct_project_attribution'
    total=0
    for page in range(5):
        # FERC uses 0 for the initial request and one-based pagination afterward:
        # page 1 repeats the first page; the next distinct page is page 2.
        requested_page=0 if page==0 else page+1
        path=OUT/'ferc_search_cache_v3'/f"{c['cik']}_{asof}_{requested_page}.json"
        path.parent.mkdir(parents=True,exist_ok=True)
        try:
            if path.exists():
                data=json.loads(path.read_bytes())
            else:
                response=requests.post(endpoint,json=ferc_payload(query,asof,requested_page),timeout=45)
                response.raise_for_status()
                data=response.json()
                path.write_text(json.dumps(data),encoding='utf-8')
                time.sleep(.25)
            if not data.get('success'):
                raise ValueError(data.get('errorMessage','FERC search unsuccessful'))
            total=int(data['totalHits'])
            page_hits=data.get('searchHits') or []
            for hit in page_hits:
                hits.append(dict(cik=c['cik'],ticker=c['ticker'],query=query,
                                 accession=hit.get('acesssionNumber',''), description=hit.get('description',''),
                                 filed_date=hit.get('filedDate',''),posted_date=hit.get('postedDate',''),
                                 availability_code=hit.get('availCode',''),
                                 docket_numbers=';'.join(hit.get('docketNumbers') or []),
                                 source_url='https://elibrary.ferc.gov/eLibrary/filelist?accession_number='+hit.get('acesssionNumber',''),
                                 metadata_sha256=sha(path.read_bytes()),cache_path=str(path.relative_to(HERE)),
                                 attribution_status='search_match_requires_entity_and_project_review'))
            if len(hits)>=total or not page_hits:
                break
        except Exception as exc:
            status='search_failed:'+type(exc).__name__+':'+str(exc)[:140]
            break
    if total>len(hits) and not status.startswith('search_failed'):
        status='truncated_candidate_search_not_complete'
    return hits,dict(cik=c['cik'],ticker=c['ticker'],query=query,total_hits=total,retained_hits=len(hits),status=status,asof=asof)


PJM_ARTICLES=[
 ('2021-06-02','2022/2023','20210602-pjm-successfully-clears-capacity-auction-to-ensure-reliable-electricity-supplies'),
 ('2022-06-21','2023/2024','20220621-pjm-capacity-auction-secures-electricity-supplies-at-competitive-prices'),
 ('2023-02-27','2024/2025','20230227-pjm-capacity-auction-procures-adequate-resources'),
 ('2024-07-30','2025/2026','20240730-pjm-capacity-auction-procures-sufficient-resources-to-meet-rto-reliability-requirement'),
 ('2025-07-22','2026/2027','20250722-pjm-auction-procures-134311-mw-of-generation-resources-supply-responds-to-price-signal'),
 ('2025-12-17','2027/2028','20251217-pjm-auction-procures-134479-mw-of-generation-resources'),
 ('2026-07-14','2028/2029','20260714-pjm-capacity-auction-procures-138318-mw-of-generation-resources'),
]


def collect_pjm(asof):
    from pypdf import PdfReader
    import io
    rows,errors=[],[]
    for published,delivery,filename in PJM_ARTICLES:
        if published>asof:
            continue
        url=f'https://www.pjm.com/-/media/DotCom/about-pjm/newsroom/{published[:4]}-releases/{filename}.pdf'
        try:
            source_urls=[url,url.replace('.pdf','.ashx'),url.replace('/DotCom/','/'),url.replace('/DotCom/','/').replace('.pdf','.ashx')]
            source_urls.append('https://www.pjm.com/-/media/DotCom/markets-ops/rpm/rpm-auction-info/'+delivery.replace('/','-')+'/'+delivery.replace('/','-')+'-base-residual-auction-report.pdf')
            failure=None
            for source_url in source_urls:
                try:
                    body,path=cached_get(source_url,'pjm_'+delivery.replace('/','_')+'.pdf')
                    url=source_url
                    break
                except (ValueError,requests.HTTPError) as exc:
                    failure=exc
            else:
                raise failure
            pdf=PdfReader(io.BytesIO(body))
            text=' '.join(' '.join(page.extract_text().split()) for page in pdf.pages)
            (path.with_suffix('.txt')).write_text(text,encoding='utf-8')
            prices=re.findall(r'\$\s*([\d,.]+)\s*/\s*MW\s*[-–]\s*day',text,re.I)
            if not prices:
                raise ValueError('No explicit USD/MW-day price')
            decline=re.search(r'rest of RTO declined from\s*\$\s*[\d,.]+\s*/\s*MW[-–]day\s*to\s*\$\s*([\d,.]+)',text,re.I)
            selected_price=decline.group(1) if decline else prices[0]
            value=float(selected_price.replace(',',''))
            stamp=dt.date.fromisoformat(published)
            date_re='(?:'+stamp.strftime('%B')+'|'+stamp.strftime('%b')+r'\.?)\s*'+str(stamp.day)+r'\s*,\s*'+str(stamp.year)
            date_source_url=''
            date_source_sha256=''
            if not re.search(date_re,text):
                # The older PJM report lacks its original announcement date. FERC's
                # contemporaneous market report explicitly records the posting date.
                if delivery!='2024/2025':
                    raise ValueError('Auction publication date mismatch')
                date_source_url='https://www.ferc.gov/sites/default/files/2023-03/23_State-of-the-market_0323.pdf'
                date_body,date_path=cached_get(date_source_url,'ferc_2023_state_of_market.pdf')
                date_text=' '.join(' '.join(page.extract_text().split()) for page in PdfReader(io.BytesIO(date_body)).pages)
                if not re.search(r'P\s*JM posted the results on February 27, 2023',date_text):
                    raise ValueError('Missing corroborating original auction posting date')
                date_source_sha256=sha(date_body)
            clause=re.search(r'.{0,120}\$\s*'+re.escape(selected_price)+r'\s*/\s*MW[-–]day.{0,200}',text,re.I)
            shortfall=re.search(r'(?:fell|falling|fall|was|is|be)\s+(?:short\s+(?:of|by)\s+)?([\d,]+)\s*MW\s+short',text,re.I)
            if not shortfall:
                shortfall=re.search(r'is short of PJM.{0,35}?reliability requirement by\s*([\d,]+)\s*MW',text,re.I)
            rows.append(dict(region='PJM_RTO',delivery_year=delivery,published_date=published,
                             available_date=next_day(published),price_usd_mw_day=value,
                             source_url=url,source_sha256=sha(body),local_path=str(path.relative_to(HERE)),
                             source_clause=clause.group(0) if clause else '',
                             date_source_url=date_source_url,date_source_sha256=date_source_sha256,
                             price_cap_hit=1 if re.search(r'(?:price|FERC-approved) cap',text,re.I) else '',
                             shortfall_mw=float(shortfall.group(1).replace(',','')) if shortfall else '',
                             interpretation='regional_capacity_price_not_retail_energy_price_or_company_cost'))
        except Exception as exc:
            errors.append(dict(source_url=url,status=type(exc).__name__+':'+str(exc)))
    rows.sort(key=lambda r:r['published_date'])
    for i,r in enumerate(rows):
        r['price_change_vs_previous_auction']=r['price_usd_mw_day']/rows[i-1]['price_usd_mw_day']-1 if i else ''
    write(OUT/'pjm_auctions.csv',rows)
    write(OUT/'power_source_errors.csv',errors,['source_url','status'])
    print('PJM auctions',len(rows),'errors',len(errors),flush=True)


def power_observations(companies,asof,include_pjm=True):
    if include_pjm:
        collect_pjm(asof)
    hits,coverage=[],[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i,(h,c) in enumerate(pool.map(ferc_search,[(c,asof) for c in companies]),1):
            hits.extend(h)
            coverage.append(c)
            if i%10==0:
                print('FERC companies searched',i,'/',len(companies),flush=True)
    unique={ (r['cik'],r['accession']):r for r in hits }
    write(OUT/'ferc_search_candidates.csv',list(unique.values()),
          ['cik','ticker','query','accession','description','filed_date','posted_date','availability_code','docket_numbers','source_url','metadata_sha256','cache_path','attribution_status'])
    write(OUT/'ferc_search_coverage.csv',coverage)
    print('FERC candidates',len(unique),'search failures',sum(c['status'].startswith('search_failed') for c in coverage),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--stage',choices=['sec','filings','pjm','ferc','power','all'],default='all')
    p.add_argument('--asof',default=dt.date.today().isoformat())
    args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    companies=read(HERE/'packaged_software_companies.csv')
    if len(companies)!=168 or len({c['cik'] for c in companies})!=168:
        raise ValueError('Expected fixed 168-company universe')
    if args.stage in {'sec','all'}:
        sec_observations(companies,args.asof)
    if args.stage in {'filings','all'}:
        scan_filings(companies,args.asof)
    if args.stage in {'power','all'}:
        power_observations(companies,args.asof)
    if args.stage=='pjm':
        collect_pjm(args.asof)
    if args.stage=='ferc':
        power_observations(companies,args.asof,include_pjm=False)
    manifest=dict(version=VERSION,asof=args.asof,collected_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  companies=168,sha256={p.name:sha(p.read_bytes()) for p in OUT.glob('*.csv')})
    (OUT/'collection_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
