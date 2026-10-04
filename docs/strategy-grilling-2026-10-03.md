# QuantHaxs strategy grilling — October 3, 2026

**Purpose:** resolve the trading mandate and economic mechanism through skeptical questions. Research facts are in docs/strategy-research-review-2026-10-03.md. This file records decisions and unresolved branches; it is not an approved trading specification.

## Already established by the user

- FDS means financial data sheets.
- EDGAR plus collected general APIs and industry-specific URLs inform the company benchmark.
- Prior public information and regime changes should inform expectations before disclosure, followed by a public-information update and risk/liquidity/capital decisions.
- Earnings/guidance, FDA/deals and REIT/rates remain in the prediction-market review scope.
- The whiteboard's industry examples are illustrative references to prior research, not user-selected priorities.
- The user requests a critical review, including the possibility that the idea is bad, and a grilling interview.
- The downstream objective is now net portfolio growth within hard risk limits. The user requests both risk gating/sizing/caps and automatic strategy-switching research, with risk profiles compared across asset universes. Numeric capital limits and live instrument permissions remain unresolved.

## Decision tree

1. **Mandate / success**
   - Research validation, prospective paper system, or intended capital deployment?
   - Then: which economic benefit and baseline must it exceed?
   - Then: what evidence would make the user abandon or redesign it?
2. **Risk envelope**
   - Capital range, tolerable drawdown, overnight permission, short-option permission?
   - Then: eligible structures, collateral, stress loss and aggregate exposure.
   - Then: exit triggers, quote-side implementation, gaps and assignment.
3. **Economic mechanism**
   - Superior public forecast, slower interpretation of novel facts, option mispricing, or a combination?
   - Then: exact event family, information advantage and alternative explanation.
   - Then: no-event risk set for anticipation or post-processing timing for response.
4. **Trade specification**
   - Conditional on mandate/mechanism/risk: exact contracts, horizon, entry rule and exit policy.
   - Then: portfolio overlap, liquidity, abstention and fallback behavior.
5. **Falsification**
   - Conditional on above: minimum useful gain, trial ledger, chronological evaluation, precision, prospective protocol.
   - Then: promote, discontinue or remain inconclusive.

## Round 1 — questions already sent

**Q1. Intended success/stage:** Is the immediate goal proving the edge, building a paper system, or preparing for real capital soon?
**Recommendation:** a frozen forward paper test before funding.
**Trade-off:** slower capital deployment in exchange for observable latency, selection and execution evidence.
**Answer:** historical validation followed by frozen forward paper, recovered from the Lattice chat in [cross-chat context](research/2026-10-03-cross-chat-scope-and-cross-asset-integration.md). The later regime/risk interview confirms net growth within hard risk limits as the objective. No capital-deployment mandate follows.

**Q2. Risk envelope:** What capital range and maximum acceptable drawdown apply, and are selling options and overnight holds allowed?
**Recommendation:** establish these constraints before selecting contracts, leverage or stops.
**Trade-off:** narrower trade choices in exchange for a strategy whose losses and capital requirements match its purpose.
**Answer:** the user asks to compare risk profiles, especially across different asset universes. Research will compare profiles; numeric caps and overnight/leverage/short permissions are still unresolved. Keep personal account details local; do not publish them in the public discussion.

## Current downstream interview

Continue with [regime and risk grilling](grill-sessions/2026-10-03-regime-risk-layer.md) and its [research work plan](research/2026-10-03-regime-risk-and-signal-optimization.md). Objective, authority and profile-comparison scope are settled; zero allocation, switching falsification and later clock/limit decisions retain their actual answer status.

## Facts looked up instead of asking the user

The current implemented sample is CFO appointments with 34 events and descriptive mark outcomes. First-public disclosure timing, full-company risk-set forecasting and executable portfolio evidence are incomplete. The broad FDS/pre/post objective is already recorded. The user does not need to answer questions about file contents or whether saved jobs/model results exist.

## Next questions once their prerequisites are resolved

- If trading profit is the goal: **what specific public fact can this system interpret or forecast better than the market, and why should the difference persist?** Recommendation: choose one falsifiable, event-specific mechanism and compare with a strong prices-plus-expectations baseline.
- If portfolio insurance is the goal: **what loss is being hedged, over what horizon, and what premium is worth paying?** Recommendation: evaluate protection and insurance cost rather than calling every negative hedge return a failed strategy.
- Once risk and mechanism are set: **what is the actual primary position and feasible entry/exit policy?** Recommendation: freeze one primary policy while keeping alternatives as logged challengers.
- Once a primary experiment is defined: **what evidence would make you stop?** Recommendation: reject leakage-dependent or non-executable results, and require informative net-benefit uncertainty rather than a selected positive average.

Ask only the current decision frontier; questions depending on unresolved earlier choices wait. Record each answer and recompute the tree. No implementation or trading decisions are taken from unanswered questions.
