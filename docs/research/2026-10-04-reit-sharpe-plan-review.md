# REIT producer review of the Sharpe and Monte Carlo plan

Scope: read-only integration review requested by the human in Research Sharpe confidence intervals. This review does not run an economic backtest, simulation or market purchase.

## Fit and sequence

The research specification and implementation plan fit the existing canonical evaluator and portfolio boundary. Accepted, regular net portfolio returns must precede inference. Keep expensive path reconstruction and calibration after the first accepted costed slice; an initial missing-data finding cannot establish no trading edge.

Add these producer-specific requirements to the incoming-packet checklist and replay scenario registration:

1. Separate strict-arbitrage cash-flow proof from statistical repricing performance. An apparently deterministic discrepancy needs bounded execution, exercise, borrow and settlement risks; zero return variance can make Sharpe undefined. Retain dollar profit, residual obligations and feasible capacity even when Sharpe is unavailable.
2. Resample common calendar shocks jointly across issuers and all instrument legs. Shared banks, interest-rate exposure, repeated filing values and source versions do not create independent observations. Network co-occurrence is not a measured causal exposure; unknown loan participation weights need explicit bounds or an unavailable scenario.
3. Carry source-clock mode and its assumption policy into the accepted capsule. SEC acceptance-plus-24-hours is an explicit conservative replay assumption, not verified first-publication time. Replay-clock sensitivity cannot be mistaken for live receipt proof.
4. Keep the frozen degraded-date exclusions over the complete feature, decision and holding windows. Minute BBO/CBBO interval endpoints and last-trade timestamps cannot supply observed quote freshness or execution evidence.

These are additions to the existing contract, not a request for a separate calendar, engine, collector or source schema.

## Actual producer state

- Published baseline: 1,533 typed financial observations, not unique loans; no full economic consumer acceptance.
- Current source inspection: 37 retained SEC originals pass issuer, filing and byte-identity checks. First-public clocks and financial-meaning approval remain separate.
- Reviewed history candidate: 8 events, 11 source-local components, 2 relations, 14 typed roles, 9 entities and 21 evidence requests. Nineteen ordered observations and five without information-time ordering are not confirmed cash-flow histories; zero confirmed borrowing/repayment flows.
- Six development market deliveries complete. The adapter is being corrected to preserve minute interval and last-trade semantics. Sentinel contract multipliers, missing dated action/deliverable evidence and missing cost qualification prevent execution claims.
- The producer has no accepted net-return/equity ledger, measured strategy Sharpe or final out-of-sample result. Post Benchmark owns the canonical economic ledger and evaluator; its latest received capsule reports zero costed/canonical labels.

## Subjective planning prior

If forced to choose a number before accepted net returns, use a planning prior centered on **zero annualized after-cost out-of-sample excess-return Sharpe** for an active candidate, with substantial uncertainty in both directions. This is a subjective assumption, not a measured forecast, fitted distribution, numerical uncertainty range or 95% confidence interval. A cash-only/no-trade path can have undefined Sharpe.

Assume zero incremental information edge until the paired evaluation establishes otherwise; trading costs can make an active implementation worse. Total portfolio Sharpe also depends on market beta, leverage, cash yield, risk limits and supported execution. Forecast accuracy, source counts and loan-network counts do not identify it.
