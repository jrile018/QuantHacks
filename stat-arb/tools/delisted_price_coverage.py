#!/usr/bin/env python3
"""Measure the half of survivorship that reconstructed membership does not fix.

    tools/delisted_price_coverage.py --sample 60

WHY THIS EXISTS
---------------
tools/sp500_membership_history.py recovers WHO was in the index on any
past date, including the 416 names that have since left. That is the
denominator. It does not supply their PRICES, and a name in the universe
with no price series is not a tradable name - it is a hole.

Whether that hole matters is an empirical question about the price
source, not something to reason about from first principles, so this
asks it directly: take a sample of names that were index members and are
not any more, request each one's bars over a window when it WAS a
member, and count how many come back.

The answer is a number to put in the README beside the membership fix,
so the remaining gap is stated rather than implied. Sampling rather than
all 416 keeps this a measurement and not a scrape; the sample is drawn
deterministically (sorted, then evenly spaced) so two runs a month apart
ask about the same names and the figures are comparable.
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
UA = "geomarket-research/0.1 (+delisted price coverage measurement)"


def to_yahoo_symbol(ticker):
    # Same mapping gm-ingest uses, so this measures the coverage the
    # pipeline would actually get rather than a different question.
    return ticker.replace(".", "-")


def epoch(iso):
    return int(time.mktime(time.strptime(iso, "%Y-%m-%d")))


def bars_between(ticker, start_iso, end_iso):
    """Number of daily closes the source returns, or None if it refused."""
    url = "%s%s?period1=%d&period2=%d&interval=1d" % (
        CHART, to_yahoo_symbol(ticker), epoch(start_iso), epoch(end_iso))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            doc = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return None if e.code in (404, 400) else "error %d" % e.code
    except Exception as e:  # network flake: reported, not silently a zero
        return "error %s" % type(e).__name__
    result = (doc.get("chart") or {}).get("result")
    if not result:
        return None
    closes = ((result[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    return sum(1 for c in closes if c is not None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--membership", default="data/reference/sp500_membership.csv")
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--recent-observations", type=int, default=3,
                    help="a ticker absent from this many trailing observations counts as departed; "
                         "matches gm-data/membership.hpp, and for the same reason - one "
                         "imperfectly parsed revision must not retire a sitting member")
    ap.add_argument("--min-bars", type=int, default=100,
                    help="fewer bars than this over a year of membership is not a usable series")
    args = ap.parse_args()

    last_seen = {}
    observation_dates = set()
    with open(args.membership, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t, d = row["ticker"], row["observed_date"]
            observation_dates.add(d)
            last_seen[t] = d
    if not last_seen:
        sys.exit("membership file has no rows")

    # Absent from the last few observations, not merely from the final
    # one: parsing a rendered table across sixteen years is imperfect,
    # and a name one revision happened to miss is a sitting member, not
    # a departure. gm-data/membership.hpp makes the same distinction and
    # for the same reason - measured against the final observation alone
    # this sample contained AvalonBay.
    recent_dates = set(sorted(observation_dates)[-args.recent_observations:])
    recent = set()
    with open(args.membership, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["observed_date"] in recent_dates:
                recent.add(row["ticker"])
    departed = sorted(t for t in last_seen if t not in recent)
    if not departed:
        sys.exit("no departed tickers in the membership file")

    # Evenly spaced through the sorted list rather than random: the same
    # names every run, so the number can be compared over time.
    step = max(1, len(departed) // args.sample)
    sample = departed[::step][:args.sample]

    have, missing, errors = [], [], []
    for ticker in sample:
        # A year that ends at the last observation naming it, so the
        # window is one in which it was genuinely a member.
        end = last_seen[ticker]
        start = "%04d%s" % (int(end[:4]) - 1, end[4:])
        n = bars_between(ticker, start, end)
        time.sleep(1.0)
        if isinstance(n, str):
            errors.append((ticker, n))
            print("  %-6s %s" % (ticker, n), file=sys.stderr)
        elif n is None or n < args.min_bars:
            missing.append(ticker)
            print("  %-6s no usable series (%s)" % (ticker, "refused" if n is None else "%d bars" % n),
                  file=sys.stderr)
        else:
            have.append(ticker)
            print("  %-6s %d bars %s..%s" % (ticker, n, start, end), file=sys.stderr)

    answered = len(have) + len(missing)
    print()
    print("departed tickers in the membership file : %d" % len(departed))
    print("sampled                                 : %d" % len(sample))
    print("network errors (excluded from the rate) : %d" % len(errors))
    print("with a usable price series              : %d" % len(have))
    print("without                                 : %d" % len(missing))
    if answered:
        print()
        print("coverage of departed names: %.0f%%  (%d of %d answered)"
              % (100.0 * len(have) / answered, len(have), answered))
        print()
        print("This is the residual survivorship gap. Reconstructed membership says")
        print("which names belonged in the universe; this says how many of the departed")
        print("ones the price source can actually supply. The shortfall cannot be")
        print("closed from a free source and is the honest scope of ADR-016.")
    if missing:
        print()
        print("no series: %s" % ", ".join(missing))


if __name__ == "__main__":
    main()
