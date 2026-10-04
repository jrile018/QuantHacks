#!/usr/bin/env python3
"""When does XBRL coverage actually begin, per issuer?

README.md has carried "XBRL coverage before ~2011 is unmeasured" as a
known gap since the fundamentals reader was written. The taxonomy was
phased in from 2009 for large filers, so ADR-002's 2010 start may sit
inside the ramp - but "may" is not a dataset statistic.

This measures it: for each issuer, the earliest EDGAR filing date and the
earliest period end present in companyfacts, for the concepts the
valuation coordinates actually need. The answer is what fraction of
ADR-002's window each coordinate can be computed over, which is the number
that belongs in the README instead of the caveat.
"""
import glob
import json
import os
import sys

CACHE = os.path.expanduser('~/projects/geomarket/data/raw/companyfacts_cache')

CONCEPTS = {
    'net_income (E/P)': [('us-gaap', 'NetIncomeLoss', 'USD'),
                         ('us-gaap', 'ProfitLoss', 'USD')],
    'op cash flow (FCF/P)': [
        ('us-gaap', 'NetCashProvidedByUsedInOperatingActivities', 'USD'),
        ('us-gaap', 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations', 'USD')],
    'operating income (EBITDA)': [('us-gaap', 'OperatingIncomeLoss', 'USD')],
    'long-term debt (EV)': [('us-gaap', 'LongTermDebtNoncurrent', 'USD'),
                            ('us-gaap', 'LongTermDebt', 'USD'),
                            ('us-gaap', 'LongTermDebtAndCapitalLeaseObligations', 'USD')],
}

WINDOW_START = '2010-01-04'   # ADR-002


def earliest_filed(doc, candidates):
    best = None
    for tax, tag, unit in candidates:
        try:
            entries = doc['facts'][tax][tag]['units'][unit]
        except (KeyError, TypeError):
            continue
        for e in entries:
            f = e.get('filed')
            if f and (best is None or f < best):
                best = f
    return best


if __name__ == '__main__':
    files = sorted(glob.glob(os.path.join(CACHE, 'CIK*.json')))
    if not files:
        sys.exit('no cached companyfacts; run the tag probe first')

    per_concept = {name: [] for name in CONCEPTS}
    late = {name: [] for name in CONCEPTS}
    for path in files:
        with open(path) as f:
            doc = json.load(f)
        name = doc.get('entityName', os.path.basename(path))[:22]
        for concept, candidates in CONCEPTS.items():
            first = earliest_filed(doc, candidates)
            if first is None:
                late[concept].append((name, 'never'))
                continue
            per_concept[concept].append(first)
            if first > WINDOW_START:
                late[concept].append((name, first))

    n = len(files)
    print('%d issuers, ADR-002 window starts %s\n' % (n, WINDOW_START))
    print('%-28s %-12s %-12s %-12s %s' % ('concept', 'earliest', 'median', 'latest',
                                           'issuers usable from 2010-01-04'))
    print('-' * 100)
    for concept in CONCEPTS:
        dates = sorted(per_concept[concept])
        if not dates:
            print('%-28s %s' % (concept, 'no issuer reports this at all'))
            continue
        on_time = sum(1 for d in dates if d <= WINDOW_START)
        print('%-28s %-12s %-12s %-12s %d/%d (%.0f%%)'
              % (concept, dates[0], dates[len(dates) // 2], dates[-1], on_time, n,
                 100.0 * on_time / n))

    print()
    for concept in CONCEPTS:
        rows = sorted(late[concept], key=lambda r: r[1])
        if not rows:
            continue
        print('%s - first available AFTER the window opens:' % concept)
        for name, when in rows[:8]:
            print('    %-24s %s' % (name, when))
        if len(rows) > 8:
            print('    ... and %d more' % (len(rows) - 8))
        print()
