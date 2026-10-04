#!/usr/bin/env python3
"""Reconstruct point-in-time S&P 500 membership from Wikipedia's revision
history, including names that were later REMOVED from the index.

    tools/sp500_membership_history.py --out data/reference/sp500_membership.csv

WHY THIS EXISTS
---------------
ADR 7.1 records, correctly and by direct fetch, that the article no longer
carries a "selected changes" table - so the current snapshot answers "was
X a member on date D" only for names still in the index today. Everything
removed since 2010 is missing, which flatters every backtest built on it:
the names that were dropped are disproportionately the ones that did
badly.

ADR-016 assigned that gap to a paid point-in-time source. That conclusion
was right about the changes table and wrong about the alternative. The
article's REVISION HISTORY is free, goes back well before 2010, and each
revision contains the full constituent table as it stood that day.
Sampling it monthly reconstructs membership directly - no vendor, no
licence.

WHAT IT DOES NOT FIX
--------------------
Membership is only half of survivorship. The other half is PRICES for
delisted names, which this does not touch: a name that was acquired in
2014 still needs a price series, and whether the price source has one is
a separate question this tool deliberately does not answer. What it does
give is the honest denominator - which names should have been in the
universe - so the size of the remaining gap is a measured number instead
of an unknown.

ON SAMPLING MONTHLY
-------------------
Index changes are announced days in advance and take effect on a known
date, so monthly sampling can misdate a change by up to a month. That is
a real limitation and much smaller than the one it replaces: being wrong
about a join date by three weeks is not comparable to a name being absent
from sixteen years of history. The membership file records the DATE OF
THE REVISION each observation came from, so the uncertainty is visible
rather than implied.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request

API = 'https://en.wikipedia.org/w/api.php'
TITLE = 'List of S&P 500 companies'
UA = 'geomarket-research/0.1 (+point-in-time membership reconstruction)'

# A plausible exchange ticker: 1-5 uppercase letters, optionally with a
# dot or dash share-class suffix. Deliberately strict - loose matching
# picks up state abbreviations, GICS words and reference markers out of
# the surrounding cells.
TICKER = re.compile(r'^[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?$')


_last_call = [0.0]


def api_get(params, attempts=5):
    """One API call, rate-limited and backed off.

    Wikipedia returns 429 readily and is entitled to: this walks ~200
    revisions of a large article for our convenience, not theirs. One
    request per second with exponential backoff on 429 is well inside
    their guidance, and the whole run still finishes in a few minutes.
    The first version of this had no delay between the revision lookups
    at all and was rate-limited within twelve calls, which was the
    correct response from their end.
    """
    params = dict(params)
    params['format'] = 'json'
    url = API + '?' + urllib.parse.urlencode(params)
    for attempt in range(attempts):
        gap = time.time() - _last_call[0]
        if gap < 1.0:
            time.sleep(1.0 - gap)
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                _last_call[0] = time.time()
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            _last_call[0] = time.time()
            if e.code != 429 or attempt == attempts - 1:
                raise
            wait = 5.0 * (2 ** attempt)
            sys.stderr.write('  rate limited, waiting %.0fs' % wait + chr(10))
            time.sleep(wait)
    raise RuntimeError('unreachable')


def revision_at(when):
    """The newest revision at or before `when` (an ISO instant)."""
    doc = api_get({
        'action': 'query', 'prop': 'revisions', 'titles': TITLE,
        'rvlimit': 1, 'rvstart': when, 'rvdir': 'older', 'rvprop': 'ids|timestamp',
    })
    for _, page in doc['query']['pages'].items():
        revs = page.get('revisions') or []
        if revs:
            return revs[0]['revid'], revs[0]['timestamp']
    return None, None


def tickers_in_revision(revid, cache_dir):
    """Every ticker in the constituent table of one revision.

    Parses the RENDERED html rather than the wikitext. The wikitext markup
    of this table has changed repeatedly over sixteen years - templates,
    column order, link styles - while the rendered table has stayed a
    table, so rendering is what makes one parser work across the range.
    """
    path = os.path.join(cache_dir, 'rev_%d.html' % revid)
    if os.path.exists(path):
        html = open(path, encoding='utf-8').read()
    else:
        doc = api_get({'action': 'parse', 'oldid': revid, 'prop': 'text'})
        html = doc['parse']['text']['*']
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)

    # The first wikitable is the constituent list in every revision
    # sampled; later tables, when present, are changes or sector counts.
    #
    # Matched on the <table> TAG rather than on the bare word "wikitable",
    # which also appears dozens of times inside the page's inlined CSS. The
    # first version searched for the word, landed in a <style> block, and
    # extracted a slice containing no rows at all - which showed up as
    # three revisions parsing zero tickers and being skipped. A skip is
    # safe; being wrong about which region is the table is not, and the
    # difference was invisible until the counts were looked at.
    table = None
    for match in re.finditer(r'<table[^>]*>', html):
        if 'wikitable' in match.group(0):
            end = html.find('</table>', match.end())
            if end > 0:
                table = html[match.end():end]
            break
    if table is None:
        return set()

    found = set()
    for row in re.findall(r'<tr.*?</tr>', table, flags=re.S):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, flags=re.S)
        for cell in cells[:2]:  # the ticker is the first or second column
            text = re.sub(r'<[^>]+>', '', cell)
            text = re.sub(r'&[a-z]+;', ' ', text).strip()
            if TICKER.match(text):
                found.add(text)
                break
    return found


def month_starts(first_year, last_year):
    out = []
    for year in range(first_year, last_year + 1):
        for month in range(1, 13):
            out.append('%04d-%02d-01T00:00:00Z' % (year, month))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='data/reference/sp500_membership.csv')
    ap.add_argument('--from-year', type=int, default=2009)
    ap.add_argument('--to-year', type=int, default=2026)
    ap.add_argument('--cache', default='data/raw/wikipedia_revisions')
    ap.add_argument('--min-tickers', type=int, default=400,
                    help='a revision yielding fewer than this is reported and SKIPPED rather '
                         'than used - a parse that half-worked is worse than one that failed')
    args = ap.parse_args()

    observations = []   # (revision_date, ticker)
    suspect = []
    seen_revids = set()

    for when in month_starts(args.from_year, args.to_year):
        if when > time.strftime('%Y-%m-%dT%H:%M:%SZ'):
            break
        revid, ts = revision_at(when)
        if revid is None or revid in seen_revids:
            continue
        seen_revids.add(revid)
        tickers = tickers_in_revision(revid, args.cache)
        if len(tickers) < args.min_tickers:
            # Never silently accept a short list: it would look exactly
            # like a month when the index shrank, and would delete real
            # members from the reconstruction.
            suspect.append((ts[:10], revid, len(tickers)))
            sys.stderr.write('  SKIP %s rev %d: only %d tickers parsed\n'
                             % (ts[:10], revid, len(tickers)))
            continue
        for t in sorted(tickers):
            observations.append((ts[:10], t))
        sys.stderr.write('  %s rev %-10d %d tickers\n' % (ts[:10], revid, len(tickers)))

    if not observations:
        sys.exit('no usable revisions parsed - refusing to write an empty membership file')

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('observed_date,ticker\n')
        for date, ticker in observations:
            f.write('%s,%s\n' % (date, ticker))

    dates = sorted({d for d, _ in observations})
    all_tickers = sorted({t for _, t in observations})
    latest = {t for d, t in observations if d == dates[-1]}
    ever_not_now = sorted(set(all_tickers) - latest)

    print()
    print('revisions used     : %d  (%s .. %s)' % (len(dates), dates[0], dates[-1]))
    print('revisions skipped  : %d' % len(suspect))
    print('tickers ever seen  : %d' % len(all_tickers))
    print('tickers in the last: %d' % len(latest))
    print('EVER a member but not in the latest snapshot: %d' % len(ever_not_now))
    print()
    print('That last number is the survivorship gap, measured rather than assumed:')
    print('names a point-in-time universe should contain and a current-constituents')
    print('snapshot does not. Sample: %s' % ', '.join(ever_not_now[:15]))
    print()
    print('wrote %s (%d observations)' % (args.out, len(observations)))


if __name__ == '__main__':
    main()
