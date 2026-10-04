# Hypothesis: contracted revenue, R&D, AI and infrastructure investment (packaged software)

Written 2026-10-04 ~05:28 America/New_York (file modified time), BEFORE any return of the thesis composite was computed.
Universe: the 168 packaged-software companies in `data/packaged_software/final/feature_matrix_qualified.csv`.

## Economic hypothesis
**Who is on the other side?** Investors who price quarterly earnings noise and headline growth, and under-weight
(a) revenue that is already contracted, (b) sustained R&D and AI/infrastructure investment, and who over-hold
companies with governance and reporting instability.
**Why it may persist:** contracted/backlog revenue lowers cash-flow risk but is slow-moving and hard to screen;
R&D and infrastructure spending depress near-term margins, so earnings-focused investors discount them; management
turmoil is an under-priced signal of operating problems.
**Prediction:** within one quarter-end cross-section, companies scoring higher on the composite below earn higher
next-quarter returns than the equal-weight universe, net of costs.
**It fails if:** the top-quintile excess return is explained by market/size/value/momentum exposure, if the rank
correlation (IC) is indistinguishable from zero, or if it does not survive 2x costs.

## Pillars (fixed before looking at returns, equal weights, no tuning)
Positive: (P1) contracted backlog = RPO / TTM revenue; (P2) R&D intensity = quarterly R&D / revenue; (P3) AI intensity =
AI mentions per 100k characters of the latest 10-K filed before the formation date; (P4) infrastructure/energy
build-out proxy = TTM physical capex / TTM revenue.
Negative: (N1) unplanned executive departures (8-K Item 5.02, resigned or terminated) in the trailing 4 quarters;
(N2) reporting-quality problems = material weakness identified or own-financials restatement in the latest 10-K.
Federal contract awards (USAspending) and WARN layoffs were part of the thesis.

## Sparse-data rule (fixed in advance, applied by code, not by performance)
A pillar enters the composite only if (a) it is scored for >= 40% of eligible company-quarters, (b) it scores >= 25
companies in >= 75% of formation dates, and (c) a binary pillar has a >= 5% positive rate. Dropped pillars are
reported with the reason and may still be shown as a clearly labeled diagnostic.
Known before running: federal awards match only 44 of 168 companies exactly (the fuzzy matches are wrong,
e.g. Intuit -> Intuitive Surgical), WARN covers 8 companies, FERC/PPA text counts are candidate sentences only.

## Protocol
- Formation at each quarter end using only information public by then; enter at the NEXT trading close; hold to the
  next entry. Signal is lagged one session.
- Long-only top quintile, equal weight. Benchmark: equal-weight eligible universe. Eligibility: price >= $3 and
  60-day median dollar volume >= $1M, price identity status = provider match.
- Costs: 10 bp per side base, 20 bp (2x) and 50 bp stress. Costs are applied to traded notional at each rebalance.
- Formations 2023Q1 .. 2026Q1 (trailing-4Q departure data starts 2022-01; factor calendar ends 2026-08-31).
- Out-of-sample = last 20% of history (about 4 quarterly formations: 2025Q2 .. 2026Q1), run ONCE after the design is
  frozen. Everything earlier is in-sample.
- Report: annualized return, volatility, Sharpe, max drawdown, turnover, equity curve (IS and OOS separately), IC,
  4-factor regression (mkt, smb, hml, mom), block-bootstrap confidence intervals, capacity, trial count.

## Known limits (stated up front)
Survivors-only universe; membership and execution not fully certified; very short history; earlier project work
(`backtest_feature_strategies.py` and the feature-strategy report) already looked at this matrix, so the OOS window
is not a clean holdout in the strictest sense.
