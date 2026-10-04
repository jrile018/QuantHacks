# What Lattice adds: completed research and implementation

**2026-10-04 interpretation update:** the [independent math audit](../lattice-math-audit/README.md) distinguishes native defects from this separate Python adaptation. The original 3.03% excess MSE is for raw-stock forecasts and cannot alone reject hedged alpha. Re-scoring the existing frozen MST predictions against their own hedge outcomes still loses to zero by 4.84% on the primary available-basket cohort (6.56% on valid models), with no refits. Original results remain preserved below.

## Simple answer

We turned relationships into two explicit questions:

1. **Did a stock drift away from its usual peers, and does that predict its next move?**
2. **How risky is the same basket of stocks likely to be tomorrow?**

The first graph-based signal failed this experiment. The second is a reasonable use of relationships, but our graph did not establish an advantage over simpler risk methods. **Current decision: no trade from this Lattice signal.** Keep the risk outputs as research context, with the standard methods available as controls.

## Research that changed the implementation

[Avellaneda–Lee](https://math.nyu.edu/faculty/avellane/AvellanedaLeeStatArb071108.pdf) model a factor-adjusted residual state rather than treating correlated stocks as an automatic trade. Their appendix acknowledges that estimating the hedge and residual on the same window forces the cumulative residual endpoint to zero. Our adaptation separates hedge formation from state calibration. It is not a reproduction of their historical performance.

[Mantegna](https://arxiv.org/abs/cond-mat/9802256) supports using correlations to organize relationships. A relationship still needs a separate prediction and cost test. Native Lattice uses cleaned correlation distances, kNN and MST, with signed basket weights estimated separately. Our narrow Python extension uses the MST distance idea; it does not silently reproduce native RIE/IPCA or claim causal business links.

The [mechanism review](mechanisms-primary-sources.md) and [risk/options review](risk-options-primary-sources.md) compare factor residuals, distance pairs, covariance shrinkage, hierarchical/filtered graphs, volatility forecasts, options variance and futures hedging. Their source studies have different universes, horizons and execution assumptions. We selected the two roles supported by our actual daily equity history.

## What was implemented and fixed before fitting

- Earlier **126 sessions** select peers and fit signed stock/hedge coefficients. The subsequent **60 sessions** calibrate residual state. Invalid mean-reversion fits abstain; they are not clipped into valid signals.
- Seven forecast models: zero, historical mean, own-return AR1, market-only state, MST peers, top-correlation peers and price-path-distance peers. Peer challengers have the same neighbor count and regression capacity.
- Every forecast faces the **same stock outcome**. Reduced variance of a different hedge target cannot count as improved stock prediction.
- Five risk estimators forecast the next squared return of the **same equal-weight 12-stock book**: diagonal, sample, Ledoit–Wolf, one-factor and an explicit tree covariance adaptation.
- Four secondary weekly allocation policies, gross one, long-only, 25% cap at rebalance. Holdings drift between rebalances. Costs are assumed **0/1/5/10 basis points per traded dollar per side**, including entry and final liquidation.
- Review corrected disappearing holdings on data gaps/failed rebalances, zero-variance tree crashes, terminal fees and common-cohort cost subtotals before real fitting.

Exact rules: [design](design-v1.md) and `configs/experiments/lattice-strategies-v1.json`. All ordinary choices followed the user's delegated ordering; the user explicitly approved secondary 5/20-session diagnostics. The grill iterations challenged endpoint pinning, target equality, ordinary-peer substitutes, reduced exposure, slower-horizon substitution and consumer boundaries.

## Forecast results

Data: 12 fixed equities, 2018–2025 price history; already inspected 2024–2025 evaluation, 502 decision sessions. Native adjusted-close snapshots have unqualified historical identity, adjustment and receipt vintages. These are exploratory statistical marks, not a new final test.

| Horizon | Matched stock opportunities | MST error versus zero-change forecast | Result |
|---|---:|---:|---|
| **Next session — primary** | 6,012 | **3.03% worse** | No forecast edge |
| 5 sessions — secondary | 5,964 | 8.10% worse | Does not rescue the primary |
| 20 sessions — secondary | 5,784 | 12.52% worse | Does not rescue the primary |

Zero had the lowest MSE of all seven models at all three horizons. On the 3,861 primary opportunities where all models had valid fits, zero remained best. The primary graph lost to zero even under the unadjusted date-block interval. All intervals remain exploratory, without multiple-comparison promotion.

MST produced 4,562 active observed daily spread marks and 1,450 no-trades. Its gross-normalized average was **−0.91 bp per opportunity even before assumed costs**. At 5 bp each way it was **−8.50 bp per opportunity**. These independently opened/closed basket marks assume favorable close-mark access and omit authoritative fills, borrow and financing; they cannot establish net account profit.

The 5/20 targets are sums of daily fractional returns, explicitly additive path diagnostics rather than compounded account returns. Labels intentionally stop in 2025. The last 1/5/20 sessions retain missing outcomes uniformly across models; no fresh 2026 tail was inspected.

## Risk results

All five risk estimators were scored on the same 501 portfolio dates. Lower QLIKE is better; it was registered as the primary risk loss.

| Method | QLIKE |
|---|---:|
| One-factor | **−8.0551** |
| Sample covariance | −8.0296 |
| MST tree | −8.0202 |
| Ledoit–Wolf | −8.0092 |
| Diagonal | −6.4891 |

The tree beat the weak diagonal estimate, but its intervals against sample, factor and shrinkage did not establish a gain. It had the lowest secondary MSE by point estimate (only about **0.10%** below shrinkage). That small secondary result does not override the primary comparison.

At the 5 bp allocation scenario, tree allocation had **2.29% higher daily standard deviation** and **10.58% lower average mark return** than shrinkage allocation. These are observed point comparisons, not forward significance or alpha claims. Lower risk than equal weighting alone is insufficient when a simpler allocation did better on these measures.

`one_way_trade_volume` describes entry/rebalance volume; terminal exit cost is reported separately. Add one gross unit for final liquidation when interpreting total traded dollars. Cost scenarios remain proxy diagnostics, not a funded portfolio replay.

## Tracking and verification

- Numerical study exit **0**; **20 focused tests passed** remotely.
- Retained **126,504** forecast rows, **2,510** risk rows and **8,032** allocation/scenario rows; every model, horizon, skip and cost variant remains visible.
- Independent audit verified **17 source hashes / 10 output hashes**, reconstructed **18,072 distinct stock path targets / 2,510 risk targets**, and checked **8,016 marked fee/weight rows** with **zero refits**.
- Independent code/result review: no remaining P1/P2 findings. A pandas API change initially broke only the post-run auditor; its failed log/version is retained and the corrected audit passed without changing model results.
- Final pre-fit source archive SHA256: `507495c3801c5e6400a650e417ba302f3565811cf7f3babbc1778c9864c1b4ab`.
- Model manifest SHA256: `198d053d176a9f1119f980063a96d216af870fee2a06f232b9a3a073277c66ee`.
- Verification receipt SHA256: `0ddcfc491454271a5b01360131d37ff132af7f9986038341c73461b7dbaa89cb`.
- Compact local reports: `artifacts/lattice-strategies/reports-v1/`. Six retrieved primary outputs and 16 local source replicas were separately hash-verified. Full row ledgers remain at `/home/john-riley/QuantHacks/lattice-strategies-20261004/results/strategies-v1/` because local disk space is scarce.

## Wider project and next supported step

Post Benchmark owns central adaptation and economic replay. We provide a hash-bound fixture of **21 stock candidate rows / 5 fixed-book risk rows**, explicit units and assumed session clocks; its new consumer audit is distinct from the already accepted prior three-row fixture. Missing receipt, identity, adjustment and execution fields remain null.

Existing selected option BBO marks were inspected and their actual file/hash/sample packet delivered. Their timestamps are received minute samples, their 100-share multiplier is inherited rather than authoritative, and adjustments/exercise/settlement/fill/fee gates remain open. Existing futures 09:36-to-next-09:36 marks do not align with this equity close-to-next-close book. No new data purchase occurred.

The useful next work is a qualified instrument/quote/lifecycle slice and a concrete economic exposure or pricing discrepancy. A dated company shock could then test a directed relationship; synchronized option chains could compare expected versus implied variance; aligned dollar book/futures marks could test a hedge. None of those prerequisites is created by drawing a graph, and this negative result provides no reason to tune the graph until it looks profitable.
