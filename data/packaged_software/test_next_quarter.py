"""Do the metrics predict next-quarter revenue growth? (checklist item 20.1)

Design, following the analysis notes on the checklist:

  Point-in-time    a predictor measured at quarter t is only used if the filing that
                   carried it was public (available_date_conservative) before the target
                   quarter ended. Without this the test reads the future.
  Cross-sectional  within each quarter, companies are ranked by the predictor and by the
                   next quarter's revenue growth, and the rank correlation (the
                   information coefficient, IC) is computed for that quarter.
  Aggregate        the per-quarter ICs are averaged and tested against zero. A predictor
                   that works should have a consistent sign, not one big quarter.
  Holdout          ICs are reported for an early period, a later period, and overall. A
                   predictor has to hold in both halves to be worth anything.

Writes output/next_quarter_test.csv.

Multiple predictors are tested, so the best one will look better than it is. With this
many tests, an average IC needs |t| well above 2 before it means anything.
Standard library only.
"""

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "extracts" / "company_metrics" / "fundamentals_quarterly.csv"
OUT = HERE / "output" / "next_quarter_test.csv"
SPLIT = "2024-07-01"
MIN_COMPANIES_PER_QUARTER = 20

# Predictors available in the quarterly file, as (column, higher_is_better_label)
PREDICTORS = [
    "rev_growth_yoy_q",      # growth momentum
    "gross_margin",
    "rd_pct_rev",
    "sm_pct_rev",
    "sbc_pct_rev",
    "fcf_physical_capex_margin",
    "goodwill_to_assets",
    "purchase_obligations_pct_ttm_rev",
]
# Two targets. The level of next-quarter growth is largely predictable from this quarter's
# growth for a mechanical reason: both are year-over-year figures sharing three quarters of
# revenue, so the IC on it is autocorrelation, not forecasting skill. The change in growth
# removes that overlap and is the honest test of whether a metric anticipates a turn.
TARGETS = {
    "next_growth_level": lambda cur, nxt: num(nxt.get("rev_growth_yoy_q", "")),
    "next_growth_change": lambda cur, nxt: (
        None if num(nxt.get("rev_growth_yoy_q", "")) is None or num(cur.get("rev_growth_yoy_q", "")) is None
        else num(nxt["rev_growth_yoy_q"]) - num(cur["rev_growth_yoy_q"])
    ),
}


def num(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def rank(values: list[float]) -> list[float]:
    """Average ranks, so ties do not bias the correlation."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num_ = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num_ / den if den else None


def main() -> int:
    with SRC.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_company: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_company[r["ticker"]].append(r)
    for t in by_company:
        by_company[t].sort(key=lambda r: r["period_end"])

    # Build (quarter, ticker, predictor values, next-quarter growth) with point-in-time checks
    samples: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    skipped_lookahead = 0
    for ticker, quarters in by_company.items():
        for cur, nxt in zip(quarters, quarters[1:]):
            known_at = cur.get("available_date_conservative") or ""
            # The predictor must have been public before the target quarter ended
            if known_at and known_at >= nxt["period_end"]:
                skipped_lookahead += 1
                continue
            for target_name, fn in TARGETS.items():
                target = fn(cur, nxt)
                if target is not None:
                    samples[cur["period_end"]][target_name].append((ticker, cur, target))

    results = []
    for target_name in TARGETS:
        for predictor in PREDICTORS:
            for period in ("early", "later", "all"):
                ics, n_used = [], 0
                for quarter in sorted(samples):
                    in_period = (period == "all") or \
                                (period == "early" and quarter < SPLIT) or \
                                (period == "later" and quarter >= SPLIT)
                    if not in_period:
                        continue
                    xs, ys = [], []
                    for ticker, cur, target in samples[quarter][target_name]:
                        x = num(cur.get(predictor, ""))
                        if x is None:
                            continue
                        xs.append(x)
                        ys.append(target)
                    if len(xs) < MIN_COMPANIES_PER_QUARTER:
                        continue
                    ic = spearman(xs, ys)
                    if ic is not None:
                        ics.append(ic)
                        n_used += len(xs)
                if len(ics) < 3:
                    continue
                mean_ic = statistics.mean(ics)
                sd = statistics.stdev(ics) if len(ics) > 1 else 0.0
                t = mean_ic / (sd / math.sqrt(len(ics))) if sd else float("nan")
                results.append({
                    "target": target_name, "predictor": predictor, "period": period,
                    "quarters": len(ics), "company_quarters": n_used,
                    "mean_ic": round(mean_ic, 4),
                    "t_stat": round(t, 2) if not math.isnan(t) else "",
                    "share_quarters_positive": round(sum(1 for i in ics if i > 0) / len(ics), 2),
                })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    print(f"Point-in-time filtered; {skipped_lookahead} pairs dropped for lookahead.")
    print(f"{'target':20} {'predictor':30} {'period':6} {'qtrs':>5} {'mean IC':>8} {'t':>7} {'% +':>5}")
    for r in results:
        print(f"{r['target']:20} {r['predictor']:30} {r['period']:6} {r['quarters']:>5} {r['mean_ic']:>8} {str(r['t_stat']):>7} {r['share_quarters_positive']:>5}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
