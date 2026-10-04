#!/usr/bin/env python3
"""Find ticker renames hiding in the membership history as a departure
plus an arrival.

WHY THIS EXISTS
---------------
ADR-023 gives every instrument a permanent key, taken from the SEC CIK
in universe.parquet. That catches an issuer wearing two tickers - but
only when BOTH tickers have a CIK, and the old ticker of a rename is
precisely the one that does not: it is gone from the current
constituents table, so it has no metadata row, so it falls back to a
ticker stand-in and the link is invisible. Measured on the real panel:
CIK identity finds 3 aliases, all of them dual share classes
(GOOG/GOOGL, FOX/FOXA, NWS/NWSA), and zero renames.

Meanwhile the membership history contains three real renames that CIK
cannot see:

    BK   -> BNY    (BK   last seen 2026-04-19, BNY  first 2026-05-23)
    ANTM -> ELV    (ANTM last seen 2022-05-20, ELV  first 2022-06-29)
    FB   -> META   (FB   last seen 2022-05-20, META first 2022-06-29)

Each has the same shape: one ticker's LAST observation is immediately
followed by another ticker's FIRST. That shape needs no metadata at all,
which is the whole point - it works on exactly the names the permanent
key cannot reach.

WHAT THIS IS NOT
----------------
It is not a resolver. A genuine departure at observation N and a genuine
unrelated addition at N+1 have the identical shape, and no amount of
staring at membership dates separates them. The output is therefore
CANDIDATES, ranked by how much else was happening at the same handoff: a
boundary where exactly one name left and exactly one arrived is worth
looking at; one where nine left and eleven arrived is quarterly index
rebalancing and the pairing is arbitrary.

Confirming a candidate takes a source this repository does not have - a
corporate-actions feed, or a human. See BLOCKED.md entry 5.

Usage:
    python3 tools/detect_ticker_renames.py \
        --membership data/reference/sp500_membership.csv \
        [--constituents data/reference/sp500_constituents.csv] \
        [--max-arrivals N]
"""

import argparse
import csv
import sys
from collections import defaultdict


def load_membership(path):
    """observation date -> set of tickers, in chronological order."""
    by_date = defaultdict(set)
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            sys.exit("membership file is empty: " + path)
        for row in reader:
            if len(row) < 2:
                continue
            by_date[row[0]].add(row[1])
    return [(d, by_date[d]) for d in sorted(by_date)]


def load_current_tickers(path):
    """Tickers still in the current constituents table - i.e. the ones
    that DO have metadata and therefore a permanent key already."""
    if not path:
        return set()
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return {row[0] for row in reader if row}
    except OSError:
        return set()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--membership", default="data/reference/sp500_membership.csv")
    parser.add_argument("--constituents", default="data/reference/sp500_constituents.csv")
    parser.add_argument("--top", type=int, default=60,
                        help="how many ranked candidates to print (default 60)")
    parser.add_argument("--max-arrivals", type=int, default=0,
                        help="only report handoffs with at most this many arrivals "
                             "(0 = report all, ranked)")
    args = parser.parse_args()

    observations = load_membership(args.membership)
    if len(observations) < 2:
        sys.exit("need at least two membership observations")
    current = load_current_tickers(args.constituents)

    # First and last observation INDEX per ticker. Index, not date, so
    # "immediately followed by" means the next observation rather than
    # some number of calendar days, which varies.
    first_index, last_index = {}, {}
    for i, (_date, members) in enumerate(observations):
        for ticker in members:
            first_index.setdefault(ticker, i)
            last_index[ticker] = i

    # Departures and arrivals at each handoff boundary i -> i+1.
    departures = defaultdict(list)
    arrivals = defaultdict(list)
    for ticker, idx in last_index.items():
        if idx < len(observations) - 1:
            departures[idx].append(ticker)
    for ticker, idx in first_index.items():
        if idx > 0:
            arrivals[idx - 1].append(ticker)

    candidates = []
    for boundary in sorted(set(departures) & set(arrivals)):
        left = sorted(departures[boundary])
        right = sorted(arrivals[boundary])
        for gone in left:
            for came in right:
                candidates.append({
                    "from": gone,
                    "to": came,
                    "last_seen": observations[boundary][0],
                    "first_seen": observations[boundary + 1][0],
                    "departures_at_boundary": len(left),
                    "arrivals_at_boundary": len(right),
                    # The old ticker being absent from the current table
                    # is what makes this case invisible to the permanent
                    # key - so these are the ones worth the attention.
                    "invisible_to_cik": gone not in current,
                })

    if args.max_arrivals > 0:
        candidates = [c for c in candidates if c["arrivals_at_boundary"] <= args.max_arrivals]

    # A 1:1 handoff is worth looking at; a 9-for-11 handoff is quarterly
    # rebalancing and every pairing in it is arbitrary.
    candidates.sort(key=lambda c: (c["departures_at_boundary"] * c["arrivals_at_boundary"],
                                    c["last_seen"], c["from"], c["to"]))

    clean = [c for c in candidates
             if c["departures_at_boundary"] == 1 and c["arrivals_at_boundary"] == 1]

    print("membership observations : %d (%s .. %s)"
          % (len(observations), observations[0][0], observations[-1][0]))
    print("tickers ever a member   : %d" % len(first_index))
    print("handoff candidates      : %d" % len(candidates))
    print("one-for-one handoffs    : %d   (highest confidence, but not the only real ones)" % len(clean))
    print()
    # Ranked, not filtered to one-for-one. Three renames confirmed by
    # hand - BK->BNY, ANTM->ELV, FB->META - all sit at busier handoffs
    # than 1:1, so a hard filter would have hidden exactly the cases
    # this tool exists to surface. DEP x ARR is printed instead, so the
    # confidence is visible per row rather than applied as a cutoff.
    print("%-6s %-6s %-12s %-12s %5s %5s  %s"
          % ("FROM", "TO", "LAST SEEN", "FIRST SEEN", "DEP", "ARR", "CIK-BLIND"))
    for c in candidates[:args.top]:
        print("%-6s %-6s %-12s %-12s %5d %5d  %s"
              % (c["from"], c["to"], c["last_seen"], c["first_seen"],
                 c["departures_at_boundary"], c["arrivals_at_boundary"],
                 "yes" if c["invisible_to_cik"] else "no"))
    if len(candidates) > args.top:
        print("... %d further candidates, progressively less likely "
              "(raise --top to see them)" % (len(candidates) - args.top))

    print()
    print("These are CANDIDATES, not renames. A real departure followed by an")
    print("unrelated addition has the identical shape and cannot be separated")
    print("from a rename using membership dates alone. Confirming one needs a")
    print("corporate-actions source this repository does not have - see")
    print("BLOCKED.md entry 5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
