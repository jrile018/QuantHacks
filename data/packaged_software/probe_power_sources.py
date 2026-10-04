"""Inspect public source entry points; no credentials or private endpoints."""
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin

out = Path(__file__).parent / 'extracts/power_capex/public_source_probe'
out.mkdir(parents=True, exist_ok=True)
for label, url in [('ferc', 'https://elibrary.ferc.gov/eLibrary/search'), ('pjm', 'https://www.pjm.com/markets-and-operations/rpm')]:
    r = requests.get(url, timeout=30)
    print(label, r.status_code, len(r.content))
    r.raise_for_status()
    (out / (label + '.html')).write_bytes(r.content)
    soup = BeautifulSoup(r.content, 'html.parser')
    if label == 'ferc':
        payload = dict(searchText='"Microsoft Corporation" AND ("data center" OR "large load" OR "power purchase")', searchFullText=True, searchDescription=False,
                       dateSearches=[dict(dateType='filed_date', startDate='2022/1/1', endDate='2026/10/4')],
                       categories=['Issuance', 'Submittal'], libraries=[], documentClass=[],
                       classTypes=[], availability=[], affiliations=[], docketSearches=[],
                       resultsPerPage=10, curPage=0, sortBy='', groupBy='NONE', allDates=False,
                       accessionNumber=None, eFiling=False, opinion=None, fedRegisterCite=None,
                       fedCourtCaseNumber=None, fercCite=None, parentAccessionNumber=None,
                       orderNumber=None, idolResultID='')
        payload['availability'] = None
        response = requests.post('https://elibrary.ferc.gov/eLibraryWebAPI/api/Search/AdvancedSearch', json=payload, timeout=45)
        (out / 'ferc_test_search.json').write_bytes(response.content)
        print('FERC search', response.status_code, response.json().get('success'), response.json().get('totalHits'))
        for hit in (response.json().get('searchHits') or [])[:5]:
            print(hit['acesssionNumber'], hit['description'])
        for filename in ['assets/config/app-settings.json', 'common.b405745e8b8a8caa.js', '913.08541ea2d5b7f8f5.js']:
            response = requests.get(urljoin(url, filename), timeout=30)
            response.raise_for_status()
            (out / filename.rsplit('/', 1)[-1]).write_bytes(response.content)
            if filename.endswith('.json'):
                print('public apiUrl', response.json().get('apiUrl'))
        for s in soup.find_all('script', src=True):
            link = urljoin(url, s['src'])
            if 'main' in link or 'runtime' in link:
                j = requests.get(link, timeout=30)
                (out / link.rsplit('/', 1)[-1]).write_bytes(j.content)
                print(link, j.status_code, len(j.content))
    else:
        for a in soup.find_all('a', href=True):
            if 'base-residual-auction-report' in a['href'].lower() or 'bra-report' in a['href'].lower():
                print(urljoin(url, a['href']))
