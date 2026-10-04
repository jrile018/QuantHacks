# REIT arbitrage and repricing: economic grill

**Evidence date: October 3, 2026.** Planning research only; no collection, backtest, fit, purchase or trade. Reviewed [strategy assessment](strategy-research-review-2026-10-03.md) and [REIT draft](superpowers/plans/2026-10-03-reit-scale-parallel-plan.md). Scope supplied by the coordinator: validated US listed REITs, January 2024 onward, typed financing/company relationships including non-REIT counterparties. Numerical examples below are hypothetical, not estimated project performance.

## 1. Economic definitions and measurable gates

**Pricing arbitrage:** an executable self-financing portfolio whose net initial outlay is nonpositive and whose terminal net value is nonnegative in every admissible market/exercise state, with a strict benefit initially or positive-probability terminal gain under the stated model, subject to attainable financing, borrow and intermediate cash requirements. An apparent pricing discrepancy is only a candidate until those conditions hold. For European same-strike/expiry options with known cash dividends and frictionless identical funding, `C − P = S − PV(dividends) − K exp(−rT)`. Test executable inequality bounds with separate borrowing/lending rates and quote sides. American exercise, uncertain dividends, stock borrow and transaction costs invalidate a naive equality screen. [OIC parity explanation](https://www.optionseducation.org/advancedconcepts/put-call-parity).

**Expected repricing:** a forecast that new financing facts or counterparty exposures predict returns after feasible processing and entry. A hedge can reduce systematic exposure while leaving issuer, jump, basis and estimation risk. Measure net excess returns against dated price/factor baselines, incremental forecast calibration, uncertainty and account drawdowns. A positive mean is evidence to evaluate; it is not a guaranteed payoff.

Keep separate reports. Arbitrage reports need candidate frequency, synchronized executable depth, confirmed borrow, fill/partial-fill rate, conservative payoff lower bound, capital occupancy, funding/assignment failure and realized reconciliation. Repricing reports need net account returns, factor attribution, calibration, turnover, event/issuer/date concentration, confidence intervals and ablations. Repeated contracts/horizons from one episode are dependent observations.

For document/network forecasts, map facts into cash flows first: annual floating-interest change is approximately `exposed principal × rate change`, subject to reset dates, caps and hedges; credit-loss scenarios use `exposure at default × default probability × loss given default`. Loan proceeds exchange cash for a liability and are not profit. Equity sensitivity must include asset/debt valuation, dilution, taxes and refinancing terms. Typed edges require contractual exposure and dated evidence; a shared lender or counterparty name alone establishes neither transmission direction nor materiality. Graph versions used at a decision must contain only relationships disclosed by then. These are proposed accounting/scenario approximations, not estimated predictive effects.

Futures qualify only when exposure matches their economic underlying. Treasury hedges should match measured yield sensitivity/DV01 rather than dollar notional; REIT equity requires an empirically justified sensitivity, not its disclosed debt principal alone. Sector futures reduce sector exposure, without exactly replicating a particular REIT. Confirm historical contract availability and executable liquidity. [CME DV01](https://www.cmegroup.com/trading/interest-rates/calculating-the-dollar-value-of-a-basis-point.html), [sector contracts](https://www.cmegroup.com/markets/equities/select-sectors.html).

## 2. Bounded, mechanism-led horizon grid

Start with these research candidates; hold period and option expiry are distinct. Avoid their unrestricted Cartesian product.

| Mechanism | Candidate outcome horizons | Reason and falsifier |
|---|---|---|
| Executable parity/replication discrepancy | Immediate completion; hold to contractual settlement only if financing survives | Mispricing must clear costs now; a later favorable move cannot rescue the arbitrage claim |
| New financing/amendment surprise | 30 minutes, next session, 5 sessions after feasible entry | Information absorption; reject if movement precedes usable evidence |
| Counterparty credit/refinancing transmission | 1, 5, 21 sessions | Propagation and cash-flow revision; reject if simple price/sector controls explain it |
| Maturity/covenant exposure repricing | 5, 21, 63 sessions | Slower reassessment; higher carry and unrelated-news exposure |

Use an intraday candidate only with historical publication/processing clocks and synchronized quotes. Longer exposure requires option expiry beyond planned exit and explicit expiry/exercise handling. Select one primary horizon per mechanism inside training; label other horizons diagnostic and register them as trials. Retain scheduled, unscheduled pre-event and post-disclosure decisions as separate risk sets, including no-event periods. These horizons are economic hypotheses, not published estimates of REIT reaction speed.

## 3. Chronological validation and contamination controls

1. Create expanding chronological outer folds, for example quarterly deployment windows after an adequate initial training period. Within each outer training set, use earlier-to-later inner folds to select features, model, horizon, instrument, hedge and sizing. Fit normalization and imputation there too. Freeze the selected pipeline before predicting the outer window.
2. At each training cutoff, admit only labels whose entire outcome interval and availability time have finished. Purge observations whose feature/outcome information intervals overlap the evaluation interval. Apply a documented boundary gap/embargo derived from actual maximum label span and information dependencies. Never admit future observations to a past-only deployment fold; an embargo cannot legitimize them.
3. Group repeated filing/instrument events and issuer episodes; evaluate calendar-block and issuer dependence. Add a held-out-issuer test for portability separately from chronological deployment. Report effective episode counts and uncertainty; short 2024-onward history may be inconclusive.
4. Register every tried/abandoned mechanism, feature, prompt, horizon, exit, cost and risk variant. Predeclare primary comparisons; use dependence-aware multiple-comparison adjustment and a Deflated Sharpe/PBO diagnostic where applicable. PBO/CSCV is a diagnostic, not a substitute for chronological deployment. [Deflated Sharpe original paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf), [PBO original paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
5. Audit inspected 2026 issuers, filings, examples and outcomes before calling any historical period untouched. Current membership, retrospectively corrected relationships, latest filings and later model weights are additional contamination paths. Preserve an independently controlled final historical holdout only if that audit supports it; otherwise lock a prospective holdout after the plan/model freeze. Do not retune after seeing final results: changes start a new trial and new future evaluation.

Controls reduce identifiable bias; they cannot guarantee bias-free research or profitable deployment. A final holdout complements the trial register and uncertainty analysis. The paper itself explains why researcher familiarity and repeated trials undermine holdout-only claims. [PBO discussion](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## 4. Costs, position limits and capital mathematics

For a long option closed before exercise, `net P&L = multiplier × quantity × (exit bid − entry ask) − fees − extra impact`. Quote-side spread is already counted. For a short stock leg, include daily borrow on lender collateral, dividend compensation, funding, commissions and impact, less actually available proceeds interest. Historical borrow availability and changing rates must be observed or clearly bounded; present availability proves nothing about 2024. [IBKR borrow costs](https://investors.interactivebrokers.com/en/pricing/short-sale-cost.php?menu=A), [availability](https://www.interactivebrokers.com/en/trading/securities-financing.php).

Break-even is an economic threshold: `expected gross P&L > all incremental costs + estimation/risk allowance`. Hypothetically, a 21-calendar-day short with 15 basis points execution cost and 10% annual borrow on assumed notional collateral needs more than `15 + 10,000 × .10 × 21/365 = 72.5 bp`, before dividends/funding. Actual collateral conventions and day count replace these assumptions.

For one exposure, a screening bound is

`q ≤ min(floor(loss budget / stressed loss per unit), floor(free equity / initial margin per unit), executable liquidity capacity, borrow capacity)`.

This is insufficient for a portfolio: for every retained stress path `s`, enforce `equity_s(q) − maintenance_margin_s(q) ≥ cash buffer`, plus settlement/assignment cash availability and concentration/Greek/exchange limits. Use one overlapping-position ledger, including restricted short proceeds. Margin is collateral capacity, not an additional trading expense or a loss cap.

Reference US requirements: FINRA ordinarily requires at least $2,000 initial equity; long maintenance is 25%; stock shorts priced at least $5 require the greater of $5/share or 30% of market value. House requirements can be higher. Typical Reg T stock initial equity is 50%; obtain dated account-specific schedules. [FINRA 4210](https://www.finra.org/rules-guidance/rulebooks/finra-rules/4210), [IBKR explanation](https://investors.interactivebrokers.com/en/trading/margin-infographic.php).

Example: short 100 shares at $50, using simplified 50% initial equity: $2,500. At $100, loss is $5,000 and 30% maintenance is $3,000. At least $8,000 initial account equity would be needed to remain compliant at that state, before costs/buffers. Neither the initial requirement nor this single stress caps short-sale loss.

A standard 100-share $50/$45 short put spread receiving $1 has $400 maximum terminal contractual loss. Assignment on the $50 short put can nevertheless create a $5,000 stock purchase while the long put remains open; model timing and broker handling. Long puts/calls cap premium loss only while held as options. Covered calls retain stock downside; naked short calls have unbounded upside loss. American assignment can affect one leg independently. [OIC assignment](https://www.optionseducation.org/referencelibrary/faq/options-assignment), [exercise](https://www.optionseducation.org/optionsoverview/exercising-options).

## 5. Optimize a feasible frontier, not the user's preferences

Evaluate account-size breakpoints from indivisible lots, fixed costs, diversification, house margin and liquidity capacity. A bounded illustrative research grid is $5k/$25k/$100k/$150k/$250k, with explicit infeasibility states, not recommended deposits. IBKR currently describes $110k portfolio-margin entry and restrictions below $100k; this is broker/account-specific and is not a historical assumption. [Broker eligibility](https://www.interactivebrokers.com/en/trading/margin-stocks.php?ex=us&hm=us&pm=1&rgt=1&rsk=0&rst=101004100808).

Within training, compare constrained expected log growth or `E[net return] − λ × tail loss`, with uncertainty shrinkage, no-trade allowed and hard feasibility gates. Log growth is a utility choice, not an objective truth. Volatility targeting `leverage = target volatility / estimated volatility`, capped by stress/margin/liquidity, is a comparator; it can increase exposure before a gap and ignores some option nonlinearities. [Kelly original paper](https://doi.org/10.1002/j.1538-7305.1956.tb03809.x).

Report net-return/expected-shortfall/drawdown/capacity frontiers. Stress issuer gaps, joint REIT/credit shocks, IV/skew changes, dividend surprise, borrow recall, partial fills, halts, margin increases and futures cash calls; rerun full nonlinear paths. Historical drawdown is a sample outcome, not a guaranteed future bound. Futures settlement variation requires cash during the holding period. [CME settlement](https://www.cmegroup.com/education/courses/introduction-to-futures/mark-to-market).

## 6. Recorded grill and revisions

Applied the remotely published [grilling instructions](https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md): prerequisites define the decision frontier; facts are researched; human decisions remain unresolved. This is a recorded challenge/revision audit, not a private reasoning transcript or completed human interview.

| Frontier challenge | Evidence/rationale | Revision |
|---|---|---|
| Can every hedged profit be called arbitrage? | Basis/exercise/funding risks remain | Separate payoff-bound and forecast-alpha gates |
| Can “test everything” identify unbiased winners? | Trial selection and correlated variants inflate evidence | Bounded mechanism grid, nested selection, full trial register |
| Is 2026 automatically independent? | Current review already uses 2026 examples | Contamination audit; prospective holdout where needed |
| Can optimization choose acceptable losses? | Utility and loss-bearing capacity are external constraints | Report Pareto frontier; never infer tolerance from best backtest |

**Human frontier:** deployment stage/permissions, actual capital available, permissible cash depletion/loss and utility tradeoffs. Research should first produce feasible alternatives and measured risks; those decisions then determine a deployable mandate. No numeric profitability, optimal account size or acceptable drawdown is established today.
