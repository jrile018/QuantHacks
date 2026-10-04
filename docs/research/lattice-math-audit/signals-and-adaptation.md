# Signal equations and Python adaptation audit

Audit date: 2026-10-04. Production source was read only. Scope: native peer baskets, OU fit, signal app and excursions; Python residual, graph, risk and evaluation modules; registered `lattice-strategies-v1.json`; compact `artifacts/lattice-strategies/reports-v1` reports. “Last seven models” means the seven models registered in that configuration. This is an equation and interpretation audit, not a new backtest, native binary certification, or full account/execution audit.

## Conclusion

The central AR(1)–OU equations and the Python hedge signs are algebraically correct. The strongest correction to the previous interpretation is that the Python pilot is **not a reproduction of native Lattice**. A raw-stock forecast loss also does not by itself establish failure of a hedged residual strategy. There are nevertheless specific native time-axis defects, a risk-control construction effect, and substantial limits to the trading conclusions.

The existing pilot still provides no reason to promote its particular MST strategy: its raw-stock one-day MSE is 3.03% worse than zero, and its independent, gross-normalized hedged daily sign marks average −0.910 basis points per opportunity before assumed costs. Correcting the interpretation does not turn either result into evidence of profitable trading. It narrows the result to the tested model and policy.

## Findings with reproducible consequences

| ID / severity | Affected branch and exact source | Expected versus actual | Consequence and witness |
|---|---|---|---|
| S1 / high interpretation | Python `residuals.py:182`, `:217`, `:221`; `evaluation.py:47`, `:97` | Primary MSE targets raw stock returns; trade marks target a stock-minus-factors portfolio. The forecast is valid for both only when future factor conditional means are set to zero. | A +1% residual forecast can exactly predict a +1% hedge return while a −10% factor return makes the stock return −9%. Raw MSE is then 0.0100 versus zero's 0.0081, even though the hedge forecast is exact. Do not call raw MSE failure a mathematical disproof of residual alpha. |
| S2 / high interpretation | Native `main.cpp:167–227`, `peer_basket.cpp:88–90`, `:119–124`; Python `residuals.py:47–125`, `graphs.py:19–47` | Native fits nonnegative simplex weights to log returns and an OU to the resulting log-price spread. Python uses MST neighbors, two unconstrained factor coefficients, simple returns and cumulative residuals. | The seven models do not test native RIE/k-NN/constrained-basket OU signals. Differences include graph, returns, hedge, calibration, gates and policy. A negative Python pilot cannot be generalized to the native engine. |
| S3 / medium implementation | Native `ou_fit.cpp:50–51`, `:81`; header `ou_fit.hpp:19` | The sample-span guard should compare half-life with `(n−1)*dt`. It instead compares physical half-life with `n−1`. | A 100-session half-life on 59 pairs fails with `dt=1` but passes with `dt=1/252`: 100/252 < 59. Correct comparison rejects 100/252 > 59/252. Default app `dt=1` is unaffected; this cannot explain the Python results. |
| S4 / high duration semantics | Native `main.cpp:447–477`, `:538–552` | Duration named `duration_days` should preserve the chosen session/calendar axis. The app appends only successful z-score rows, then writes the difference of indices in that compressed list. | If valid rows occur at session indices 0, 3 and 5, an excursion from the first to last row is reported as 2 rather than 5 sessions. Missing/invalid-fit periods disappear. Requires preserving the session axis and censoring/handling gaps explicitly. No assertion is made here about frequency in actual data. |
| S5 / medium time-series assumption | Native `main.cpp:162–172`, `:212`, `:426–430` | `fit_ou` requires evenly spaced observations. The app builds dates from each target's available positive prices and always passes `dt=1`. | Missing target sessions can make consecutive observations span unequal numbers of sessions. A two-session move is treated as one. This is conditional on gaps; the audit did not enumerate the native dataset. Python retains missing cells within its panel, but the exchange-completeness of that panel is explicitly unverified. |
| S6 / medium benchmark interpretation | Python `risk.py:31–39`, `:124`, `:139–142` | The one-factor estimator uses the very equal-weight book being scored as its factor, then discards off-diagonal residual covariances. | For this book its variance equals the sample book variance **plus** a nonnegative residual-diagonal term. Better QLIKE can reflect mechanical upward adjustment rather than independently identified factors. Tiny oracle below derives and checks the exact identity. This is a covariance-model assumption, not an algebraic implementation mistake. |
| S7 / medium inference | Python `residuals.py:116–124`; native `ou_fit.cpp:42–87` | A fitted coefficient in `(0,1)` and a reversion-time cap are parameter screens, not proof that the underlying spread is stationary. | A finite random-walk sample can pass these screens. No unit-root/cointegration rejection, parameter stability result, or corrected post-selection inference is produced here. Calling accepted fits “proven mean reverting” would overstate the evidence. |
| S8 / low documentation | Python `risk.py:3–4` versus `:154`; `evaluation.py:143` | Squaring a variance forecast error gives fractional-return fourth-power units. | The module opening docstring incorrectly gives MSE the variance unit. Rows and final report carry the correct fourth-power unit. Numeric scores are unaffected. |

