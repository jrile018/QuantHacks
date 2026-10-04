# Sharpe confidence intervals and Monte Carlo validation

Date: 2026-10-04. Status: researched integration specification. The user requires a **95% confidence interval whenever the strategy's economic Sharpe is reported**, plus Monte Carlo validation after the upstream work is ready. No strategy backtest or simulation campaign was run for this document. No measured Sharpe, confidence limits, or profitability are claimed.

This extends the [canonical strategy-validation spine](../superpowers/plans/2026-10-03-strategy-validation.md), the [first-backtest process](../coordination/processes/first-backtest.md), and [regime/risk research](2026-10-03-regime-risk-and-signal-optimization.md). It has a [three-deliverable implementation plan](../superpowers/plans/2026-10-04-sharpe-confidence-and-monte-carlo.md). The other agent's strategy and accepted portfolio-ledger contract have not yet arrived in this chat. Their receipt should resolve the integration inputs in section 10, without reopening the research requirement.

Inspected root repository base: `3f76ce20b7b3e055b47e37478924a93eaaf1f126`. The working tree contains substantial concurrent, uncommitted work, so that commit alone does not identify the live sources. Implementation and runs must pin the actual source snapshot and input hashes. The nested `stat-arb/` repository is a separate owner boundary.

## 1. Recommended addition

Use the untouched chronological holdout of the single frozen final policy as the primary economic input, with regular net portfolio returns and a justified return-process assumption. Report its period Sharpe and an explicitly labeled annualization convention. Construct the primary 95% interval with a **studentized circular block bootstrap**, using dependence-aware standard errors and coverage calibration. Report a HAC asymptotic interval as a diagnostic. Keep simulation-based stress outcomes and selection-bias analysis as separate outputs. Point-only development diagnostics remain internal; an eligible economic Sharpe assessment cannot be `complete` before its calibrated 95% interval exists.

| Analysis | Question | Required output |
| --- | --- | --- |
| Historical economic replay | What did the frozen strategy earn at feasible prices? | Net equity/cash ledger, coverage, rejected opportunities, costs and lifecycle accounting |
| Sharpe sampling inference | How uncertain is the fixed policy's estimated population Sharpe? | Estimate, 95% interval, method/assumptions, block and HAC settings, invalid-state reasons |
| Paired economic comparison | Does the new layer improve the same baseline? | Paired difference in Sharpe and its 95% interval; growth and loss comparisons |
| Market-path Monte Carlo | How does the unchanged engine behave under specified alternative paths? | Conditional distributions of wealth, drawdown, loss, costs, cash/margin breaches and no fills |
| Selection/null analysis | Could the searched strategy family generate this result without an edge? | Trial ledger; justified search-aware null statistic/p-value; optional DSR/PBO diagnostics |
| Inference calibration | Does the interval procedure achieve its advertised coverage in controlled cases? | Repeated-sample coverage, null rejection and failure rates, each with simulation uncertainty |

An interval spanning economically attractive and unattractive outcomes is inconclusive for that comparison. A positive lower bound does not by itself pass coverage, costs, risk, selection or forward-validation gates. This project's selected objective remains **net portfolio growth within hard risk limits**; Sharpe is one summary, especially limited for nonlinear option tails.

## 2. Define the return series before defining Sharpe

Let `r_t` be the strategy's simple portfolio return for one complete, regular valuation interval and `rf_t` the matching risk-free return in the same currency and interval. Define `x_t = r_t - rf_t` and

```text
n = number of valid scheduled portfolio valuation intervals
mu_hat = sum(x_t) / n
s_hat = sqrt(sum((x_t - mu_hat)^2) / (n - 1))
S_hat = mu_hat / s_hat
```

