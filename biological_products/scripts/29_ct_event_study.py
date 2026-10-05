"""Event study for posted ClinicalTrials.gov record changes.

Entry is the open of the first trading day strictly after the usable date
(posted date plus one calendar day). Day 5 and day 20 exits are inclusive.
Liquidity is checked using the market day before entry.
"""

import argparse
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


DIRECTIONS = {
    "primary_completion_date_change": -1,
    "status_to_terminated": -1,
    "status_to_suspended": -1,
    "status_to_withdrawn": -1,
    "status_to_active_not_recruiting": 1,
    "results_first_posted": 1,
    "primary_outcome_change": -1,
}


def month_t(frame, column):
    if frame.empty:
        return np.nan
    x = frame.groupby(["ticker", "month"])[column].mean().dropna().to_numpy()
    return x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 1 and x.std(ddof=1) > 0 else np.nan


def summarize(frame, label):
    print(label)
    print("type | n | mean5 | median5 | positive5 | t5 blocks | mean20 | median20 | positive20 | t20 blocks | same_day_8k | direction5 | direction20 | control_n | control5 | control20")
    for kind, group in frame.groupby("event_type", sort=True):
        clean5 = group.dropna(subset=["abn5"])
        clean20 = group.dropna(subset=["abn20"])
        direction = DIRECTIONS.get(kind)
        direction5 = (direction * clean5.abn5).mean() if direction else np.nan
        direction20 = (direction * clean20.abn20).mean() if direction else np.nan
        print(f"{kind} | {len(group)} | {clean5.abn5.mean():+.4f} | {clean5.abn5.median():+.4f} | {(clean5.abn5 > 0).mean():.3f} | {month_t(clean5, 'abn5'):+.2f} | {clean20.abn20.mean():+.4f} | {clean20.abn20.median():+.4f} | {(clean20.abn20 > 0).mean():.3f} | {month_t(clean20, 'abn20'):+.2f} | {group.same_day_8k.sum()} | {direction5:+.4f} | {direction20:+.4f} | {group.control5.notna().sum()} | {clean5.control5.mean():+.4f} | {clean20.control20.mean():+.4f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    args = parser.parse_args()
    raw = args.data / "raw"
    fds = args.data / "fds"
    changes = pd.read_csv(raw / "ct_changes.csv", keep_default_na=False)
    changes = changes[changes.initial.astype(int) == 0].copy()
    changes["event_type"] = changes.change_type
    status = changes.change_type == "status_change"
    changes.loc[status, "event_type"] = "status_to_" + changes.loc[status, "new_value"].str.lower()
    changes["posted"] = pd.to_datetime(changes.version_date.astype(str))
    changes["usable"] = changes.posted + pd.Timedelta(days=1)
    lookup = pd.read_csv(fds / "fds_lookup_cik_ticker.csv")
    c2t = dict(zip(lookup.cik.astype(int), lookup.ticker.astype(str)))
    t2c = dict(zip(lookup.ticker.astype(str), lookup.cik.astype(int)))
    prices = pd.read_csv(raw / "prices.csv", usecols=["ticker", "date", "open", "close"])
    prices["d"] = pd.to_datetime(prices.date.astype(str))
    price_map = {t: g.sort_values("d").reset_index(drop=True) for t, g in prices.groupby("ticker")}
    xbi = price_map["XBI"]
    xbi_by_day = xbi.set_index("d")
    features = pd.read_csv(fds / "fds_features.csv", usecols=["cik", "date", "px_adv20_usd_m", "px_close_raw"])
    features["d"] = pd.to_datetime(features.date.astype(str))
    feature_map = {(int(r.cik), r.d): (r.px_adv20_usd_m, r.px_close_raw) for r in features.itertuples(index=False)}
    filing = pd.read_csv(raw / "events_8k.csv", usecols=["cik", "filing_date", "supporting_text"])
    filing["d"] = pd.to_datetime(filing.filing_date, errors="coerce")
    filing_dates = defaultdict(list)
    for row in filing.itertuples(index=False):
        if pd.notna(row.d):
            filing_dates[int(row.cik)].append(row.d)
    news = pd.read_csv(raw / "news.csv", usecols=["ticker", "published_utc", "title", "description"])
    news["d"] = pd.to_datetime(news.published_utc, utc=True, errors="coerce").dt.tz_convert(None).dt.normalize()
    trials = pd.read_csv(raw / "trials.csv", usecols=["nct_id", "title"])
    titles = dict(zip(trials.nct_id, trials.title))
    calendar = xbi.d.to_numpy()
    rng = np.random.default_rng(0)

    def return_for(ticker, entry_index, horizon):
        stock = price_map.get(ticker)
        if stock is None or entry_index + horizon - 1 >= len(calendar):
            return np.nan
        start, end = pd.Timestamp(calendar[entry_index]), pd.Timestamp(calendar[entry_index + horizon - 1])
        s = stock.set_index("d")
        if start not in s.index or end not in s.index or start not in xbi_by_day.index or end not in xbi_by_day.index:
            return np.nan
        stock_open, stock_close = s.loc[start, "open"], s.loc[end, "close"]
        xbi_open, xbi_close = xbi_by_day.loc[start, "open"], xbi_by_day.loc[end, "close"]
        if min(stock_open, stock_close, xbi_open, xbi_close) <= 0:
            return np.nan
        return stock_close / stock_open - xbi_close / xbi_open

    def eligible(ticker, entry_index):
        if entry_index <= 0 or entry_index >= len(calendar):
            return False
        prior = pd.Timestamp(calendar[entry_index - 1])
        cik = t2c.get(ticker)
        adv, close = feature_map.get((cik, prior), (np.nan, np.nan))
        return pd.notna(adv) and pd.notna(close) and adv >= 1 and close >= 1

    # Matched random company-month market days use the same liquidity gate.
    eligible_by_company_month = defaultdict(list)
    eligible_by_company = defaultdict(list)
    for ticker in changes.ticker.unique():
        for i in range(1, len(calendar) - 19):
            if eligible(ticker, i):
                day = pd.Timestamp(calendar[i])
                eligible_by_company_month[(ticker, day.to_period("M"))].append(i)
                eligible_by_company[ticker].append(i)

    output = []
    for row in changes.itertuples(index=False):
        ticker = row.ticker
        if ticker not in price_map:
            continue
        # The first market day strictly after the usable calendar date.
        i = int(np.searchsorted(calendar, np.datetime64(row.usable), side="right"))
        if not eligible(ticker, i):
            continue
        abn5, abn20 = return_for(ticker, i, 5), return_for(ticker, i, 20)
        if pd.isna(abn5) and pd.isna(abn20):
            continue
        entry_day = pd.Timestamp(calendar[i])
        options = eligible_by_company_month.get((ticker, entry_day.to_period("M")), [])
        candidates = [j for j in options if abs(j - i) > 2]
        if not candidates:
            candidates = [j for j in eligible_by_company[ticker] if abs(j - i) > 2]
        control_i = int(rng.choice(candidates)) if candidates else None
        same_day = any(d == row.posted for d in filing_dates.get(int(t2c[ticker]), []))
        nearby = any(abs((d - row.posted).days) <= 2 for d in filing_dates.get(int(t2c[ticker]), []))
        output.append(dict(ticker=ticker, nct_id=row.nct_id, version_number=row.version_number,
                           days_shifted=row.days_shifted, event_type=row.event_type,
                           posted=row.posted, usable=row.usable, entry=entry_day,
                           month=str(entry_day.to_period("M")), abn5=abn5, abn20=abn20,
                           control5=return_for(ticker, control_i, 5) if control_i is not None else np.nan,
                           control20=return_for(ticker, control_i, 20) if control_i is not None else np.nan,
                           same_day_8k=same_day, nearby_8k=nearby))
    result = pd.DataFrame(output)
    if result.empty:
        print("No liquid events with complete price windows")
        return
    summarize(result, "All liquid events")
    summarize(result[~result.nearby_8k], "No 8-K within 2 calendar days of registry posting")
    print(f"Events on same day as 8-K: {result.same_day_8k.sum()} / {len(result)}")

    # Approximate mention search. Prefer NCT ID, then a specific asset token in the title.
    for event_type in ("primary_completion_date_change", "status_to_terminated"):
        sample = result[result.event_type == event_type]
        delays = []
        never = 0
        for row in sample.itertuples(index=False):
            title = str(titles.get(row.nct_id, ""))
            tokens = [row.nct_id.lower()] + [x.lower() for x in re.findall(r"\b[A-Z]{2,}[0-9]{2,}[A-Z0-9-]*\b", title)]
            tokens = list(dict.fromkeys(tokens))
            f = filing[filing.cik.astype(str).str.lstrip("0") == str(t2c[row.ticker])]
            n = news[news.ticker == row.ticker]
            fd = [x.d for x in f.itertuples(index=False) if x.d >= row.posted and any(t in str(x.supporting_text).lower() for t in tokens)]
            nd = [x.d for x in n.itertuples(index=False) if pd.notna(x.d) and x.d >= row.posted and any(t in (str(x.title) + " " + str(x.description)).lower() for t in tokens)]
            found = fd + nd
            if found:
                delays.append((min(found) - row.posted).days)
            else:
                never += 1
        median = np.median(delays) if delays else np.nan
        print(f"Mention check {event_type}: {len(sample)} events; median days to first later 8-K or news mention {median}; never mentioned {never}/{len(sample)}")
    destination = raw / "ct_event_study.csv"
    if destination.exists():
        raise SystemExit(f"Refusing to edit existing file: {destination}")
    result.to_csv(destination, index=False)
    print(f"Saved {destination}")
    print("Mention method: NCT ID or title asset code in 8-K supporting text or news title/description after posting. This misses releases without those strings and does not prove that the mention describes the change.")


if __name__ == "__main__":
    main()