### Native excursions are not fixed-basket profit labels

`main.cpp:383–396` already explains that daily refitted spreads cannot be differenced as held-position P&L. The same care is needed for z-score excursions: `:476–477` collects z values from changing baskets and fitted equilibria; `excursion.cpp:29–44` detects absolute-band reentry. A constant spread of 0.02 has z=2 when its fitted mean is 0 and stationary standard deviation is 0.01, then z=0 when a refit moves the mean to 0.02. A “reverted” label can therefore occur with no fixed-basket price convergence. This is a valid description of a changing model's signal surface; it is not automatically the economic outcome of an entry trade. Directionless absolute-band excursions also differ from directional long/short exit rules.

## Independent equation derivation

For evenly spaced observations, write `X[t+1] = c + phi*X[t] + epsilon[t+1]`, with innovation variance `v`. The exact discretization of `dX = theta*(mu−X)dt + sigma*dW` implies:

```
phi = exp(−theta*dt)
c = mu*(1−phi)
v = sigma²*(1−phi²)/(2*theta)
theta = −log(phi)/dt
mu = c/(1−phi)
sigma² = v*2*theta/(1−phi²)
stationary_sd = sqrt(v/(1−phi²))
half_life = log(2)/theta
z = (X−mu)/stationary_sd
```

These match native `ou_fit.cpp:39–40`, `:50–51`, `:90–113`. Positive z means the spread is above its fitted equilibrium: pure mean reversion predicts a short spread. Negative phi may define a stationary discrete AR(1) when its absolute value is below one, but cannot be an exact sample of this scalar continuous OU. Native rejection of negative phi is therefore correct for its stated OU model.

The native variance `SSE/(n−1)` is the conditional Gaussian likelihood variance. Calling the regression a Gaussian MLE is precise when conditioning on the first observation; stationary-initial-state likelihood includes another term. Python `_ar1` uses the sample variance of innovations with `ddof=1`, which is neither the native likelihood convention nor the standard two-parameter regression residual variance `SSE/(number_of_pairs−2)`. That difference affects its reported innovation variance, but the Python forecast, tau gate and sign policy do not use this variance. It does not explain those forecast results.

For the Python factor regression, let `r_i = alpha + beta_M*M + beta_P*P + epsilon`. Both factor portfolios exclude the target. Defining signed security weights as in `residuals.py:101–104` gives the exact daily identity:

```
w_i = 1
w_j = −beta_M/(N−1) − I(j in peers)*beta_P/K
w' r = r_i − beta_M*M − beta_P*P = alpha + epsilon
X_t = sum(calibration epsilon)
E[X_(t+h)−X_t] = (phi^h−1)*(X_t−mu)
E[sum future hedged returns] = h*alpha + (phi^h−1)*(X_t−mu)
```

