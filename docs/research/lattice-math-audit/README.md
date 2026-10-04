# Lattice math and performance audit

## Simple conclusion

**The core OU equations are correct, but native Lattice has specific math defects. Our Python pilot differs from native Lattice and does not call the defective native helpers. Those defects cannot explain its 3.03% stock-forecast loss.**

I corrected an interpretation error: raw-stock forecast error and stock-minus-factor hedge error answer different questions. Raw-stock loss alone cannot reject hedged alpha. Re-scoring the same frozen predictions against their own frozen hedges still found worse error than zero. No predictions were refitted.

| Horizon | Own-basket observations | MST hedge MSE worse than its own zero |
|---|---:|---:|
| Next session, primary | 6,012 | 4.84% |
| Five sessions, secondary | 5,964 | 10.13% |
| Twenty sessions, secondary | 5,784 | 18.45% |

On the 4,562 valid-model primary observations the loss is 6.56%. Available-basket cohorts retain zero-forecast abstentions. Different models have different hedges, so cross-model hedged MSE ranking is invalid. These are post-result exploratory diagnostics on already inspected 2024/2025, with unadjusted circular date-block intervals. The exact daily sign policy still averages −0.91 bp/opportunity before costs; neither MSE nor these research marks certify executable P&L.

## Independent findings

Three reviewers separately audited [native geometry](native-spectral.md), [signals and adaptations](signals-and-adaptation.md), and [boundaries/options/evaluation](boundaries-options-evaluation.md). A [fourth reviewer](independent-review.md) challenged their conclusions and checked the rescore.

| Finding | Verified scope | Explains Python stock loss? |
|---|---|---|
| Native LW overwrites covariance diagonal instead of normalizing correlation | Compiled example: approximately zero reported shrinkage, correlation 0.5 instead of 1. Off-diagonals gain an unintended `(T−1)/T` factor. | No; helper not called. |
| Native singular RIE correction omitted | Compiled rank-two sample remains singular at q>1. Literature has a positive companion-transform nullspace correction. Conditional on RIE; default is shrink_clip. | No; helper not called. |
| MP continuous lower edge confused with zero atom | Compiled q=4/3: 0 rather than 0.0239323. Current clipping uses upper edge only. | No; metadata issue. |
| Native OU guard compares physical time to count | Compiled same sample rejected in days, accepted in years. Correct duration is `(n−1)*dt`. | No; default dt=1 unaffected. |
| Excursion durations remove failed/missing-fit periods | Static application source; changing daily models also prevent reading every band reentry as fixed-basket convergence. | No; these labels are not used. |
| One-factor risk benchmark uses scored book as its factor | Above its variance floor, discarding residual cross-covariances mechanically adds variance. | Risk-benchmark interpretation only. |
| Boundary tails lack future calibration | Fitted chi-square scores and self-included KDE thresholds are reference scores. Gaussian KDE normalization is correct. | Separate native score path. |
| Contextual filter control freezes training exposure | Synthetic increment can arise solely from holdout exposure changes; economic inference was already blocked. | Ancillary filter interpretation only. |

The original P1 label for *shrunk-covariance naming* is downgraded to an unquantified documentation/contract mismatch. Optional lower-dimensional mesh export and nonfinite graph inputs have separate static conditional defects; no production failure was reproduced.

## Why it performed worse

The exact primary hedge loss decomposition is mean forecast squared `0.0000107971` minus twice mean forecast times outcome `−0.00000202396`, giving excess error `0.0000128210`. Forecasts added magnitude without useful positive cross-product credit. This explains the arithmetic, not the causal design failure.

Possible causes include weak MST substitutes, noisy parameters, a hedge frozen 60 sessions before the decision, unstable reversion, zero expected future factors, and daily trading of tiny signals. No controlled ablation isolated these causes. Native full-distance kNN/simplex/log-spread/threshold rules differ from our signed-factor/simple-return adaptation. Native peers are chosen before MDS compression; native coordinates are not normalized onto a unit sphere.

The diagram separates equity forecasts, fixed-book risk, changing allocations, futures point-risk forecasts, options marks/coverage gates and native calculations. Futures were not in the newest 12-equity study. Options rarity is not IV, option mispricing or a payout probability. Financial numbers need meaning, units, release clocks and signed relationships to become useful context.

## Evidence

Remote run `/home/john-riley/QuantHacks/lattice-math-audit-20261004-v1` completed exit 0 under detached tmux/shared lock/two threads/4 GiB. **10 focused tests passed in 0.60 seconds**, and production local C++ witnesses compiled and ran. Boundary, mesh, options and application claims remain static/synthetic, not runtime certification. No full native suite or full account engine was certified.

Local native HEAD: `0d77fc4d15e1a84e0e6d5798617cc110c9f0390e`. Exact 26-file archive SHA-256: `5ee056e266a842c877ed85b278fd266b31509dbbb734f5501f7b0a7eff638101`. The different remote native checkout was not substituted. Compact receipts: `artifacts/lattice-math-audit/run-v1/`. Native witness SHA: `8470145b4a33bce4761ac556cbd62843dcee8633e8c795ae9c21c9a031ea36d3`; frozen-target report SHA: `a83459c936765e9ebf967c0cc4957865726f1d85c913fbb99882f95029478de6`. Previous result artifacts are unchanged; no purchase, new fit or trade occurred.

Actual scoped Graphify: **579 nodes / 1,061 links / 51 source files**; 1,047 EXTRACTED and 14 INFERRED links, all AST origin. Graph SHA: `be1345aa5a9d6cfbbfd77a2e6bea88b54ca00903e6418af18cd35a8f5f832959`. Root coordinator graph remains intact. Code structure and reviewed semantic links are separate evidence, not accepted runtime integration or causal economics.

Next: correct native estimators and time/domain guards; register a faithful native-versus-ordinary-peer comparison with identical target/holdings/clocks/costs; qualify futures dollar accounting and options deliverable/quote/lifecycle evidence; freeze any survivor for forward paper. The current pilot provides no promotion basis.

Primary basis: [Ledoit–Péché singular branch, theorem 1.4 equation 13](https://arxiv.org/pdf/0911.3010), [Ledoit–Wolf covariance shrinkage](https://perso.ens-lyon.fr/patrick.flandrin/LedoitWolf_JMA2004.pdf), [Avellaneda–Lee residual model/trading rules](https://math.nyu.edu/faculty/avellane/AvellanedaLeeStatArb071108.pdf).
