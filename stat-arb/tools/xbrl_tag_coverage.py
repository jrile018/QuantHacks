#!/usr/bin/env python3
"""Measure which XBRL tags real filers actually use for each concept.

The blocker on the valuation layer is that EBITDA and enterprise value are
not XBRL concepts - they have to be assembled from tags that different
issuers report under different names, and some issuers omit entirely. The
fallback chain has to be designed from what filers DO, not from what the
taxonomy says they may do, so this downloads companyfacts for a real
sample and counts.

Output is a coverage table per concept: how many issuers have each
candidate tag at all, and how many are left with nothing after the whole
chain. That last number is the honest answer to "can we compute this".
"""
import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error

UA = 'geomarket-research/0.1 (+tag coverage probe)'
CACHE = os.path.expanduser('~/projects/geomarket/data/raw/companyfacts_cache')

# Candidate tags per concept, best first. Ordering matters: the first that
# is present wins, so the most specific / most standard goes first.
CONCEPTS = {
    'net_income': [
        ('us-gaap', 'NetIncomeLoss', 'USD'),
        ('us-gaap', 'ProfitLoss', 'USD'),
    ],
    'operating_income': [
        ('us-gaap', 'OperatingIncomeLoss', 'USD'),
    ],
    'depreciation_amortisation': [
        ('us-gaap', 'DepreciationDepletionAndAmortization', 'USD'),
        ('us-gaap', 'DepreciationAmortizationAndAccretionNet', 'USD'),
        ('us-gaap', 'DepreciationAndAmortization', 'USD'),
        ('us-gaap', 'Depreciation', 'USD'),
        ('us-gaap', 'AmortizationOfIntangibleAssets', 'USD'),
    ],
    'operating_cash_flow': [
        ('us-gaap', 'NetCashProvidedByUsedInOperatingActivities', 'USD'),
        ('us-gaap',
         'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations', 'USD'),
    ],
    'capex': [
        ('us-gaap', 'PaymentsToAcquirePropertyPlantAndEquipment', 'USD'),
        ('us-gaap', 'PaymentsToAcquireProductiveAssets', 'USD'),
        ('us-gaap', 'PaymentsForCapitalImprovements', 'USD'),
    ],
    'long_term_debt': [
        ('us-gaap', 'LongTermDebtNoncurrent', 'USD'),
        ('us-gaap', 'LongTermDebt', 'USD'),
        ('us-gaap', 'LongTermDebtAndCapitalLeaseObligations', 'USD'),
    ],
    'short_term_debt': [
        ('us-gaap', 'LongTermDebtCurrent', 'USD'),
        ('us-gaap', 'DebtCurrent', 'USD'),
        ('us-gaap', 'ShortTermBorrowings', 'USD'),
        ('us-gaap', 'OtherShortTermBorrowings', 'USD'),
    ],
    'cash': [
        ('us-gaap', 'CashAndCashEquivalentsAtCarryingValue', 'USD'),
        ('us-gaap',
         'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents', 'USD'),
    ],
    'short_term_investments': [
        ('us-gaap', 'ShortTermInvestments', 'USD'),
        ('us-gaap', 'MarketableSecuritiesCurrent', 'USD'),
        ('us-gaap', 'AvailableForSaleSecuritiesDebtSecuritiesCurrent', 'USD'),
        ('us-gaap', 'OtherShortTermInvestments', 'USD'),
    ],
    'shares': [
        ('us-gaap', 'CommonStockSharesOutstanding', 'shares'),
        ('dei', 'EntityCommonStockSharesOutstanding', 'shares'),
        ('us-gaap', 'WeightedAverageNumberOfDilutedSharesOutstanding', 'shares'),
        ('us-gaap', 'WeightedAverageNumberOfSharesOutstandingBasic', 'shares'),
    ],
}


def fetch(cik):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, 'CIK%010d.json' % cik)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    url = 'https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json' % cik
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return None if e.code == 404 else None
    except Exception:
        return None
    with open(path, 'w') as f:
        f.write(body)
    time.sleep(0.15)  # SEC asks for <= 10 requests/second; stay well under
    return json.loads(body)


def has_tag(doc, taxonomy, tag, unit):
    try:
        entries = doc['facts'][taxonomy][tag]['units'][unit]
    except (KeyError, TypeError):
        return 0
    return len(entries)


if __name__ == '__main__':
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rows = []
    with open(os.path.expanduser(
            '~/projects/geomarket/data/reference/sp500_constituents.csv')) as f:
        for row in csv.DictReader(f):
            rows.append((row['symbol'], int(row['cik'])))

    # A spread across the alphabet rather than the first N, so the sample is
    # not accidentally one sector.
    step = max(1, len(rows) // limit)
    sample = rows[::step][:limit]

    docs = {}
    for sym, cik in sample:
        d = fetch(cik)
        if d is not None:
            docs[sym] = d
        sys.stderr.write('.')
        sys.stderr.flush()
    sys.stderr.write('\n%d/%d issuers fetched\n' % (len(docs), len(sample)))

    print('%-28s %-58s %6s' % ('concept', 'tag', 'issuers'))
    print('-' * 96)
    for concept, candidates in CONCEPTS.items():
        covered = set()
        for tax, tag, unit in candidates:
            n = [s for s, d in docs.items() if has_tag(d, tax, tag, unit) > 0]
            covered |= set(n)
            print('%-28s %-58s %4d/%d' % (concept, '%s:%s' % (tax, tag), len(n), len(docs)))
        missing = sorted(set(docs) - covered)
        print('%-28s %-58s %4d/%d   MISSING: %s'
              % ('', '>>> ANY of the above', len(covered), len(docs),
                 ','.join(missing) if missing else 'none'))
        print()
