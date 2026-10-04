"""Do data-centre capex, cloud spend and AI intensity predict excess returns?

Candidate signals, each measured per company-quarter using only information public by the
quarter end (available_date_conservative for XBRL-based figures, filing date for 10-K text):

  capex_pct_rev          TTM physical capex as a share of revenue (data-centre build-out proxy)
  purchase_oblig_pct     unrecorded purchase obligations as a share of TTM revenue (commitments,
                         which include cloud and hosting contracts)
  cloud_mentions         cloud-provider names per 10-K (AWS, Azure, Google Cloud)
  ai_mentions_per_k      AI or machine-learning mentions per 1,000 words of the 10-K
  ai_mentions_change     change in AI intensity against the company's prior 10-K

Outcome: the company's return in excess of the market (Mkt-RF + RF) over the 63 trading
days after the quarter end. Each signal is rank-correlated with the outcome within each
quarter (information coefficient), and the per-quarter ICs are averaged. Significance uses
the spread across quarters, which is the level the project's spec requires, since companies
share market dates within a quarter.

Two periods are reported: 2022-2023 (warm-up) and 2024 onward (evaluation). A signal has to
hold in both to be credible. The number of signals tested is recorded so the threshold can
be corrected for multiple comparisons.

Writes output/datacenter_ai_signals.csv.
"""

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
EXTRACTS = HERE / "extracts"
HORIZON = 63
EVAL_START = "2024-01-01"
MIN_COMPANIES = 20


