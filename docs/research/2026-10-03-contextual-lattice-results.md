# Contextual Lattice: completed results

## Simple summary

We tested catch-up, reversal and movement forecasting across equities, S&P 500 futures (ES), Treasury-note futures (ZN), oil futures (CL) and gold futures (GC): **15 fixed comparisons**. Each used six controls on the same eligible observations. **Context plus Lattice had the lowest forecast error in none of the 15 comparisons.**

This does not establish that every Lattice idea is useless. These specific daily rules did not earn a promotion to trading. The futures models had only 60–61 qualified training rows, and all 2024/2025 outcomes were already development data.

| Market | Best catch-up forecast | Best reversal forecast | Best movement forecast |
|---|---|---|---|
| equities | ticker training mean | ticker training mean | Lattice alone |
| ES | zero change | zero change | ticker training mean |
| ZN | zero change | zero change | ticker training mean |
| CL | zero change | zero change | ticker training mean |
| GC | zero change | zero change | ticker training mean |

“Best” means lowest observed mean squared forecast error, not proven profitability or a statistically established winner. The zero forecast predicts no change; the ticker mean repeats that instrument's average change from training.

## What context means here

- **Catch-up:** ask whether a prior market move and a mismatch with related assets help forecast the next session. This is a market-price proxy. Actual transmission through customer/supplier or financing links still needs dated signed exposures, prior expectations and public-information clocks.
- **Reversal:** ask whether the size of the observed move, peer mismatch and relationship stability change the next-session forecast. Equities also use conservatively cutoff-known SEC 8-K context. The fitted graph interactions are continuous; the exported two-standard-deviation gap flag is descriptive.
- **Movement:** forecast how much the next-session mark changes, without predicting its direction. Compare it against prior own volatility, prior absolute movement and a training mean. This is not an option-price or profit forecast.

We compared ordinary history, context alone, Lattice alone, the combination, zero change and the ticker training mean. No parameters were tuned after reading these results.

## The improvements that do not establish an edge

- Treasury catch-up: adding Lattice reduced error by **8.98% versus context alone**, but the simpler zero-change forecast still won.
- Gold movement: the combination reduced error by **23.24% versus context alone**, but the ticker training mean still won.
- Equity movement: the combination improved error by **0.20% versus context alone**, with uncertainty spanning zero, and was **0.50% worse than Lattice alone**.

The block intervals are exploratory within-cell diagnostics across a 15-cell family; they are not adjusted discoveries. These findings do not supply an independent confirmation or a forecast-to-profit bridge.

## Options, risk filtering and hedging

Options audit: **34 attempted events, 90 event/expiry rows, 31 events with descriptive mark pairs**. The original primary sample remains **18 distinct events**, below its fixed 20-event gate. Twenty rows had diagnostic stock movement predictions; they do not constitute twenty independent events. Options remain **inconclusive**, with option premium, implied volatility and executable profit blocked.

Stock movement is a fractional adjusted-close target in the main experiment. The options audit separately records absolute stock log changes and fixed-contract straddle midpoint changes; those are different quantities. Long-maturity option premiums are not a one-session implied-movement estimate.

Direct signals and risk filters were recorded as uncosted mark comparisons. A positive gold catch-up risk mark had about 97.96% exposure versus a 91.67% training-frozen cash control, so it cannot demonstrate superior risk filtering. Futures hedge benefit remains untestable without a fixed portfolio exposure, costs, margin and lifecycle contract.

## Data, clocks and missing information

- Equity targets: fractional next-panel-session adjusted-close changes. Features use a completed 16:00 ET statistical close with assumed replay availability; identity, adjustment vintages and original receipts are not certified.
- Futures targets: actual same-contract point changes divided by the decision-time prior point-risk scale. These are dimensionless risk units, not percentage returns. Decisions are 09:30 ET using previous-session 09:36 inputs; entry/exit marks are sampled interval-end midpoints. The reference calendar is the observed common cash-session panel, not a certified product-session or executable-fill model. MES remains an implementation-size diagnostic, not a separately tested independent forecasting market.
- SEC context: 4,058 cached filings; ten complete 8-K inventories. XOM is unknown and GD partial. Reversal retains those missing states and evaluates 5,020 of 6,024 equity diagnostic rows. No future filings are used to label a decision as news-free.
- Benchmark currently has zero qualified historical financial/security-mapping rows for this join, and no qualified prior expectations or signed business exposures. Those fields remain unavailable.
- No new Databento order was placed. Future acquisitions must adopt the shared absolute SQLite paid gate; the legacy pilot buyer is currently unused and its migration remains unverified.