The estimand is the population ratio `S = E[x_t] / sqrt(Var[x_t])` for the **frozen policy and specified return distribution/frequency**. The [original definition](https://web.stanford.edu/~wfsharpe/art/sr/SR.htm) uses differential return and its variability. Use arithmetic mean and sample standard deviation; CAGR divided by volatility is a different statistic.

Portfolio accounting requirements:

- Use total account equity with cash, all simultaneous holdings, financing, fees, distributions, and supported realized/unrealized marks. Remove external deposits/withdrawals using a declared cash-flow adjustment or subperiod time-weighting. Equity in the denominator is capital exposed to the policy, not option premium, notional or margin alone.
- Include valid flat/no-position periods on the selected calendar. Never treat individual trades, option variants, or repeated issuer labels as independent portfolio periods. Shared calendar shocks enter one portfolio path.
- Align the risk-free series and quote/accrual convention. An effective annual rate can be compounded to the interval; a discount yield or money-market quote needs its own conversion. Do not assume an unknown rate is zero.
- Preserve the session/time zone, valuation time, return units, equity base, missing/stale-mark reasons and instrument lifecycle. A source gap is not a zero return; silently dropping it changes frequency and can distort dependence. Do not bridge ineligible segments and call the result a complete daily path.
- Record quoted spread, additional slippage, impact, fees, financing and borrow separately; charge each once. Net-return resampling must not subtract the same historical costs a second time.
- Zero or negligible variance gives undefined or numerically unreliable Sharpe, including a cash-only portfolio with zero excess return. Bankruptcy/nonpositive equity remains an economic failure, not a row to discard to improve Sharpe. Report its path and failure state; never assign infinite Sharpe or erase the loss.

For a risky benchmark, `mean(r_strategy-r_benchmark)/sd(r_strategy-r_benchmark)` is labeled **information ratio**. It differs from `Sharpe(strategy)-Sharpe(benchmark)`. A cash/no-trade comparator whose excess-return variance is zero has no defined Sharpe; compare wealth/cost/risk directly rather than fabricate a benchmark ratio.

## 3. Frequency and annualization are part of the estimand

Report `S_hat` at the observation frequency first. If `A` is the declared number of valuation periods per reporting year, `S_conventional = sqrt(A) * S_hat` is a conventional scale of the period statistic. Its CI uses the same scale. Do not infer `A` from the number of trades or substitute 252 across every calendar without checking the portfolio contract.

[Lo's author publication record](https://alo.mit.edu/publications/page/18/) explains that ordinary square-root annualization is restricted by serial dependence. Distinguish the convention above from the Sharpe of a stationary **arithmetic sum** of `q` excess returns:

```text
gamma_k = Cov(x_t, x_(t-k))
Var(sum of q excess returns) = q*gamma_0 + 2*sum((q-k)*gamma_k, k=1..q-1)
S_q = q*mu / sqrt(q*gamma_0 + 2*sum((q-k)*gamma_k, k=1..q-1))
```

This identity follows by expanding the variance of a sum. It is not a compounded buy-and-hold return or CAGR identity. Estimating many autocovariances from a short history is unstable. If reporting an estimated `S_q`, bootstrap the **entire** statistic, including the estimated autocovariances; do not simply reuse the conventional annual CI. Label the horizon, stationarity assumptions, estimator and missing-history limitations. The direct MIT paper PDF was inaccessible in this research session; the author abstract and DOI [10.2469/faj.v58.n4.2453](https://doi.org/10.2469/faj.v58.n4.2453) verify the paper and its central annualization warning.

## 4. Construct the 95% interval

### 4.1 Analytic diagnostics

Under IID normal excess returns, a large-sample diagnostic is

```text
SE(S_hat) ~= sqrt((1 + S_hat^2/2) / n)
CI95_period ~= S_hat +/- 1.959963984540054 * SE(S_hat)
```

This is an asymptotic diagnostic, not finite-sample exactness or a dependence correction. Hypothetically, annualized conventional Sharpe 1.0 over 504 daily intervals with `A=252` gives annualized SE about 0.708 and CI about **[-0.387, 2.387]**, even under favorable IID normal assumptions. This is a locally checked arithmetic illustration, not project performance.

An optional finite-sample IID-normal diagnostic can invert the noncentral-t distribution: `sqrt(n)*S_hat` has `df=n-1` and noncentrality `sqrt(n)*S`. Solve its CDF at the observed statistic for lower/upper noncentralities at 0.975/0.025, then divide by `sqrt(n)`. [SciPy's official noncentral-t documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nct.html) supplies the distribution implementation. These assumptions are particularly restrictive for this strategy; this diagnostic cannot become the headline interval by convenience.

For weakly dependent, stationary returns with sufficient finite moments, use the delta-method influence sequence. The following is our explicit single-ratio implementation formula, with sample estimates substituted:

```text
psi_t = (x_t - mu)/sigma
        - mu * ((x_t - mu)^2 - sigma^2) / (2*sigma^3)
gamma_psi(k) = covariance of psi_t and psi_(t-k)
Omega_hat = gamma_hat_psi(0)
            + 2*sum((1-k/(L+1))*gamma_hat_psi(k), k=1..L)
SE_HAC(S_hat) = sqrt(Omega_hat/n)
CI95_HAC = S_hat +/- 1.959963984540054 * SE_HAC(S_hat)
```

Specify the covariance divisor, centering, Bartlett kernel, lag selection and finite-sample convention. Apply HAC to **psi**, including the squared-return component, rather than only to `x`; zero return autocorrelation does not rule out volatility clustering. The usual CLT needs positive volatility, finite fourth moments (stronger moment/mixing conditions for some dependent-process results) and weak dependence. These are assumptions to diagnose, not facts conferred by the software.

For paired strategies A and B, form `psi_delta_t = psi_A_t - psi_B_t`; estimate its long-run variance. This retains contemporaneous and lagged covariance. If this variance is zero because the paths are identical, report an explicitly degenerate equality rather than studentize by zero.

### 4.2 Primary interval: studentized circular block bootstrap

[Ledoit and Wolf's author working paper](https://www.econ.uzh.ch/apps/workingpapers/wp/iewwp320.pdf), sections 3.1–3.2, motivates HAC and studentized time-series inference for paired Sharpe differences; it also describes extension to a single ratio. Their fixed-block circular procedure informs this recommendation. Coverage still depends on return-process assumptions and calibration.

Freeze these operations before final evaluation:

1. Compute the observed statistic `theta_hat` and its positive, finite `se_hat`. `theta` is either period Sharpe or paired delta Sharpe; name it explicitly.
2. Resample circular blocks of `b` consecutive, aligned calendar return vectors. Sample starts uniformly, wrap at the sample end, concatenate, and trim the **last** block to exactly `n` observations. Retain strategy/baseline alignment and issuer/event grouping needed by the input grain.
3. For every replicate, recompute `theta_b` and its documented dependence-aware `se_b`. The bootstrap SE must respect the resampling/block structure; start with the circular-bootstrap studentization in the cited paper and calibrate any generic Bartlett-HAC substitution as a separate version. Copying `se_hat` into every replicate is not studentization.
4. Set `u_b = abs(theta_b - theta_hat)/se_b`. Let `c95` be the prespecified empirical 95th percentile of `u_b` with a recorded quantile convention.
5. Return the symmetric interval `[theta_hat-c95*se_hat, theta_hat+c95*se_hat]`. Multiply estimate and bounds by `sqrt(A)` only when the target is the same conventional scaled period statistic.

An equal-tail bootstrap-t interval is a registered alternative, using signed `t_b=(theta_b-theta_hat)/se_b` and endpoints `[theta_hat-q975(t)*se_hat, theta_hat-q025(t)*se_hat]`. Do not choose whichever interval looks better after inspecting the result. A percentile block interval may be a labeled sensitivity output; failure to studentize must not silently downgrade the primary method and issue a pass.

If `b=1`, the procedure reduces to IID resampling; use that for diagnostics, not as a universal setting. A stationary bootstrap has geometric random block lengths and is a **different** method. The [Politis–Romano paper](https://www.tandfonline.com/doi/abs/10.1080/01621459.1994.10476870) supplies its time-series basis. Both methods preserve observed structure within blocks and break some structure at joins; neither discovers unseen crises or cures structural change.

### 4.3 Block choice and failure rules

Choose block length on development/calibration data, assessing return and influence/squared-return dependence, overlapping positions and shared events. For mathematical consistency, block length grows with sample size while `b/n` tends to zero; this does not supply a magic finite-sample value. Record `n/b` as a diagnostic, not a literal independent-event count.

Candidate automatic selectors must include the [2009 correction](https://public.econ.duke.edu/~ap172/Patton_Politis_White_2009.pdf) to [Politis–White](https://www.math.ucsd.edu/~politis/SBblock-revER.pdf). An estimated selector is a starting point. Compare a preregistered shorter/reference/longer block grid and circular/stationary methods; retain all results. If conclusions depend on that choice, report instability/inconclusive. Sparse announcements or one common crisis cannot be repaired by multiplying bootstrap draws.

Predeclare `insufficient_data`, `invalid_return_panel`, `undefined_sharpe`, `invalid_studentization`, `calibration_failed`, and `complete` states. Include sample/unique-event counts, missing-mark flags, variance/SE conditions and all invalid-replicate reasons. Default to withholding the primary CI when any unresolved degenerate draws occur. An alternative extended-value or conditional-resampling rule needs separate documented calibration; silently discarding such draws biases the tails. Do not invent universal minimum-trade or minimum-day requirements; precision, block support, known-parameter calibration and independent-shock coverage determine adequacy.

The intended interpretation is **95% repeated-sample coverage for a fixed population parameter under the stated conditions**. It is not a 95% posterior probability that true Sharpe lies inside these bounds and not a predictive interval for future realized Sharpe. The fraction of ordinary bootstrap Sharpes above zero is neither that posterior probability nor a valid null p-value.

## 5. Monte Carlo campaign: three separate modes

### A. Sampling uncertainty of observed performance

Run the return-vector bootstrap above on the accepted frozen-policy economic replay. Compare strategies using the same replicate index paths. This measures sampling variability of the observed return process. It does not test how an adaptive execution/sizing engine changes its decisions on a new market path.

### B. Conditional market-path and execution stress

Once the engine interface exists, jointly simulate **market innovations/state vectors**, reconstruct valid paths, and rerun the unchanged causal engine, risk controls and ledger. Keep equity, rates, sector/common event factors, option-surface state and execution conditions contemporaneously aligned. Resample innovations rather than past absolute prices, contract IDs or option quotes onto incompatible future states.

Begin with joint block resampling and historical shock replay. Add a fitted heavy-tail/volatility-cluster/jump challenger only if it improves development diagnostics; fit it without final-period outcomes. Joint vectors preserve observed cross-asset dependence within blocks, while model challengers expose assumptions. Event/time/contract identity, expiration, corporate actions and quote consistency need an explicit reconstruction rule. If that rule is unsupported, expose the mode as unavailable rather than generating artificial executable prices.

For options, jointly revalue underlying movement, elapsed time, implied volatility/skew, spread, dividends/deliverable and exercise/assignment. Include no-event decay, correct forecast but overpriced premium, illiquid exit and jump/market co-movement. For futures, include variation cash, changing margin and roll/expiry. For stock shorts, include borrow availability, recall and cost. Trading gates and halts are part of execution, not guaranteed stop fills. Apply all shared capital limits across overlapping positions.

Stress reference costs and preregistered harsher spread/slippage/impact, latency, missing/partial fills, financing, margin and common-shock correlation. Stress magnitudes come from accepted quotes/broker/instrument evidence or explicitly labeled scenarios, not invented probabilities. Historical net-return bootstrap uses already charged costs; alternative execution stress recomputes the ledger.

Report horizon, conditional generator, wealth/CAGR distributions, maximum peak-to-trough drawdown, loss probability, expected shortfall when tails support it, turnover, fill rate, cost sensitivity, cash/margin failure and ruin. Ruin thresholds and numeric risk limits must be supplied by the strategy mandate. Stop new risk and carry the declared liquidation/valuation/absorbing failure policy through the horizon; do not erase failed paths. Stress frequencies describe the generator, not calibrated real-world crisis probabilities.

### C. Explicit zero-edge and search-aware null

For a fixed Sharpe or delta Sharpe, obtain a two-sided centered studentized bootstrap test from `abs(theta_hat)/se_hat` against the `u_b` distribution, recording `(exceedances+1)/(B+1)`. This is a test under stated inference assumptions. Do not equate zero differential mean with equality of two nonzero Sharpe ratios.

If the economic null is no incremental **mean performance differential**, center that differential and use a dependence-preserving null procedure. For best-of-many strategies, rerun the actual development search/selection in each null replicate and compare the corresponding maximum statistic. A mean-return null does not automatically test all definitions of Sharpe/utility superiority. Design any signal permutation after the causal strategy/holding-window contract arrives; unrestricted row shuffling breaks time and event structure.

[White's Reality Check](https://doi.org/10.1111/1468-0262.00152) provides a search-aware benchmark comparison framework. A fixed-policy CI alone does not account for selecting that policy using the same data.

## 6. Protect out-of-sample evaluation and account for searches

Keep chronological walk-forward development with all scaling, feature selection, model fitting, calibration, router/risk rules and parameter choice confined to available past observations. Preserve a genuinely untouched final period. Purge overlapping label/holding windows and group economic-event variants; embargo length follows the actual information/holding contract. Calendar shock dependence remains in inference even after leakage is removed.

The primary fixed-policy CI uses the untouched holdout of the **single frozen final policy**, with its stationarity/weak-dependence assumptions assessed. Causal walk-forward segments can contain different fitted models, parameters and distributions; joining them does not establish that estimand or stationarity. If a stitched OOS Sharpe is also evaluated, define its target as the preregistered retraining/evaluation procedure, record every fold/policy transition and capital/reset rule, and calibrate inference for that procedure, including refits where relevant. Otherwise its 95% CI is unavailable and its point statistic remains a separately labeled development diagnostic. Do not average fold Sharpes or present ordinary block resampling of mixed-policy returns as fixed-policy evidence.

Log every materially tried strategy, source subset, signal rule, holding period, instrument, risk profile, cost assumption and metric selection, including failed/abandoned candidates. The [Deflated Sharpe Ratio paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) uses track-record moments, trial Sharpe dispersion and an effective independent trial count to diagnose selection. Require defensible inputs, compatible units and an assumption report; absent trial history means `unavailable`, not one trial by default. DSR is a separate diagnostic, not a replacement CI or a general serial-dependence correction.

[PBO/CSCV research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) requires comparable candidate performance history. Use it only with the complete candidate-by-time matrix and state dependence/regime limitations. It cannot replace chronological validation or turn repeatedly inspected final data into a fresh holdout. Repeatedly checking a CI while collecting data also changes testing error; use fixed evaluation dates or a separately specified sequential method.

## 7. Choose simulation count by error, not appearance

Proposed development bootstrap count: `B=2,000`; initial final-analysis count: `B=10,000`. These are engineering starting settings, not guarantees. Predeclare independent seed batches and increasing-count checks. Stop on recorded simulation-precision tolerances with a fixed maximum budget; reaching the budget without precision gives `mc_precision_insufficient`.

For independent simulated paths conditional on the generator, a frequency estimate has simulation-only `SE ~= sqrt(p_hat*(1-p_hat)/B)`. At `p=0.05`, `B=10,000` gives about 0.00218 SE. Report Wilson or exact binomial uncertainty, especially at zero exceedances; zero observed breaches is not zero breach probability. [NIST's exact binomial interval documentation](https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbici.htm) provides a reference. This uncertainty is about finite simulation draws and excludes model/data uncertainty.

Record the rank-p-value resolution `1/(B+1)`. For CI endpoints and tail quantiles, use repeated independent batches or order-statistic rank uncertainty; binomial probability SE is not a Sharpe-endpoint SE. Validate the empirical quantile convention. Increasing draws reduces simulation noise and cannot add independent market history.

Before final use, register tolerances for interval endpoints and relevant tail metrics in their own units. A proposed endpoint tolerance is 0.02 conventional annual Sharpe units across independent-batch quantile uncertainty checks; this is a simulation precision setting for review, not a trading/promotion threshold. Rare tail-risk metrics may need substantially more draws. Preserve all batch estimates and failed convergence checks.

## 8. Calibrate the inference procedure itself

Outer Monte Carlo must generate independent *datasets* of the intended length under known population parameters; inner bootstrap draws construct one CI per dataset. Measure whether that CI includes the known `S` or paired `delta_S`. Merely recovering the sample Sharpe with resamples is not a coverage test.

The preregistered calibration matrix should include:

- IID Gaussian with zero and nonzero Sharpe, multiple sample lengths and optional exact noncentral-t comparison.
- Stationary AR(1)/VAR return processes with positive/negative autocorrelation; compute the known period Sharpe from their stationary mean/variance.
- Skewed finite-fourth-moment and Student-t with degrees of freedom above four, plus finite-fourth-moment stationary volatility clustering. Choose GARCH parameters using the appropriate fourth-moment condition, not only `alpha+beta<1`.
- Paired strategies sharing market innovations; identical paths, strongly correlated paths and near-degenerate deltas.
- Sparse event jumps/overlapping positions, short samples, missing/stale marks, zero variance, gaps, nonpositive equity and regime shifts. Invalid panels must be rejected. Nonstationary/infinite-fourth-moment cases are failure/stress diagnostics, not cases in which nominal coverage is promised.

Report coverage and false-positive rates with binomial Monte Carlo intervals, failure rates, interval widths, skew/tail behavior, HAC/block sensitivity and all predefined settings. For orientation, `M=2,000` outer datasets at true 95% coverage have simulation SE about 0.00487; exact/binomial bounds determine whether observed undercoverage is distinguishable from simulation noise. Do not force exactly 95.0% or choose the best method after seeing the final strategy result. A method that materially undercovers development-relevant cases fails calibration until repaired and rerun.

For market-path generators, compare simulated versus development-data autocorrelation, squared-return persistence, tails, cross-asset covariance and common event behavior. This is model checking, not proof that unseen tail probabilities are accurate.

## 9. Reproducibility and reports

Every assessment publishes:

```text
schema_version, method_version, strategy_id, policy_hash, engine_hash
source_commit, working_snapshot_hash, dependency/environment versions
input_snapshot_hashes, return_panel_hash, calendar/frequency/currency/units
valuation_basis, cash_flow_adjustment, risk_free_source/conversion
split dates, fold policy, as_of bounds, horizon, trial_registry_hash
n_periods, economic_event_counts, missing/stale/excluded opportunity counts
Sharpe estimand, annualization convention/factor, estimate, standard_error, ci_level=0.95
ci_lower, ci_upper, HAC kernel/lags/convention, bootstrap method/block settings
RNG algorithm, master seed, deterministic replicate substreams, B and batches
invalid replicate counts/reasons, calibration reference, convergence evidence
cost/borrow/margin/lifecycle/latency assumptions, baseline identity
scenario generator/version, wealth/loss metrics, simulation-only intervals
status, unmet gates and conclusion (candidate / inconclusive / no useful benefit)
```

Use JSON null plus explicit status/reasons for unavailable metrics; never publish `Infinity`, NaN, or fabricated bounds. Legacy descriptive trade/forecast scoreboards must retain their scope label and cannot be relabeled portfolio Sharpe. Plot equity/drawdown and the paired effect interval only when accepted outputs exist. A reproducible report may legitimately have no eligible economic assessment.

Large bootstrap campaigns, outer calibration, multi-year/path backtests and sweeps run automatically on **`home-pc` through detached `tmux`**, logged and identified by task. Prepare a pinned code/data bundle, record command/environment and expected output hashes, start detached, then poll session/log status without waiting in foreground. Retrieve artifacts before removing the finished session. If Tailscale/host access fails, report it; do not substitute the LAN address or launch the heavy job locally. Tiny deterministic fixtures and formula checks remain local. This research launched no remote jobs.

## 10. Handoff to the incoming strategy agent

### Current integration seams

The read-only integration audit found existing mean/forecast uncertainty, but no Sharpe estimator or portfolio path simulator in the current Python `src/`/`tests/` scope:

| Existing component | Current capability and boundary |
| --- | --- |
| `src/risk_management.py`: `bootstrap_ci`, `scoreboard` | IID percentile sample-mean CI and strategy/horizon P&L per dollar of spot; not Sharpe or account equity. `bootstrap_ci` drops NaNs and has its own small-sample behavior; do not reuse those semantics for the strict economic return panel. |
| `src/lattice_strategies/evaluation.py`: `paired_interval`, `summarize_forecasts`, `residual_cost_sensitivity`, `summarize_risk` | Paired forecast/mark comparisons and cost/allocation proxies. Multi-session fractional targets are arithmetic sums; these functions do not establish fills, funding, shared inventory or an account ledger. |
| `src/contextual_lattice/evaluation.py`: `evaluate_contextual_hypothesis`, `_ledger`, `_interval` | Opportunity-level decisions, labels, clocks, units, source versions and abstention evidence; preserve that grain. |
| `src/multi_market/evaluation.py`: `calendar_block_interval`, `evaluate_forecasts` | Mean intervals that bundle cross-section by date, with chronology and label-availability checks; useful alignment precedent, not a Sharpe CI implementation. |

The future performance adapter consumes a **distinct ordered periodic net account equity/return series** emitted by an accepted costed capsule. It must not pass `target`/`outcome` rows directly into Sharpe, sum opportunity marks into an alleged portfolio, or change upstream target semantics. Read the accepted consumer receipt to locate the eventual ledger and report hook.

Regression targets are `tests/test_lattice_strategy_evaluation.py`, `tests/test_contextual_lattice_evaluation.py`, and `tests/test_multi_market_evaluation.py`: shared targets/cohorts, paired/date-cluster behavior, chronology, retained missing opportunities and scope labels must survive. No `tests/test_risk_management.py` was found in the audit. Nested C++ Sharpe code does not establish an accepted root-Python portfolio contract.

### Required incoming packet

Provide these concrete inputs before connecting economic outputs:

| Input | Why it is required |
| --- | --- |
| Strategy/engine ID, frozen rules and candidate/trial ledger | Identifies the policy, adaptive behavior and selection exposure |
| Accepted immutable return/equity ledger path, schema and hashes | Establishes actual net portfolio returns and provenance |
| Calendar, valuation time, currency/units, cash-flow treatment and risk-free series | Defines Sharpe and reproducible annualization |
| Dated universe, event IDs and as-of/receipt/execution/lifecycle records | Prevents leakage and distinguishes missing data from losses/no trade |
| Baseline and identical evaluation opportunities | Supports a paired incremental-value comparison |
| Development/final split and holdout access policy | Constrains method calibration and prevents new selection on final data |
| Shared capital, allowed instruments, cash/margin/ruin and numeric risk limits | Defines valid economic replay and risk-stress outcomes |
| Engine replay interface and coherent market/quote-state reconstruction | Enables full path Monte Carlo beyond net-return resampling |
| Remote workspace/environment and artifact destination | Makes heavy runs detached, recoverable and reproducible |

Receipt does not authorize publishing messages, submitting paid data requests, or live trading. Research readiness does not depend on those actions. Integrate through the existing evaluation spine, with source-specific upstream owners retaining their schemas and responsibilities. Future implementation belongs in focused performance/simulation modules and a report adapter; no duplicate collector, learner or execution engine is proposed.

## 11. Completion criteria for the future implementation

Every eligible economic Sharpe report carries its 95% interval and inference metadata, or a precise insufficient/invalid reason. Paired comparisons preserve dependence. Controlled calibration supports the nominal procedure in its advertised domain. Market simulations rerun the frozen engine with realistic capital and lifecycle effects and remain clearly conditional. Selection diagnostics retain complete trials, final evaluation remains untouched until frozen, and the report is reproducible from pinned artifacts.

This document satisfies the research/handoff stage. Production integration and real strategy validation await the incoming accepted strategy contract and subsequent execution of the linked plan.