There is no missing minus sign or duplicated alpha. Subtracting alpha when constructing state and restoring it in the hedged return forecast is consistent. Unhedged stock forecasts additionally require `beta_M*E[sum M] + beta_P*E[sum P]`. The configuration sets these expected factor returns to zero. Hedged exposures are not necessarily dollar neutral: total net weight is `1−beta_M−beta_P`. Formation residual orthogonality is not a guarantee of future neutrality or stable hedge coefficients.

### Formation, calibration and endpoint pinning

For a forecast on session t, Python formation is `[t−185,t−60]` (126 sessions), calibration is `[t−59,t]` (60 sessions), and the first scored return is t+1. The slices at `residuals.py:157–159` implement this correctly. Graph, hedge coefficients and alpha use formation; state dynamics use calibration. The newest observation can inform the forecast for the next session without future-return leakage. This remains an assumed post-close clock, not evidence of an executable same-close fill.

Because calibration residuals are evaluated using earlier coefficients, their sum is not forced to zero. The prepended `X_0=0` sets an origin; an intercept-bearing AR(1) and `X−mu` are invariant to constant shifts. This is not endpoint pinning. By contrast, same-sample OLS with an intercept makes the sum of its fitted residuals zero, which constrains a cumulative path's terminal level. Neither operation itself establishes genuine stationarity.

Python's `tau=−1/log(phi)` is the characteristic reversion time, not the half-life. Its `tau<=30` implies `half_life<=30*log(2)=20.794` sessions. Native's default 60-level fit instead accepts half-life up to 59 sessions. The gates are materially different.

### Original-paper comparison

