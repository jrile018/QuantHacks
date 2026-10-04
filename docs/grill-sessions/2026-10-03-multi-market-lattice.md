# Multi-market Lattice grilling record

Date: 2026-10-03. Purpose: challenge the expansion's economic roles, data assumptions and falsification rules. This is a decision record, not an accepted fitted strategy.

Method: the user requested grill-me. The [upstream grill-me alias](https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md) delegates to [grilling](https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md): map dependent decisions, ask the currently answerable frontier with recommendations, and wait for answers before the next round. The upstream files were read online because they were not installed locally.

## Established intent

- The figure is secondary; numbers used to create it may be candidate signals.
- Option A is selected: test Lattice as incremental market context rather than inheriting its existing equity rule as proven alpha.
- Equities, listed equity options and futures are in the research scope.
- Existing data informs the starting point but does not bind the eventual source scope.
- The FDS/pre-release/post-release objective from the whiteboard and tracking chat remains; forecasts and risk/hedge decisions need separate objectives.

## Round 1 — answered

1. **Decision pace:** Daily decisions with next-session outcomes. User selected the recommended answer.
2. **Futures economic role:** Both standalone profit and hedge benefit, evaluated separately. User selected the recommended answer.
3. **Stage/success:** Establish incremental historical value, then a frozen forward paper test. User selected the recommended answer.

These are user decisions, not inferred defaults. No account size, maximum drawdown, permitted short positions or exact clock is established by them.

## Round 2 — resolved by execution authorization

1. **Futures universe:** The user directed testing all proposed families, with recommendations first. Start with ES/MES (one index exposure), then Treasury rates, then energy/metals. Each product retains separate lifecycle/data gates.
2. **Numerical roles:** The user directed testing forecasts, risk/filter rules and direct signals, with recommendations first. Forecast information comes first; risk/filter and direct tests are separate registered outcomes, including failures. Futures hedging remains a separate comparison.

The same message authorizes thoroughly evaluating valuable extensions beyond the repository's current implementation. See [extension research](../research/2026-10-03-lattice-extensions.md), [execution record](../research/2026-10-03-multi-market-execution-status.md) and the versioned research config at `configs/experiments/multi-market-v1.json`. Ordinary research defaults are recorded there; missing economic prerequisites stay explicit.

## Conditional later frontier

- Exact daily decision/entry/exit, product-session calendars and initial eligible equity/option cohort; integrate the event-family answer from Post Benchmark without asking the user to repeat settled choices.
- Permissible exposures/shorting, analytical account capital and maximum acceptable loss/drawdown. Personal account details remain local.
- A specific economic mechanism for standalone futures alpha. Aggregate index market state, rate surprises and commodity supply/demand are different mechanisms; issuer 8-K polarity is not a universal futures target.
- Minimum useful gain and uncertainty needed to keep the Lattice feature; strong ordinary volatility/correlation/sector-peer substitutes.
- Data-missingness abstention, liquidity limits and fallback. A missing option should not make the system silently select a different winning instrument.
- A stopping rule: when to reject a candidate, when evidence is inconclusive, and how many additional registered variants are affordable before search becomes uninformative.

## Skeptical review incorporated

1. H1 failed a correlation-distance peer-basket reversion test. MDS did not participate in that signal path; other output families remain untested.
2. The current geometry uses raw adjusted-close returns, not a stored factor-residual return panel. Proposed residual/eigenvalue scalar exports are new work.
3. Duplicating one underlying through shares, options and index futures does not create independent alpha or diversification.
4. Continuous futures roll gaps, collateral-based return denominators, source revisions and session mismatches can manufacture an edge.
5. Compare identical dated decisions, quote/cost assumptions and exposure. Test each numerical family against its simple substitute.
6. OCR/wording, event occurrence, repricing, trade P&L and hedge protection have separate truth standards.
7. Independent draft review preserved the primary-test frontier rather than requiring forecast improvement before the user's choice. It added executable quote-size/nonfill rules, reconciliation against variation-margin double counting, and explicit dependence-preserving inference and daily-account Sharpe reporting. All four material findings were incorporated. The later execution instruction resolved round 2 as all families/all roles, recommendations first.

Linked [research design](../research/2026-10-03-multi-market-lattice-design.md) and [implementation research plan](../superpowers/plans/2026-10-03-multi-market-lattice-research.md). Recompute the frontier after answers; no implementation of unanswered branches is implied by this document.
