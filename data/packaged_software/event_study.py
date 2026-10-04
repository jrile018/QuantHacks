"""Abnormal-return event study for the 168-company universe (checklist item 20).

For each event, the stock's abnormal return is its daily total return minus the market's
total return (Mkt-RF + RF from the Fama-French daily file), summed over a short window.
Cumulative abnormal returns (CAR) are then averaged across events and tested against zero
with a t-statistic.

Timing: the filing date is a date, not a timestamp, so the time of day of acceptance is unknown.
A filing made after the 16:00 New York close cannot move the stock on its own date, so day 0
is never used as a reaction day. The first eligible reaction day is the trading day after
the event date (day +1). This is a conservative policy for a daily proxy; it can miss part of
a reaction to a pre-open filing.

Stock total return: close-to-close price return plus cash dividends on their ex-dividend date
(split-adjusted amounts from extracts/backtest_inputs/dividends.csv), so it matches the market's
total return. Tickers absent from the dividend file are treated as paying no dividends in the
window; the file covers 16 of the 168 tickers.

Event types:
  auditor_change    first 10-K naming a new auditor (output/auditor_changes.csv)
  restatement       8-K Item 4.02, non-reliance on prior financials (output/8k_item_filings.csv)
  earnings          8-K Item 2.02, results of operations (output/8k_item_filings.csv)

Two windows are reported: day +1 to +2 (the first reaction) and day +1 to +6 (about one week).
Results are split into an early period (events before 2025) and a later period (2025 on),
so a pattern has to show up in both to be taken seriously.

Caveats:
  - Multiple event types and windows are tested, so one significant result is expected by
    chance. Treat any single result as a lead, not a finding.
  - Auditor changes are dated at the filing that reports them, which can lag the real change.
  - Event dates that fall on non-trading days use the next trading day.
Standard library only.
"""

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
BARS = HERE / "extracts" / "prices" / "daily_bars.csv"
DIVIDENDS = HERE / "extracts" / "backtest_inputs" / "dividends.csv"
FACTORS = OUT / "factor_returns_daily.csv"
AUDITOR = OUT / "auditor_changes.csv"
FILINGS = OUT / "8k_item_filings.csv"
OUT_EVENTS = OUT / "event_study_results.csv"
SPLIT = "2025-01-01"
# Offsets count trading days from the event date's session. Day 0 is excluded (see module docstring).
WINDOWS = {"d1_d2": (1, 2), "d1_d6": (1, 6)}
MIN_EVENTS = 5


def load_prices() -> dict[str, list[tuple[str, float]]]:
    series: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with BARS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["close"]:
                series[r["ticker"]].append((r["date"], float(r["close"])))
    for t in series:
        series[t].sort()
    return series


def load_market() -> dict[str, float]:
    """Total market return per day, in decimal: (Mkt-RF + RF) / 100."""
    market = {}
    with FACTORS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["mkt_rf"] and r["rf"]:
                market[r["date"]] = (float(r["mkt_rf"]) + float(r["rf"])) / 100.0
    return market


def load_dividends() -> dict[str, dict[str, float]]:
    """Split-adjusted cash dividends by ticker and ex-dividend date, summed when a date repeats."""
    divs: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    with DIVIDENDS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["split_adjusted_cash_amount"] and r["ex_dividend_date"]:
                divs[r["ticker"]][r["ex_dividend_date"]] += float(r["split_adjusted_cash_amount"])
    return divs


def daily_returns(prices: list[tuple[str, float]], dividends: dict[str, float]) -> dict[str, float]:
    """Total return on each session: (close + dividend going ex that day) / prior close - 1."""
    out = {}
    for (d0, p0), (d1, p1) in zip(prices, prices[1:]):
        if p0 > 0:
            out[d1] = (p1 + dividends.get(d1, 0.0)) / p0 - 1.0
    return out


def events() -> list[dict]:
    rows = []
    with AUDITOR.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"ticker": r["ticker"], "date": r["first_filing_with_new_auditor"], "type": "auditor_change"})
    with FILINGS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["item"] in ("4.02", "2.02") and r["form"] == "8-K":
                folder_date = r["filing_folder"].split("_")[0]
                kind = "restatement" if r["item"] == "4.02" else "earnings"
                rows.append({"ticker": r["ticker"], "date": folder_date, "type": kind})
    return rows


def car(ticker_returns: dict[str, float], market: dict[str, float], trading_days: list[str],
        event_date: str, lo: int, hi: int) -> float | None:
    """Cumulative abnormal return from day lo to day hi, counted in trading days."""
    start = next((i for i, d in enumerate(trading_days) if d >= event_date), None)
    if start is None:
        return None
    total = 0.0
    for k in range(lo, hi + 1):
        i = start + k
        if i >= len(trading_days) or i < 0:
            return None
        d = trading_days[i]
        if d not in ticker_returns or d not in market:
            return None
        total += ticker_returns[d] - market[d]
    return total


def tstat(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n < 2:
        return float("nan"), float("nan")
    mean = statistics.mean(values)
    sd = statistics.stdev(values)
    t = mean / (sd / math.sqrt(n)) if sd else float("nan")
    return mean, t


def main() -> int:
    prices = load_prices()
    market = load_market()
    trading_days = sorted(market)
    dividends = load_dividends()
    returns = {t: daily_returns(p, dividends.get(t, {})) for t, p in prices.items()}

    results = []
    evs = events()
    for etype in sorted({e["type"] for e in evs}):
        subset = [e for e in evs if e["type"] == etype]
        for period in ("early", "later", "all"):
            for wname, (lo, hi) in WINDOWS.items():
                vals = []
                for e in subset:
                    if e["ticker"] not in returns:
                        continue
                    in_period = (period == "all") or \
                                (period == "early" and e["date"] < SPLIT) or \
                                (period == "later" and e["date"] >= SPLIT)
                    if not in_period:
                        continue
                    c = car(returns[e["ticker"]], market, trading_days, e["date"], lo, hi)
                    if c is not None:
                        vals.append(c)
                mean, t = tstat(vals) if vals else (float("nan"), float("nan"))
                results.append({
                    "event_type": etype, "period": period, "window": wname,
                    "events_used": len(vals), "mean_car_pct": round(mean * 100, 3) if vals else "",
                    "t_stat": round(t, 2) if vals and not math.isnan(t) else "",
                    "enough_events": "yes" if len(vals) >= MIN_EVENTS else "no",
                })

    OUT.mkdir(parents=True, exist_ok=True)
    with OUT_EVENTS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    print(f"{len(evs)} events; results written to {OUT_EVENTS.name}\n")
    print(f"{'event':15} {'period':6} {'window':6} {'n':>4} {'mean CAR %':>11} {'t':>6}")
    for r in results:
        if r["events_used"]:
            print(f"{r['event_type']:15} {r['period']:6} {r['window']:6} {r['events_used']:>4} "
                  f"{str(r['mean_car_pct']):>11} {str(r['t_stat']):>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
