#!/usr/bin/env python3
"""Per-yield derivability, which is the number that decides the design.

Per-concept coverage is not the answer: a yield needs SEVERAL concepts at
once, so what matters is the intersection. This also separates two cases
that per-concept counting conflates:

  REQUIRED   - absence means the yield cannot be computed for that issuer
               (no net income, no share count, no cash).
  OPTIONAL   - absence most likely means the issuer HAS none of it, and
               treating it as zero is correct rather than a guess. A
               company with no marketable securities does not tag
               ShortTermInvestments with a zero; it omits the tag.

Getting that distinction wrong in either direction is a silent error:
treating optional-absent as fatal throws away issuers needlessly, and
treating required-absent as zero fabricates a number.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xbrl_tag_coverage import CONCEPTS, fetch, has_tag  # noqa: E402
import csv
import os

# Which concepts a yield needs, and whether absence is fatal or means zero.
REQUIRED = {
    'e_p':     ['net_income', 'shares'],
    'fcf_p':   ['operating_cash_flow', 'capex', 'shares'],
    'ebitda_ev': ['operating_income', 'depreciation_amortisation', 'shares',
                  'cash', 'long_term_debt'],
}
OPTIONAL = {
    'e_p': [],
    'fcf_p': [],
    # Absent short-term debt / short-term investments almost always means
    # the issuer has none, not that it failed to report. Counted so the
    # assumption is visible rather than buried.
    'ebitda_ev': ['short_term_debt', 'short_term_investments'],
}

if __name__ == '__main__':
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rows = []
    with open(os.path.expanduser(
            '~/projects/geomarket/data/reference/sp500_constituents.csv')) as f:
        for row in csv.DictReader(f):
            rows.append((row['symbol'], int(row['cik'])))
    step = max(1, len(rows) // limit)
    sample = rows[::step][:limit]

    docs = {}
    for sym, cik in sample:
        d = fetch(cik)
        if d is not None:
            docs[sym] = d
    print('%d issuers\n' % len(docs))

    present = {}  # sym -> set of concepts resolvable
    for sym, doc in docs.items():
        got = set()
        for concept, candidates in CONCEPTS.items():
            if any(has_tag(doc, t, g, u) > 0 for t, g, u in candidates):
                got.add(concept)
        present[sym] = got

    for yield_name in ('e_p', 'fcf_p', 'ebitda_ev'):
        need = REQUIRED[yield_name]
        ok = [s for s, got in present.items() if all(c in got for c in need)]
        bad = sorted(set(present) - set(ok))
        print('%-10s derivable for %2d/%2d issuers (%.0f%%)'
              % (yield_name, len(ok), len(docs), 100.0 * len(ok) / len(docs)))
        if bad:
            print('           blocked: %s' % ','.join(bad))
            # Which requirement did each blocked issuer actually miss?
            for s in bad:
                missing = [c for c in need if c not in present[s]]
                print('             %-8s missing %s' % (s, ', '.join(missing)))
        for c in OPTIONAL[yield_name]:
            n = sum(1 for s in ok if c in present[s])
            print('           optional %-24s present for %d/%d of those '
                  '(rest treated as zero)' % (c, n, len(ok)))
        print()