## Tracking and verification

- 7,024 distinct instrument-days; 21,072 market/hypothesis decisions.
- 20,044 evaluated decisions and 1,028 context/outcome abstentions; six candidates per attempt produce 126,432 ledger rows.
- 8,471 no-trade statuses include missing information, direction conflicts and magnitude-only movement forecasts. Every outcome and reason is preserved where available.
- **45 focused remote tests passed.** Independent source and result review completed; 15 reports, zero operational failures.
- Source-only snapshots, pre-fit config/input/code hashes, append-only lifecycle events, output hashes, commands and logs are retained. Runtime package versions were observed after the run, not retroactively described as a pre-fit environment lock.
- Results archive and all 78 primary output-file hashes verified after retrieval. The integration fixture archive and its six output/log hashes also verified.

## Where everything lives

- [Registered experiment](../../configs/experiments/contextual-lattice-v1.json)
- [Summary and all 15 reports](../../artifacts/contextual-lattice/run-v1/results/contextual-v1/summary.json)
- [Every opportunity and its source/context fields](../../artifacts/contextual-lattice/run-v1/results/contextual-v1/all_opportunities.csv)
- [Every candidate decision](../../artifacts/contextual-lattice/run-v1/results/contextual-v1/all_candidate_decisions.csv)
- [Frozen manifest](../../artifacts/contextual-lattice/run-v1/results/contextual-v1/manifest.json) and [lifecycle events](../../artifacts/contextual-lattice/run-v1/results/contextual-v1/events.jsonl)
- [Options audit](../../artifacts/contextual-lattice/run-v1/results/options-context-v1/summary.json)
- [Runtime and exact counts](../../artifacts/contextual-lattice/handoff-v1/runtime_and_counts.json)
- [Three-row 2024 integration fixture](../../artifacts/contextual-lattice/handoff-v1/results/integration-2024-fixture-v1/fixture.json) and [producer manifest](../../artifacts/contextual-lattice/handoff-v1/results/integration-2024-fixture-v1/manifest.json). Consumer acceptance is pending; delivery is not acceptance.

## All comparisons

Positive percentages mean the combination had less squared error than context alone; a negative percentage means more error. This comparison does not imply it beat the simpler controls.

| Trial | Qualified training rows | Diagnostic rows | Error reduction versus context | Lowest observed error |
|---|---:|---:|---:|---|
| equities_catchup | 15,828 | 6,024 | -0.058% | ticker training mean |
| equities_reversal | 13,190 | 5,020 | -0.062% | ticker training mean |
| equities_movement | 15,828 | 6,024 | +0.203% | Lattice alone |
| ES_catchup | 61 | 249 | +0.373% | zero change |
| ES_reversal | 61 | 249 | -3.923% | zero change |
| ES_movement | 61 | 249 | -0.216% | ticker training mean |
| ZN_catchup | 61 | 249 | +8.981% | zero change |
| ZN_reversal | 61 | 249 | -8.231% | zero change |
| ZN_movement | 61 | 249 | -1.210% | ticker training mean |
| CL_catchup | 61 | 249 | -0.967% | zero change |
| CL_reversal | 61 | 249 | +0.859% | zero change |
| CL_movement | 61 | 249 | +1.431% | ticker training mean |
| GC_catchup | 60 | 245 | -0.596% | zero change |
| GC_reversal | 60 | 245 | +0.707% | zero change |
| GC_movement | 60 | 245 | +23.238% | ticker training mean |

## Next research gate

The useful next question is whether qualified company/economic event context improves these forecasts. It requires dated identities/exposures, usable publication/receipt/processing clocks and expectations frozen before release. It should be tested against strong ordinary/context-only substitutes, then genuinely new observations. The current tested combination is not ready for a trading or hedging paper candidate.

Experiment config fingerprint: `ea5ea62f21a45a15168f6573d1e561c709fd3df442ec2e75d93dd3abbfb77c49`.