def read(p: Path) -> list[dict]:
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cal_quarter(date: str) -> str:
    y, m = int(date[:4]), int(date[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def quarter_end(q: str) -> str:
    y, qn = int(q[:4]), int(q[-1])
    last = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[qn]
    return f"{y}-{last}"


def rank(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < MIN_COMPANIES:
        return None
    rx, ry = rank(x), rank(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num_ = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num_ / den if den else None


def main() -> int:
    # Prices and market returns
    closes: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in read(EXTRACTS / "prices" / "daily_bars.csv"):
        if r["close"]:
            closes[r["ticker"]].append((r["date"], float(r["close"])))
    for t in closes:
        closes[t].sort()
    market = {}
    for r in read(EXTRACTS / "../output/factor_returns_daily.csv") if (EXTRACTS / "../output/factor_returns_daily.csv").exists() else read(OUT / "factor_returns_daily.csv"):
        if r["mkt_rf"] and r["rf"]:
            market[r["date"]] = (float(r["mkt_rf"]) + float(r["rf"])) / 100.0
    days = sorted(market)
    day_index = {d: i for i, d in enumerate(days)}

    def forward_excess(ticker: str, start_date: str) -> float | None:
        series = closes.get(ticker, [])
        dates = [d for d, _ in series]
        i0 = next((i for i, d in enumerate(dates) if d > start_date), None)
        if i0 is None or i0 + HORIZON >= len(series):
            return None
        p0, p1 = series[i0 - 1][1] if i0 else None, series[i0 + HORIZON][1]
        if not p0:
            return None
        stock = p1 / p0 - 1
        window = [d for d in dates[i0 - 1:i0 + HORIZON] if d in market]
        mkt = sum(market[d] for d in window)
        return stock - mkt

    # Quarterly XBRL-based figures, public by the availability date
    fundamentals = read(EXTRACTS / "company_metrics" / "fundamentals_quarterly.csv")
    xbrl: dict[tuple[str, str], dict] = {}
    for r in fundamentals:
        as_of = r.get("available_date_conservative", "")
        if not as_of:
            continue
        q = cal_quarter(as_of)
        key = (r["ticker"], q)
        prev = xbrl.get(key)
        if prev is None or as_of > prev["as_of"]:
            xbrl[key] = {"as_of": as_of, "capex": num(r.get("physical_capex_pct_rev")),
                         "oblig": num(r.get("purchase_obligations_pct_ttm_rev"))}

    # 10-K text, dated by filing date
    tenk = {}
    for r in read(OUT / "tenk_sections.csv"):
        q = cal_quarter(r["filing_date"])
        words = num(r.get("mda_words")) or 0
        tenk[(r["ticker"], q, r["filing_date"])] = {"words": words}
    flags = {}
    for r in read(OUT / "tenk_text_flags.csv"):
        key = (r["ticker"], r["filing_date"])
        flags[key] = {"cloud": num(r.get("cloud_provider_mention")) or 0,
                      "ai": num(r.get("artificial_intelligence")) or 0,
                      "words": tenk.get((r["ticker"], cal_quarter(r["filing_date"]), r["filing_date"]), {}).get("words", 0)}

    # Per company: each 10-K's signals, plus the prior filing's AI intensity for the change
    per_filing: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for (ticker, date), f in flags.items():
        if f["words"]:
            per_filing[ticker].append((date, {
                "cloud": f["cloud"], "ai_per_k": 1000 * f["ai"] / f["words"]}))
    for t in per_filing:
        per_filing[t].sort()

    # Build company-quarter observations
    tickers = sorted(closes)
    quarters = sorted({q for (_, q) in xbrl} | {cal_quarter(d) for t in per_filing for d, _ in per_filing[t]})
    obs = defaultdict(dict)  # quarter -> ticker -> signals + outcome
    for q in quarters:
        qe = quarter_end(q)
        if qe > days[-1]:
            continue
        for t in tickers:
            row = {}
            x = xbrl.get((t, q))
            if x:
                row["capex_pct_rev"] = x["capex"]
                row["purchase_oblig_pct"] = x["oblig"]
            # latest 10-K filed on or before quarter end
            prior = [(d, v) for d, v in per_filing.get(t, []) if d <= qe]
            if prior:
                d_last, v_last = prior[-1]
                row["cloud_mentions"] = v_last["cloud"]
                row["ai_mentions_per_k"] = v_last["ai_per_k"]
                if len(prior) >= 2:
                    row["ai_mentions_change"] = v_last["ai_per_k"] - prior[-2][1]["ai_per_k"]
            out = forward_excess(t, qe)
            if out is not None:
                row["outcome"] = out
            if row:
                obs[q][t] = row

    signals = ["capex_pct_rev", "purchase_oblig_pct", "cloud_mentions",
               "ai_mentions_per_k", "ai_mentions_change"]
    results = []
    for s in signals:
        for period, keep in (("2022-2023", lambda q: q < "2024Q1"),
                             ("2024-onward", lambda q: q >= "2024Q1"),
                             ("all", lambda q: True)):
            ics = []
            for q in sorted(obs):
                if not keep(q):
                    continue
                pairs = [(v[s], v["outcome"]) for v in obs[q].values()
                         if s in v and "outcome" in v and v[s] is not None]
                if len(pairs) < MIN_COMPANIES:
                    continue
                ic = spearman([p[0] for p in pairs], [p[1] for p in pairs])
                if ic is not None:
                    ics.append(ic)
            if len(ics) < 3:
                continue
            mean = statistics.mean(ics)
            sd = statistics.stdev(ics)
            t_stat = mean / (sd / math.sqrt(len(ics))) if sd else float("nan")
            results.append({"signal": s, "period": period, "quarters": len(ics),
                            "mean_ic": round(mean, 4),
                            "t_stat_across_quarters": round(t_stat, 2) if not math.isnan(t_stat) else "",
                            "share_quarters_positive": round(sum(1 for i in ics if i > 0) / len(ics), 2)})

    # Bonferroni across every signal-by-period test in this family: two-sided alpha 0.05
    # divided by the number of tests. The critical t depends on the quarters in each row,
    # so it is computed per row with a normal approximation (conservative for ~15 quarters).
    from statistics import NormalDist
    n_tests = len(results)
    alpha = 0.05 / max(n_tests, 1)
    for r in results:
        r["tests_in_family"] = n_tests
        r["bonferroni_critical_t"] = round(NormalDist().inv_cdf(1 - alpha / 2), 2)
        t = r["t_stat_across_quarters"]
        r["passes_bonferroni"] = "yes" if t != "" and abs(float(t)) >= r["bonferroni_critical_t"] else "no"

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "datacenter_ai_signals.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    print(f"{'signal':20} {'period':12} {'qtrs':>5} {'mean IC':>8} {'t':>7} {'%+':>5}")
    for r in results:
        print(f"{r['signal']:20} {r['period']:12} {r['quarters']:>5} {r['mean_ic']:>8} "
              f"{str(r['t_stat_across_quarters']):>7} {r['share_quarters_positive']:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
