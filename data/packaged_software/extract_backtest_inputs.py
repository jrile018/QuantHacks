"""Real dividend cashflows and historical options entitlement checks; no secret output."""
import json
import urllib.parse
import urllib.error
from pathlib import Path
import pandas as pd
from extract_company_news import NewsClient

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/packaged_software/extracts/backtest_inputs'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    client=NewsClient(ROOT/'data/packaged_software/extracts/_cache/backtest_inputs')
    companies=pd.read_csv(ROOT/'data/packaged_software/packaged_software_companies.csv')
    bars=pd.read_csv(ROOT/'data/packaged_software/extracts/prices/daily_bars.csv')
    end=bars.date.max()
    query={'ex_dividend_date.gte':'2022-01-01','ex_dividend_date.lte':end,'limit':5000,'sort':'ex_dividend_date.asc'}
    url='https://api.massive.com/stocks/v1/dividends?'+urllib.parse.urlencode(query)
    rows=[];pages=0;seen=set()
    while url:
        if url in seen:raise ValueError('Repeated pagination URL')
        seen.add(url);data=client.page(url);pages+=1
        rows.extend(x for x in data.get('results',[]) if x.get('ticker') in set(companies.ticker))
        url=data.get('next_url')
        print('Dividend page',pages,'universe distributions',len(rows),flush=True)
    columns=['id','ticker','ex_dividend_date','pay_date','declaration_date','currency','cash_amount','split_adjusted_cash_amount','distribution_type']
    frame=pd.DataFrame(rows).reindex(columns=columns).drop_duplicates('id')
    frame.to_csv(OUT/'dividends.csv',index=False)
    capability={'stored_historical_option_quotes_before_probe':False,'historical_contract_access':False,
                'historical_quote_access':False,'historical_aggregate_access':False,'probe_date':'2022-01-03',
                'note':'Capabilities do not constitute a complete options backtest dataset.'}
    try:
        spot=float(bars[(bars.ticker=='MSFT') & (bars.date=='2022-01-03')].iloc[0].close)
        params={'underlying_ticker':'MSFT','expired':'true','as_of':'2022-01-03','contract_type':'call',
                'expiration_date.gte':'2022-02-01','expiration_date.lte':'2022-03-04',
                'strike_price.gte':round(spot*.98,2),'strike_price.lte':round(spot*1.02,2),'limit':1}
        data=client.page('https://api.massive.com/v3/reference/options/contracts?'+urllib.parse.urlencode(params))
        contracts=data.get('results',[])
        capability['historical_contract_access']=bool(contracts)
        if contracts:
            ticker=contracts[0]['ticker'];capability['probe_contract']=ticker
            try:
                q={'timestamp.gte':'2022-01-03T14:30:00Z','timestamp.lte':'2022-01-03T21:00:00Z','limit':1,'order':'desc','sort':'timestamp'}
                quotes=client.page('https://api.massive.com/v3/quotes/'+urllib.parse.quote(ticker)+'?'+urllib.parse.urlencode(q))
                capability['historical_quote_access']=bool(quotes.get('results'))
            except urllib.error.HTTPError as e:capability['quotes_http_status']=e.code
            try:
                aggs=client.page('https://api.massive.com/v2/aggs/ticker/'+urllib.parse.quote(ticker)+'/range/1/day/2022-01-03/2022-01-07?adjusted=true')
                capability['historical_aggregate_access']=bool(aggs.get('results'))
            except urllib.error.HTTPError as e:capability['aggregates_http_status']=e.code
    except urllib.error.HTTPError as e:capability['contracts_http_status']=e.code
    (OUT/'options_capability.json').write_text(json.dumps(capability,indent=2),encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps({'end':end,'dividend_rows':len(frame),'pages':pages,
        'source':'https://api.massive.com/stocks/v1/dividends','dividend_accounting':'signed shares held before ex-date times split_adjusted_cash_amount; ex-date economic accrual',
        'symbols':'current symbols; historical rename gaps not silently stitched','options':capability},indent=2),encoding='utf-8')
    print(json.dumps(capability,indent=2))


if __name__=='__main__':main()
