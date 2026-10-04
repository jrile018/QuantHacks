"""17_massive_probe.py - what does our Massive key unlock for options? Reads the key from MASSIVE_API_KEY."""
import os, sys
import requests

K = os.environ.get('MASSIVE_API_KEY')
if not K:
    sys.exit('Set the key first in PowerShell:  $env:MASSIVE_API_KEY="your_key_here"   then run again')
B = 'https://api.massive.com'
UNDER = sys.argv[1] if len(sys.argv) > 1 else 'MRNA'

def g(path, **p):
    r = requests.get(B + path, params={**p, 'apiKey': K}, timeout=30)
    try:
        j = r.json()
    except Exception:
        j = {'raw': r.text[:150]}
    return r.status_code, j

def show(name, s, j):
    rows = j.get('results')
    n = len(rows) if isinstance(rows, list) else ('object' if rows else 0)
    print(f'{name:28s} http {s}  status={j.get("status", "")}  msg={j.get("message") or j.get("error") or ""}  rows={n}')
    return rows

# 1) recent EXPIRED contracts (expired in 2026) so history exists
s, j = g('/v3/reference/options/contracts', underlying_ticker=UNDER, expired='true',
         **{'expiration_date.gte': '2026-03-01', 'expiration_date.lte': '2026-08-31'}, limit=200, order='asc', sort='strike_price')
cons = j.get('results', [])
print(f'expired contracts for {UNDER}:', s, len(cons))
found = None
for c in cons[::max(1, len(cons) // 25)]:           # sample up to ~25 contracts across strikes
    t, exp = c['ticker'], c['expiration_date']
    s, b = g(f'/v2/aggs/ticker/{t}/range/1/day/2026-01-01/{exp}')
    if s == 200 and b.get('results'):
        found = (t, exp, b['results']); break
if not found:
    sys.exit('no expired contract with daily bars found; try another underlying: python 17_massive_probe.py GILD')
t, exp, bars = found
day = __import__('datetime').datetime.utcfromtimestamp(bars[-1]['t'] / 1000).strftime('%Y-%m-%d')
print('\nusing expired contract', t, 'expiry', exp, 'bars', len(bars), 'last bar day', day)
show('daily bars', 200, {'results': bars, 'status': 'OK'})
s, j = g(f'/v3/quotes/{t}', timestamp=day, limit=5);  q = show('quotes (bid/ask) on that day', s, j)
if q: print('   sample quote:', {k: q[0].get(k) for k in ('bid_price', 'ask_price', 'bid_size', 'ask_size', 'sip_timestamp')})
s, j = g(f'/v3/trades/{t}', timestamp=day, limit=5);  tr = show('trades on that day', s, j)

# 2) a LIVE contract for snapshot (iv, greeks, open interest)
s, j = g('/v3/reference/options/contracts', underlying_ticker=UNDER, expired='false', limit=1)
live = j.get('results', [])
if live:
    lt = live[0]['ticker']
    s, j = g(f'/v3/snapshot/options/{UNDER}/{lt}')
    r = show('snapshot (live contract)', s, j)
    if isinstance(r, dict): print('   snapshot keys:', sorted(r.keys()))
else:
    print('no live contracts found for', UNDER)
