# Registered implementation choice

This extends Lattice's relationship representation into two separately evaluated numerical roles. The original 15 failed combined tests remain evidence. Nothing is promoted and no data order is required.

| Candidate | Support in our data | Decision |
|---|---|---|
| Frozen-hedge cumulative residual state | Daily equity history supports an explicit forecast; separate windows avoid forced endpoint pinning. | Implement against zero, mean, own-return AR1, market-only and equally sized ordinary peer controls. |
| Fixed-book covariance forecast | The same 12-name portfolio has a common next-session squared-return target for every estimator. | Implement shrinkage, diagonal, sample, factor and one explicit correlation-tree challenger. |
| Directed news graph / option relative value / futures portfolio hedge | Dated exposures, option lifecycle, or synchronized book and hedge intervals remain incomplete. | Preserve as untestable extensions with exact requirements; do not fabricate inputs. |

These are research adaptations, not a reproduction of the source papers or Lattice's native RIE/IPCA stack. The MST uses Lattice's signed correlation distance. The tree covariance replaces nonedge correlations with products along tree paths; this is neither LoGo nor proof that the discarded edges are noise.

## Grill iterations and rulings

1. **What exactly closes?** A cumulative, factor-adjusted residual, not a drawing on the sphere. Hedge coefficients/graph are fitted on an earlier 126-session window; the subsequent 60-session block fits the state. This disjoint specification is our explicit modification. Same-window OLS with intercept would mechanically force the residual endpoint to zero.
2. **What exactly is predicted?** Every direction model is scored against the same stock return. A hedge can lower its own residual variance without improving that forecast; comparing different residual MSE targets would be misleading. Future factor forecasts are fixed at zero, a disclosed assumption. Hedge path outcomes are additional diagnostics.
3. **Is the graph better than ordinary peers?** The MST neighbor basket faces top-correlation and normalized-price-path-distance baskets with the same neighbor count and predictor count. Graph choice uses only the earlier window. No sector membership or causal business exposure is inferred.
4. **Does a risk model merely move less money?** Primary risk forecasts all target the same fixed 1/N book. Secondary allocation policies remain long-only, gross one, capped at 25% at allocation/rebalance; holdings may drift between weekly rebalances. Costs use traded dollars and drifted holdings. Costs are assumed scenarios, not verified executions.
5. **Can a slower horizon rescue failure?** The human approved 5/20 sessions as separate diagnostics. Next-session remains primary. Secondary targets sum returns at fixed notional rather than silently switching to compounded or option returns. Labels stop at 2025-12-31 intentionally: the final h sessions have unobserved outcomes for horizon h, retained in every ledger; we do not inspect a new 2026 label tail.
6. **Where does this enter the wider project?** Our producer supplies versioned forecasts/risk diagnostics and hashes. Post Benchmark retains central record adaptation and economic replay. Actual consumer acceptance of the prior three-row fixture was diagnostics only; it did not lift clocks, identity or execution gates.

Exact parameters and trial family are in configs/experiments/lattice-strategies-v1.json, frozen before any real-data fit. The two component workers and root own separate source/test files. Heavy execution uses home-pc, detached tmux, the shared flock, two threads and a 4 GB cap. Dependencies and code/config/input hashes are recorded before fitting. The previously inspected 2024/2025 interval remains exploratory.
