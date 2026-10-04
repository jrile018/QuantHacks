# Does the prediction-market benchmark idea deserve implementation?

Evidence checked October 3, 2026. FDS means **financial data sheets**. Scope: whether Polymarket/Kalshi information adds value to this project's company benchmark, pre-disclosure forecasts and after-cost options/risk decisions.

**Follow-up:** [Detailed strategy validation research](strategy-validation-research-2026-10-03.md) and [the shared implementation plan](superpowers/plans/2026-10-03-strategy-validation.md) add matched base-rate comparisons, event clocks, independent-event inference and executable portfolio tests. The March earnings PDF was previously accessible/indexed; its direct URL now returns 404. Its reported figures remain March-version evidence, not verified estimates from the later August revision.

## Verdict

**Conditional yes for a small expectations-check experiment. Unproven for trading.** The literature supports information content in particular earnings and macro contracts. It does not establish that these sources verify company financial condition, predict the economic quality of an entire 8-K, or improve this project's after-cost options results.

This is a literature and design audit. No paired FDS/prediction-market/options backtest was run, and no incremental performance has been measured for QuantHaxs. The implementation recommendation is now a coverage audit, readable company expectations cards and permission-cleared shadow collection. Integration into position decisions requires new evidence.

## What the primary research actually supports

| Evidence | Verified result and scope | Consequence for our design |
| --- | --- | --- |
| [Gómez-Cram, Guo, Jensen and Kung, Financial Prediction Markets — accessible March 7, 2026 version](https://www.hhs.se/contentassets/fa9e2f0927584e4c8ba7b098a98ccf2a/financial_prediction_markets.pdf) | Its two-month earnings sample reports announcement-return R² rising from 0.036 with analyst surprise to 0.058 with prediction-market surprise added. Market changes predict later analyst revisions. These are explanatory return tests, not an executable options strategy. | Supports testing an extra earnings-expectations input. Announcement surprise uses realized earnings, so these regressions cannot be presented as pre-release trading performance. |
| [Li and Luan, What Moves Prediction Markets? Evidence from Corporate Earnings, SSRN 7324239](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7324239) | The September 2026 abstract reports 599 Polymarket earnings events: stock returns predict subsequent market-price changes over 1 hour–1 day, while prediction-market changes do not predict stock returns. The full paper was not accessible for independent numerical verification. | A serious reason to test redundancy with stock/options inputs. Odds can follow already priced news. |
| [Diercks, Katz and Wright, Kalshi and the Rise of Macro Markets, February 2026](https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf) | The working paper finds macro forecasts broadly comparable to professional benchmarks, with some headline-CPI improvements. Tables 3 and the calibration tests show performance varies by variable and measure; this is macro forecasting, not REIT/options P&L. | Supports a rate/regime context experiment. It does not convert macro probabilities into issuer-specific disclosure odds. |
| [Bürgi, Deng and Whelan, Makers and Takers, CESifo working paper 12122](https://doi.org/10.65864/s9kc4p0b7t) | Over 300,000 contracts show informative prices with favorite–longshot bias and distinct maker/taker behavior. Broad-platform calibration is not guaranteed for a specific event family. | Preserve quote sides and assess calibration at the actual horizon/category. Never equate a displayed price with a verified probability. |

These are working papers, not a settled general result. For Gómez-Cram et al., [SSRN lists an August 30 revision](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5933475), whose full updated text was not retrieved. The sample and numerical figures above are confirmed only for the accessible March version; they are not described as the latest estimates.

The two earnings papers can coexist: a prediction market may precede slow analyst revisions while following stock prices. The first study's lead/lag comparison is against analysts; the second is against equity prices. This distinction weakens an inference that prediction-market odds necessarily reveal news before the equity market has priced it.

## Claims that pass or fail the proof check

| Proposed claim | Assessment |
| --- | --- |
| A precise earnings-event contract can supply a useful outside expectation | Supported enough to test; conditional on rules, quality, timing and coverage |
| Prediction markets independently confirm the company's financial health | Unsupported: they price outcomes and settlement rules, not audited balance sheets |
| An 80% YES price means an 80% chance that the whole 8-K is good | Invalid mapping unless a specific, reviewed outcome is defined; even then calibration is required |
| Adding odds necessarily improves our existing FDS model | Unmeasured; same news can already be in stock prices, options, guidance or other features |
| Better event forecasts imply profitable call/put choices | Does not follow; magnitude, option premium, volatility, spreads, timing and losses remain |
| Existing earnings evidence establishes FDA/deal/REIT performance | Unsupported extrapolation; each track needs its own data and evaluation |

Economic inference: the most useful potential contribution is a clearer measurement of **what is already expected**, possibly at higher frequency than analyst updates. Its value is greatest when our existing sources have a measurable gap in event-specific expectations. Coverage, stale quotes, unclear rules and recurring data costs can eliminate that value.

## Keep all tracks, but evaluate their contributions separately

- **Earnings/guidance:** first direct forecasting comparison because quarterly definitions repeat. Compare exact metrics with contemporaneous analyst consensus, previous guidance, FDS and stock/options context. Exclude mere keyword contracts from the financial-outcome group.
- **FDA/deals:** audit direct product/transaction coverage and issuer exposure. Use exact decisions/deadlines and scenario valuations; do not generalize a positive approval or deal probability into a positive option-return probability. No applicable cohort coverage or incremental performance has yet been established.
- **REIT/rates:** use an issuer exposure/rate scenario card. Test additional information beyond dated macro releases and conventional rate expectations. Refinancing sensitivity belongs to verified debt/reset/maturity facts. A Fed decision remains a shared macro event, not a forecast of an individual REIT's 8-K.

Improving the FDS extraction/timing and obtaining executable paired option data remain prerequisites. This layer should not delay those foundations or receive greater priority merely because odds are easy to display.

## The empirical test that could reject the idea

1. **Define eligibility before observing results.** Fix company universe, all ordinary decision dates, precise events/horizons, contract rules and first-public-release protocol. Record no coverage explicitly. Require provider rights and contemporaneous availability; unverified historical receipts/rules cannot support an executable backtest.
2. **Build a strong baseline on the same rows.** FDS, known calendar, public news/guidance, accessible dated consensus, stock returns, option prices/IV/spreads and conventional macro expectations. Compare full-universe and identical-covered-subset results.
3. **Add odds without changing the strategy.** Freeze feature definitions and the current option selection/exit rules. Use training/validation to set calibration, spread/freshness limits and combination weights. Preserve a later holdout.
4. **Challenge incremental information.** Test both lead/lag directions. Ask whether the contribution survives contemporaneous stock/options controls and chronological event/issuer splits. Compare with block-preserving placebo features; repeated issuer observations of one macro event must remain grouped.
5. **Test the economic decision.** Measure after-cost returns, downside and capital/liquidity on the frozen strategy versus baseline and no trade. Include provider/maintenance costs when judging whether the layer is worthwhile. Forecast scores are an intermediate outcome.
6. **Decide by track.** Pre-register a minimum useful gain and power/precision target after the coverage audit, before holdout inspection. Promote a track only if uncertainty bounds support incremental forecast and economically material, risk-constrained value. Keep forecast-only benefits as research context; discontinue tracks with failed rights, insufficient usable coverage or failed increments. An inconclusive test is not a success.

The relevant proof is a repeatable improvement on **our actual, timestamped decisions** after realistic costs, not a published accuracy percentage borrowed from another domain. Current evidence warrants a bounded test and supports no promise of improved trading returns.

## Practical access gate

The API design is feasible, but Kalshi's [Developer Agreement](https://kalshi-public-docs.s3.amazonaws.com/Kalshi-Developer-Agreement.pdf) limits use/storage to members' own Kalshi trading; permission for this distinct forecasting use must be resolved. Polymarket's [institutional notice](https://institutional.polymarket.com/) requires consultation for capital-markets entities. Applicable research, ML, retention and publication rights must be recorded before ingestion. A reachable public API is not enough to proceed with the proposed use.

The implementation details, event mappings, data contracts and six delivery stages are in [the implementation plan](superpowers/plans/2026-10-03-prediction-market-benchmark.md).