The original Avellaneda–Lee paper models cumulative factor-residual states, uses stock/factor hedges, and distinguishes characteristic reversion time from the s-score. Its appendix explicitly acknowledges a zero terminal cumulative residual caused by same-sample regression, and mentions using different estimation windows. Its trading rules have threshold entries and persistent positions. The Python diagnostic borrows this state idea while changing factors, windows and policy; native uses a constrained log-price basket. Neither implementation is a complete reproduction. [Author-hosted paper, sections 3–4 and appendix](https://math.nyu.edu/inmemoriam/avellaneda/AvellanedaLeeStatArb20090616.pdf).

## Units, normalization and cost accounting

Native log prices and spread are dimensionless, although each price starts in currency per share. The hedge weights sum to one, so a common currency-scale factor cancels. Rescaling an individual security shifts the spread and its fitted mean by the same constant for a fixed basket, leaving z unchanged. A fixed-weight log-spread change is exactly the corresponding weighted log-return difference; it is not exactly finite-interval account P&L of dollar legs. Dollar P&L needs fractional price changes, holdings and a capital denominator.

Python state sums fractional daily residual returns. For one session, these are the matching fractional-return hedge marks. Over several sessions they represent an additive constant-notional diagnostic, not buy-and-hold or compounded returns. Example: +10%, then −10%, sums to zero but compounds to −1%; the log change is `log(0.99)`. This distinction is correctly declared in the configuration.

For a one-day weight vector w, `G=sum(abs(w))` is gross exposure per unit target notional. `evaluation.py:93–103` uses `sign(forecast)*(w' r)/G`. A hypothetical weight vector `[1,−2]` has gross 3, so a 0.03 unnormalized hedge mark becomes 0.01 per unit gross. Charging `2*bps/10000` is consistent with an assumed complete entry and exit of that gross-one basket at the same one-way rate. It is not a factor-of-two cost bug.

Those marks are not one consolidated portfolio. They omit cross-basket netting, persistent positions, realized changing exit notionals, short inventory, financing and impact. Controls `historical_mean` and `own_return_ar1` trade raw single stocks; state models trade hedges. Equal gross does not equal market exposure, volatility or capacity. Thus their mean cost marks are not a controlled estimate of incremental graph alpha. The experiment's policy also trades every nonzero forecast, however small. Native thresholds and holding periods are untested here.

The secondary risk allocation code correctly uses the full L1 security trade volume, including both purchases and sales, with initial and terminal charges. It drifts weights between weekly decisions. It records an additive mark proxy rather than a complete cash account with cost-adjusted holdings. These limitations are already identified in its output.

## Risk-control algebra and tree interpretation

Let centered returns be the matrix R, equal weights be e, and factor `f=R e`. In the active branch `factor_variance > VARIANCE_FLOOR`, OLS slopes satisfy `e' beta=1`. Residuals `U=R−f beta'` therefore satisfy `U e=0`: their portfolio sum vanishes. Keeping the complete residual covariance would exactly recover the sample covariance. The zero-variance fallback sets beta to zero and does not obey this identity; it is not the branch used in the saved equity diagnostic.

The implementation instead returns `Var(f)*beta beta' + diag(Var(U_j))`. For the tested equal book:

```
e' Sigma_one_factor e
  = Var(f) + sum_j Var(U_j)/N²
  >= e' Sigma_sample e.
```

This explains the compact artifact means: sample predicts 0.000117344 and one-factor 0.000135961, an average increase of 0.000018617 (about 15.87%). The realized squared-return average is 0.000117665. QLIKE ranks the one-factor model slightly better anyway because QLIKE is a datewise, nonlinear loss that penalizes low forecasts during large moves. Comparing average variances alone cannot reconstruct QLIKE or establish which estimator is best.

The tree covariance at `graphs.py:50–68` retains diagonal variances and multiplies signed edge correlations along paths. It defines a coherent Gaussian tree covariance when edge correlations have magnitude below one. In a three-node chain with edge correlations 0.8 and 0.7, the endpoint correlation is forced to 0.56; a sample value 0.50 is changed by construction. The method is explicitly neither native RIE nor LoGo. Edges maximize signed correlation, not absolute correlation or Gaussian mutual information. This is a chosen graph prior; it can be mathematically valid and empirically worse.

The risk target `(e' r_next)^2` is a second-moment observation. A demeaned covariance forecasts variance. Treating the former as a variance proxy assumes negligible conditional mean, otherwise the conditional mean squared must also be accounted for. All estimators share this target assumption.

## What survives in the saved results

Source artifacts: `residual_report.json`, `residual_cost_report.json`, `risk_report.json`, all under `artifacts/lattice-strategies/reports-v1`.

| Saved observation | Correct conclusion |
|---|---|
| One-day common cohort: 6,012 stock-date opportunities, 501 dates. Zero MSE 0.000370885; MST 0.000382134. | This exact MST raw-stock forecast loses 3.033% versus zero on reused 2024–2025 outcomes. |
| MST versus zero MSE improvement −0.0000112493; exploratory 95% block interval [−0.0000167819, −0.0000059094]. | The registered date-block resampling supports a loss in this sample under its assumptions. It is not a permutation test, untouched holdout or adjustment for model selection. |
| MST versus market-only raw MSE improvement 0.148%; interval spans zero. | No clear incremental peer benefit under this metric. It does not isolate the native graph or net hedged alpha. |
| MST daily hedge mark −0.910 bp/opportunity before costs; −2.428 at 1 bp each way; −8.498 at 5 bp each way. | The particular daily sign/roundtrip policy offers no positive observed mean even before costs. The report has no uncertainty interval for this mean; do not infer statistical significance. |
| Tree QLIKE −8.02021; sample −8.02958; Ledoit–Wolf −8.00918; one-factor −8.05512. Lower is better. | Tree ranks between these controls; tree comparisons with each of sample/LW/one-factor have intervals crossing zero. A general claim of tree superiority or inferiority is unsupported. |
| Same opportunity counts but state abstentions around 24%; different raw versus hedged exposure for controls. | Forecast cohort fairness is explicit, while trading exposures and risk are not matched. Both qualifications must remain visible. |

Mechanisms consistent with weakness include estimating extra hedge/state parameters, 60-session-stale hedge formation, global MST connectivity admitting weak local substitutes, enforcing a stationary state where the process may not be stationary, zero factor forecasts, and forcing daily trading of tiny signals. They are hypotheses, not causal explanations established by these artifacts. The latest run contains no matched ablations that separately identify their contributions.

The seven models do **not** test native peer-weight optimization, native OU thresholds/holding rules, RIE versus sample covariance, k-NN versus MST with identical downstream logic, a common-hedge comparison of alpha forecasts, portfolio netting, futures dollar hedges/rolls/margin, options volatility/surface forecasts, business/news exposures, or a fresh untouched holdout. The actual universe is 12 US equities: AAPL, MSFT, AMZN, GOOGL, META, NVDA, JPM, BAC, XOM, CVX, UNH, GD. Asset classes must not be added to the visual merely because the repository contains them elsewhere.

No Sharpe ratio is claimed here. A future performance claim requires an appropriate cost-bearing portfolio, out-of-sample validation, dependence-aware confidence intervals and permutation-based inference before trusting p-values.

## Flow annotations for the graph visualization

| Node | Input → output and units | Interpretation / branch |
|---|---|---|
| Prices | Native Yahoo adjusted close, currency/share | Historical identity, adjustment and receipt vintages not qualified by this pilot. |
| Native basket | Log-return target/neighbors → nonnegative weights summing to one | Return tracking with ridge; fixed target 1, peer short total 1. |
| Native spread | Log prices + weights → log spread | Relative valuation, not account equity. |
| Native OU | Prior spread levels → theta, mu, sigma, half-life | 1/session, log spread, log spread/sqrt(session), sessions. |
| Native score | Current spread + prior OU → z | Dimensionless; positive suggests short for pure reversion. |
| Native excursion | Sequence of daily refitted z → band-return labels | Changing-model signal behavior; compressed duration concern. |
| Python returns | Adjusted closes → simple fractional returns | Shared 12-equity input for signal and risk branches. |
| Formation graph | Earlier 126-session residual correlation → peer sets | MST versus same-degree top correlation or normalized-price distance. |
| Python hedge | Market and peer means → alpha, beta_M, beta_P, signed weights | Alpha fraction/session; betas dimensionless; target excluded from factor holdings. |
| Calibration state | Later 60-session residual increments → X | Additive fractional-return state; terminal value not forced to zero. |
| State AR(1) | X → phi, equilibrium, tau | Dimensionless phi; additive fraction equilibrium; tau in sessions. |
| Forecast | State + dynamics → h*alpha + expected state change | Additive hedged return expectation; raw stock interpretation assumes zero factors. |
| Forecast score | Forecast versus raw stock future sum → MSE/MAE | Prediction branch; retain zero forecasts for no-trades. |
| Hedge marks | Forecast sign + signed weights + future returns → gross-one mark | Separate daily policy/cost branch, not native threshold trading. |
| Covariance | Same trailing 126 raw-return sessions → Sigma | Fractional-return squared per session. |
| Fixed-book risk | Sigma and equal weights → variance, QLIKE/MSE | Same book across estimators; covariance MSE has fourth-power units. |
| Allocation | Covariance → weekly capped long-only weights → drifted marks | Secondary policy branch; does not validate residual alpha. |

## Verification boundaries

`tests/audit/test_signal_math.py` contains eight small synthetic oracles: exact OU mapping; the native time-unit guard counterexample; disjoint calibration and hedge identity; raw-stock/hedge target divergence; gross normalization and two-way cost; additive versus compounded returns; one-factor equal-book inflation; coherent tree covariance with changed nonedges. It does not invoke the native C++ binary or use market data. Native source defects are established by source and algebra; a compiled native witness remains a separate verification step.

No production fix, parameter tuning, market-data read, remote backtest or package installation was performed in this audit.
