# Extensions of Lattice's numerical approach

Date: 2026-10-03. Status: research recommendations and falsification protocol, not implemented capabilities or trading results. Only this note was created for this review. No jobs, acquisition, model fitting or trades were performed.

## Scope and decision

The latest user direction is to test **all proposed futures families and all three numerical roles**, following the recommendations first: equity-index futures before Treasury rates before energy/metals; forecast information before risk/filter rules before direct standalone signals. Futures alpha and hedge benefit remain separate. Decisions are daily and outcomes are next-session; historical evidence precedes a frozen forward paper test. These choices supersede the earlier pending first-family/first-role frontier. Exact clocks, contract selection, risk permissions, capital, costs and reserved dates still require an experiment freeze.

The decision optimized here is which extensions can produce a trustworthy answer about incremental information or economic value with manageable data and search. The repository is evidence of available plumbing, not a boundary on research ideas. Its failed H1 correlation-distance peer-reversion rule remains failed. MDS coordinates were absent from that signal path; alternative numeric features are unproven. Factor-residual exports, surface adapters, futures lifecycle panels and learned policies below are proposed work.

**Recommended first packet:** factor/residual geometry and a causal relationship-stability measurement, with ordinary volatility/correlation controls. Start on equities plus ES/MES, then apply the registered packet to rates and commodities. Curves and options require their own representations and competing baselines. Do not call a common-factor return a novel geometry effect.

## Ranking contract and evidence

Scores are subjective priority judgments from 1 (weak) to 5 (strong), not probabilities of success. Weights: economic specificity **35%**, falsifiability **25%**, data tractability **25%**, plausible incremental value beyond simple controls **15%**. A missing execution or timing prerequisite blocks evaluation irrespective of score.

| Rank | Extension | Economic / falsifiable / tractable / incremental | Weighted priority | Main value | Main uncertainty |
|---:|---|---|---:|---|---|
| 1 | Factor-residual geometry | 4 / 5 / 4 / 4 | 4.25 | Separate issuer relationships from dominant market/sector exposures | Residual geometry may add nothing beyond its factor model |
| 2 | Graph stability and regime reliability | 3 / 5 / 5 / 3 | 4.00 | Detect unreliable peer/hedge relations with few extra data sources | Sampling noise can masquerade as a structural break |
| 3 | Futures curve/basis state geometry | 4 / 4 / 3 / 4 | 3.75 | Represent product-specific carry and curve innovations | Historical risk-premium evidence does not establish next-session prediction |
| 4 | Constrained learned hedge/risk policy | 4 / 4 / 3 / 3 | 3.60 | Translate state information into lower residual risk after costs | Gains may be ordinary deleveraging or covariance shrinkage |
| 5 | Option-surface residual repricing | 4 / 4 / 2 / 4 | 3.50 | Forecast exact premium changes beyond underlying direction | Quotes, exercise treatment and systematic option risks dominate apparent edge |
| 6 | Dated economic-exposure/disclosure graph | 3 / 3 / 2 / 5 | 3.05 | Connect FDS facts to economically related issuers and explicit exposures | Small event sample and historical linkage vintages |

**Evidence versus inference:** Mantegna demonstrates economically meaningful stock-correlation hierarchies; Ledoit–Wolf addresses covariance estimation; Engle provides a dynamic-correlation model. These support representation and competing benchmarks, not profitable Lattice strategies. [Mantegna paper](https://arxiv.org/abs/cond-mat/9802256), [Ledoit–Wolf covariance paper](https://www.ledoit.net/Well-conditioned2004.pdf), [Engle DCC paper](https://pages.stern.nyu.edu/~rengle/dccfinal.pdf).

The carry paper documents predictability and common bad periods across asset classes. The commodity inventory paper links inventories and basis to risk premiums. Neither validates this daily-next-session geometry experiment. [Koijen et al., Carry](https://www.aqr.com/Insights/Research/Journal-Article/Carry), [Gorton, Hayashi and Rouwenhorst](https://www.nber.org/papers/w13249).

The 2025 options factor study finds that much of documented delta-hedged strategy profitability is explained by common option factors. Its monthly setting differs from the proposed next-session holds. Its lesson here is to distinguish residual information from stock, volatility, jump and liquidity exposures. [Goyal and Saretto](https://academic.oup.com/rfs/article/38/6/1783/8010873).

If risk protection becomes the primary mandate, rank 4 can move ahead of curves. If a fully audited option chain already exists, rank 5 becomes more tractable. If only equity closes are available, ranks 1–2 can be explored descriptively; economic promotion waits for eligible execution evidence. These changes affect research order, not empirical conclusions.

## 1. Factor-residual geometry

**Mechanism hypothesis.** Broad market and sector movements can make firms appear related without identifying issuer-specific news transmission. Fit a small dated factor model, retain each issuer's residual return, then measure relationships and unusualness in that residual panel. Test whether financially relevant residual shocks predict the next-session residual response. Joint market geometry remains a separate state variable; stripping factors must not remove useful aggregate information and then claim its absence is alpha.

**Minimal data.** A proposed 12-name historically eligible equity cohort, market and sector proxy observations, actual corporate-action vintages, complete session calendars and executable underlying prices. Fit betas with past-only observations. No current constituent list reconstructed into the past. For futures, standardized point/cash innovations and explicit economic factor proxies replace equity log-return code; one ES/MES index exposure occupies one vertex.

**Small representation.** Start with a shrinkage residual-correlation matrix, one invariant eigenvalue concentration scalar, and one per-name weighted peer residual shock. Peer weights are fixed using the preceding eligible window; their current shock enters only after its source observations are available. Residual geometry and raw geometry are distinct experiments. MDS display coordinates are unnecessary.

**Competing baseline and test.** Ordinary market/sector betas, own residual momentum, residual volatility and sector-peer residual shock; a trailing PCA/shrinkage-correlation substitute uses the same source data and capacity. Evaluate paired next-session residual forecast loss, then fixed-policy executable cash outcomes. The factor model itself must receive credit through an ablation that adds factors without geometry.

**Leakage/overfit risk.** Full-history beta/PCA fits, revised actions, full-sample peer selection, unstable inverse covariance, missing-name cohort changes and selecting the factor set after outcomes. More factors can suppress any desired return by construction.

**Reject.** Increment disappears after ordinary factor/peer controls, weights depend on future observations, effect is concentrated in one issuer/episode, or residual forecast gains fail executable economics. A noisy interval spanning both useful and harmful effects is inconclusive. Failure does not revive H1 under a new name.

## 2. Graph stability and regime reliability

**Mechanism hypothesis.** Relationships estimated from quiet history may become unreliable during changing market states. A causal graph-stability measure could identify when a peer forecast, beta hedge or covariance forecast should be trusted less. Structural change alone has no signed return implication.

**Minimal data and representation.** Reuse rank 1's panel. Freeze graph construction, sparsity and one lookback. Start with edge turnover between consecutive past-only windows: `1 - |E_t intersection E_previous| / |E_t union E_previous|`, using stable node identities and an explicit empty-graph convention. The windows share observations; this dependence is real. Compare observed turnover with an estimation-noise diagnostic constructed only in development. Membership additions/deletions and stale observations are not genuine breaks.

**Competing baseline and test.** Changes in average correlation, realized volatility and factor concentration; a shrinkage covariance or simple exponentially weighted covariance forecast. Forecast next-session squared residual error and covariance error before any policy. Then compare a fixed filter/sizing rule with ordinary volatility sizing at comparable average gross exposure. Register stability as risk/reliability information; its direct-direction test is allowed to fail separately.

**Leakage/overfit risk.** Tuning graph sparsity/windows until a crash is identified, labeling regimes retrospectively, selecting turning points from future data, and treating coordinate rotation as a break. Existing tear/topology fields do not automatically implement this stability estimator.

**Reject.** Turnover is explained by sampling noise, stale data or node changes; covariance prediction is no better than the substitute; or apparent protection is reproduced by uniformly reducing exposure. Persistence/topology features require another registered experiment if the simple graph measure fails; they are not unlimited rescue variants.

## 3. Futures curve and basis states

**Mechanism hypothesis.** Product curves represent different economics. Commodity curves can reflect inventory scarcity/storage and financing; Treasury futures also embed deliverable-bond and conversion-factor mechanics; equity index basis involves the cash index, rates and dividends. A joint curve-state representation might improve conditional return/risk forecasts beyond ordinary carry, momentum and volatility. It is not a guarantee that contango means a short trade tomorrow.

**Minimal data.** Actual contract definitions and the front plus next eligible maturity per root; dated settlements or synchronized prices, publication/correction timestamps, expiration/notice/delivery calendars and execution quotes. Add a third maturity only for a separately registered curvature feature. A cash basis claim also needs a comparable cash instrument and financing/dividend inputs. Without those, label the feature a calendar spread, not verified cash basis.

**Small representation.** Start with a signed maturity-adjusted calendar-spread slope in native units and past risk scale, not a log ratio that fails at zero/negative prices. The slope is an ordinary control. The geometry challenger is one distance/depth of the current slope-and-price-innovation vector relative to its past fitted distribution. Product-local transformations precede any joint state model.

**Competing baseline and test.** Price momentum, volatility, ordinary slope/carry and simple linear interactions are the benchmark. Fit separate ES, ZN, CL and GC next-session cash-change models; test standardized forecast error, risk policy and direct after-cost outcomes separately. Curve depth must add value beyond the same slope used without geometry. Treasury cash basis requires cheapest-to-deliver, conversion factors, cash DV01 and repo inputs; otherwise defer that claim. [CME Treasury delivery mechanics](https://www.cmegroup.com/content/dam/cmegroup/trading/interest-rates/files/us-treasury-futures-delivery-process.pdf).

**Leakage/overfit risk.** Roll jumps, final corrected settlements/OI, current cheapest-to-deliver backfilled into history, incompatible maturity intervals, seasonal effects selected after outcomes, and normalizing with future volatility. A Treasury futures price is not a constant-duration cash yield series.

**Reject.** Returns come from a symbol switch, late data, scaling error or unmodeled carry exposure; geometry does not beat slope/momentum; or next-session intervals are uninformative despite longer-horizon published evidence. Keep any informative risk state distinct from failed directional alpha. Uranium would need spot-versus-term-contract observations and its own economic instrument mapping; this note proposes no uranium futures panel or miner-to-spot equivalence.

## 4. Constrained learned hedge and risk policy

**Mechanism hypothesis.** Market state can change how much risk an existing portfolio carries and which hedge offsets it. Learn a small state-conditioned covariance/beta adjustment, then construct a hedge under a frozen risk and turnover objective. Signal generation and portfolio construction remain separate; the hedge cannot quietly add a directional bet to improve its scoreboard.

**Minimal data.** Rank 1/2 state features; dated holdings and Greeks; actual hedge contracts, prices and fees; margin schedules and broker assumptions; one account ledger. Index hedges initially address equity beta. A Treasury hedge needs measured portfolio rate exposure; oil/gold hedges need documented exposures. A discovered correlation alone does not establish an economic hedge mandate.

**Competing baseline and test.** No hedge, a frozen rolling-beta/DV01 or measured exposure hedge, and shrinkage/EWMA covariance hedging. Compare the Lattice-conditioned policy's net portfolio downside variation and residual exposure, matched for hedge budget, average leverage and turnover constraints. Report expected-return change, not only realized variance. Use a simple constrained quadratic construction with a turnover penalty; reinforcement learning is not an initial requirement.

**Leakage/overfit risk.** Optimizing historical crash dates, changing the underlying alpha strategy, choosing hedge instruments after losses, learning allocation and covariance jointly with a large action space, and reporting risk reductions without their capital/cost effect.

**Reject.** Improvement disappears against shrinkage/EWMA or uniform deleveraging, is achieved by unequal leverage/cash, exceeds hedge mandate, or fails after fees and integer contract sizing. A useful hedge is not standalone futures alpha. A risk filter is not a calibrated forecast unless evaluated as one.

## 5. Option-surface residual repricing

**Mechanism hypothesis.** A company's stock forecast does not determine its option premium change. Measure implied-volatility level/skew/term innovations relative to contemporaneous market/sector options and dated event expectations. Test whether a small residual surface representation forecasts the next-session change of a frozen contract beyond stock direction and ordinary IV/RV inputs. Use “residual repricing candidate,” not “mispricing,” until the economic test survives risk adjustment and costs.

**Minimal data.** A proposed four-name option subset selected before outcome inspection; at least two eligible expiries and five usable moneyness locations per expiry, actual underlying quotes, call/put bid/ask sizes, rates/dividends, adjusted deliverables and exercise conventions. Missing coverage blocks that surface, rather than triggering a favorable contract replacement. Surface context does not change the separately frozen primary tradable-contract policy.

**Small representation.** One standardized ATM-volatility innovation after simple market/sector controls and one skew innovation. Fit/interpolate only the decision-available chain. Gatheral–Jacquier provides static-arbitrage constraints for SVI surfaces; this is a useful later model reference, not evidence of trading alpha or permission to transplant European constraints into American equity-option pricing. [SVI paper](https://arxiv.org/abs/1204.0646). A sparse-chain diagnostic cannot assert a fully validated arbitrage-free surface.

**Competing baseline and test.** Same-contract premium prediction using underlying returns/volatility, spread, moneyness, DTE, IV level, IV–RV and simple skew/term slope. Report midpoint and after-cost ask-entry/bid-exit targets separately. Compare exposure-matched equity implementation and, if evaluated, a predeclared delta-hedged diagnostic that includes underlying hedge costs. Frozen forward contracts are never selected using later Greeks or winners.

**Leakage/overfit risk.** Asynchronous chains, last-trade marks, interpolating with later quotes, exercise-model error, picking a surface by fit quality after realized outcomes, and counting many strikes as independent. Apparent cheapness may compensate jump/volatility/liquidity risk.

**Reject.** Predictability vanishes with contemporaneous simple surface controls, premium economics vanish at valid sides/sizes, or performance is explainable by common option exposures. Do not infer short-option safety from failed long-option economics. Shorting permissions and tail-capital rules require their own freeze.

## 6. Dated economic-exposure and disclosure graph

**Mechanism hypothesis.** Extend price geometry with a separate graph of economically meaningful links: documented customers/suppliers, financing sensitivity, material input costs, revenue geography or industry exposure. Combine a frozen link with a new economic fact minus its frozen expectation. The hypothesis is delayed or heterogeneous issuer response, not a universal “good 8-K means ES rises” rule.

**Minimal data.** Historically dated FDS/link evidence, source coverage and direction/units, release times, frozen expectations and the existing market panel. Company-level facts are not revised into earlier decisions. Different link types remain separate; supplier revenue exposure and customer input-cost exposure can have opposite implications.

**Competing baseline and test.** Sector-peer response and ordinary beta/correlation links; factual surprise without a graph; text tone without economic links. Test one predeclared link-weighted surprise scalar against next-session issuer residual returns. A separate futures aggregation would need documented index weights or aggregate supply/demand/rate mapping, plus enough independent releases. Scheduled macro surprises require actual prerelease expectations and vintage releases, not today's revised series.

**Evidence limit.** Cohen–Frazzini studies delayed information incorporation across economically related firms. Its evidence motivates an economic graph, but does not establish this horizon, modern execution or FDS extraction quality. [Author paper](https://pages.stern.nyu.edu/~afrazzin/pdf/Economic%20Links%20and%20Predictable%20Returns%20-%20Cohen%20and%20Frazzini.pdf).

**Leakage/overfit risk and reject.** Reject future-discovered links, target filing features in anticipation, retrospective surprise definitions, winners-only events, or effects that disappear against sector/factor controls. The existing 34 CFO events cannot power a broad learned exposure graph. This extension is deferred to a new protocol when dated linkage/independent event coverage can support it.

## Bounded market coverage and contract accounting

The initial representatives below cover every proposed family without multiplying nearly identical exposures. Symbols are research recommendations, not acquisition orders or live positions. ES and MES are separately priced implementations of the same index hypothesis; MES fills/costs cannot be borrowed from ES.

| Order | Family / proposed root | Contract unit and outright tick | Intended independent tests |
|---:|---|---|---|
| 1 | S&P 500 ES and MES | ES $50/index point, 0.25 point = $12.50; MES $5/index point, 0.25 = $1.25 | One index alpha hypothesis; implementation/capital comparison; equity-beta hedge |
| 2 | Treasury ZN | $100,000 face, $1,000 per quoted point; 1/64 point = $15.625 | Rate-market standalone returns; measured rate-exposure hedge |
| 3 | Energy CL | 1,000 barrels; $0.01/barrel = $10 | Product-specific standalone returns; explicit energy-exposure hedge |
| 4 | Metals GC | 100 troy ounces; $0.10/ounce = $10 | Product-specific standalone returns; documented metals/portfolio exposure hedge |

Sources checked for these specifications: [ES rulebook](https://www.cmegroup.com/rulebook/CME/IV/350/358/358.pdf), [MES FAQ](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-micro-e-mini-equity-index-futures.html), [ZN rulebook](https://www.cmegroup.com/rulebook/CBOT/II/19.pdf), [CL rulebook](https://www.cmegroup.com/rulebook/NYMEX/2/200.pdf), [GC rulebook](https://www.cmegroup.com/rulebook/COMEX/1a/113.pdf). These are current source checks; actual replay uses dated definitions and notices. Notice/delivery, expiry, price limits, sessions and historical initial/maintenance margin are product-specific inputs. No current margin number is substituted into history.

Freeze a calendar-based contract-selection/roll rule before returns, recording each resolved maturity and the exact planned dates; enforce a safety window ahead of applicable notice/delivery/last-trade dates. Actual transactions settle in actual contracts. Front-contract series can support a named feature but their switches are not returns. A next-session trade ordinarily closes before a roll; if its interval crosses the frozen switch, handle the actual legs or abstain under a frozen rule, never manufacture a gap gain.

Futures point/cash changes support zero and negative prices. Reconcile variation margin plus residual mark-to-market/entry-exit adjustments to total execution P&L less fees and slippage. Count each roll leg once. Collateral transfers are not profit; margin is not the denominator for strategy return. Forecast cash changes, size on past risk, and report one account-equity return series with financing and liquidation constraints. [CME margin explanation](https://www.cmegroup.com/education/courses/introduction-to-futures/margin-know-what-is-needed), [CME roll explanation](https://www.cmegroup.com/education/courses/introduction-to-futures/understanding-futures-expiration-contract-roll).

## Feature and trial budget

The executed initial diagnostic uses **one fixed lookback of 63 eligible sessions**, frozen in `configs/experiments/multi-market-v1.json` before outcomes were opened. This supersedes this research note's earlier 126-session recommendation. No 126/252-session robustness run is authorized by this amendment or silently added after seeing results. Use past-only shrinkage/normalization, no learned embedding and no neural/RL model. A different lookback needs a separately registered development trial and counts in the ledger.

Maximum **six new scalar predictors** across the whole initial program: residual peer shock, residual spectral concentration, edge turnover, futures curve-state depth, option ATM-volatility residual innovation and option skew residual innovation. Ordinary slope, carry, price, volatility, beta, liquidity and IV controls are baseline features, not counted as invented geometry gains. No stock-option contract receives its own equity-like vertex. Economic-link surprise (rank 6), raw coordinates, topology grids, third-maturity curvature, macro surprise combinations and extra lookbacks await a separately registered protocol.

Use one registered additive challenger packet per lane, with simple substitutes and capacity matched in advance. ES uses joint state concentration/stability and ordinary directional controls; equity targets may additionally use residual peer shock; futures curve lanes add curve depth; options add their two surface residuals. A state feature may prove useless for signed returns: that result is retained rather than fixing a direction retrospectively.

The full initial budget is **22 primary cells**: four futures economic exposures × three roles (12), aggregate equity cohort × three roles (3), aggregate option cohort × three roles (3), and four separate exposure-appropriate hedge comparisons (4). A hedge cell without a defensible portfolio exposure is recorded as blocked/inapplicable, not forced into an unrelated portfolio. ES/MES execution comparison is one registered implementation diagnostic, not two independent alpha cells.

Reserve up to **six feature-deletion ablations**, each with a preselected market/target in development; report all, without selecting the best ablation as another final model. Thus at most **28 named primary/ablation questions**, plus the declared implementation diagnostic. Each comparison has an ordinary baseline and a simple-substitute benchmark. Cost/quote/latency stress scenarios are fixed diagnostics; choosing a winner among them creates a new trial. Maintain a ledger of every discarded fit, rule and cohort; a nominal cap does not erase earlier attempts.

## Evaluation schedule and gates

This is a sequence of evidence gates, not a promise of elapsed weeks or available history. The user asked to test every role; no role is silently dropped because forecasting fails. Forecast, risk and direct outcomes may disagree and receive separate decisions.

| Stage | Work and frozen deliverable | Gate before next stage |
|---|---|---|
| 0 | Free metadata and existing-file audit; versioned clocks, schemas, eligibility, costs, contract rules, budgets and test IDs | Audited sources and executable/proxy classifications; no automatic purchase from this note |
| 1 | Equity plus ES/MES: baseline and residual/state forecast; risk/filter comparison; direct next-session policy; separate beta hedge and ES/MES implementation diagnostic | Finish/report every registered role, including failures; freeze transfer packet before rates outcomes |
| 2 | ZN: same roles, Treasury mechanics and optional curve depth | Dated contract/rate inputs; no cash-basis claim without cash/repo/CTD evidence |
| 3 | CL then GC: same roles, product-local curve state and exposure-specific hedge comparison | Negative-price/roll fixtures, notices/delivery, dated statistics and quotes |
| 4 | Exact-contract option surface forecast, risk/filter and direct outcomes; equity implementation comparator | Valid synchronized underlying/option evidence, quoted sizes and fixed contract identities |
| 5 | One reserved historical evaluation of the registered candidates, full multiplicity ledger and account/exposure report | Per-role practically useful increment with informative uncertainty; no selection by headline Sharpe |
| 6 | Frozen surviving versions in forward paper; all ordinary/no-trade/missing/nonfill decisions logged | Complete the predeclared precision/coverage window; keep/reject/inconclusive per role |

Data/adapters for later markets can be audited in parallel with stage 1. Economic evaluation remains staged, and one integration owner controls schemas and the trial ledger. The recommended order prioritizes index forecasting; it does not make an equity forecast gain a scientific prerequisite for independent commodity alpha.

Aim for a bounded panel with **252 warmup + 504 training + 126 validation + 126 reserved-test sessions** (1,008 reference sessions total), subject to actual historical quote and vintage coverage. This is a planning size, not proof of power or confirmation that data exists or fits the acquisition cap. Use at least three chronological development validation blocks within the earlier history, preserving future-label purges. If coverage is inadequate, report a smaller study's limitations or defer economics; never backfill synthetic execution and call it proven.

Reserve final dates/cohorts before their outcomes are inspected. The current inspected CFO/cache data is development material. A downloaded file can still be eligible for a reserved study if its outcomes have genuinely not been inspected, but provenance must document access and reservations. Register fixed source-processing replay latencies; real historical receipt cannot be invented. Daily eligibility includes ordinary issuer-days, not only future-known events.

Exact daily cutoff and feasible next-session entry/exit must be frozen. Recommend a common US cash-session reference for initial cross-market comparability, while retaining every product's actual overnight trading calendar and the common account mark. A US daytime hold is not the entire overnight futures session; a separate overnight-horizon test is a new trial. Inputs must already be published/received/processed at the cutoff, and entry follows it. Do not repair a closed option decision with a later futures/cash quote. Same-session targets and actual next-session execution returns are kept distinct when the chosen clocks differ.

## Success, rejection and inference

**Forecast:** compare paired standardized next-session loss/calibration on identical eligible rows. A proposed practically useful floor is a 1% relative error reduction; finalize this before the holdout. It is a research criterion, not a profit claim. Reject a confidently nonpositive increment; remain inconclusive if precision cannot distinguish the floor from zero.

**Risk/filter:** compare downside variation/tail exposure net of costs against simple volatility/covariance policy at comparable average gross exposure, hedge budget and expected-return opportunity. A proposed floor is 5% lower downside variation without violating the separately frozen return/risk constraints. Uniformly holding more cash must appear as a competing baseline. Report uncertainty and opportunity cost; insufficient tail observations remain inconclusive.

**Direct signal:** map each lane's frozen forecast to exposure with a predeclared transaction-cost threshold and position cap. Compare after-cost daily account returns against the ordinary same-policy predictor and no trade. Require a positive net outcome and a materially useful paired increment after costs, exposure attribution and uncertainty. Absolute return/drawdown and capital limits remain to freeze with the analytical mandate; these recommendations do not assume permission to short equities/options or sell uncovered event risk. A lane unable to meet its execution/capital contract remains a forecast/pricing study.

**Hedge:** compare portfolio-plus-hedge cash/account outcomes to no hedge and a simple exposure/covariance hedge. No claim of alpha follows from lower residual risk. Hold the underlying portfolio policy fixed and preserve economically relevant beta/delta, gamma/vega and rate/commodity exposure measures.

All promotion gates require chronological out-of-sample evidence and the registered simple substitute comparison. Outcome intervals are purged across splits, and related issuer events/options/equity observations remain bundled. Time blocks preserve shared equity/futures/option shocks. Do not count 34 events, many contracts and their overlapping returns as independent observations.

Use preregistered dependence-preserving permutation tests before interpreting p-values, documenting the valid exchangeability/null assumption. If no valid permutation is available, state the limitation and use appropriate dependence-aware estimation without manufacturing a significance claim. Account for the full registered family and earlier trials; no uncorrected winning p-value justifies promotion. Report paired effect intervals and net daily account-return Sharpe with dependence-aware bootstrap confidence intervals, explicit capital denominator and annualization. Fat tails and serial dependence matter for Sharpe comparisons. [Ledoit–Wolf primary research record](https://ledoit.net/research.htm).

Reject results that depend on future fits, revised facts, stale quotes, roll jumps, incomparable exposure or unrealizable fills. Preserve original side-specific timestamps and sizes; model participation, partial fills and nonfills. Missing fixed exits cannot be replaced by favorable later exits, and missing selected contracts cannot be replaced by later winners. A narrow pricing proxy can support a diagnostic, not account-profit proof.

Keep **joint market state** and **issuer disclosure effects** as separate sources of evidence. Evaluate baseline state forecasts on ordinary daily rows. Evaluate pre-release arrival/surprise on a complete eligible risk set and post-release fact-minus-expectation only after usable processing. An event-state interaction is a separately registered question, not a free feature crossed with every market. FDS, OCR and FinBERT supply observations; measured market outcomes provide the labels.

Frozen forward paper records real receipts, feature completion, forecasts, quote opportunities, hypothetical fill/nonfill assumptions, exposures and policy versions. Predeclare observation duration/coverage from required precision; do not stop at the first favorable result. Passing historical forecasting alone does not prove direct alpha. Passing historical economic gates earns the forward test, not live capital.

## Next actions and integration

- Register the six-scalar/22-cell budget and the explicit six-ablation allowance; amend the older first-family/first-role pending record to reflect the user's all-markets/all-roles direction.
- Audit existing Lattice exporters for past-only windows and build the smallest factor/residual and graph-state definitions before any broader feature set.
- Quote bounded actual-contract and option-chain gaps using free metadata and the shared acquisition ledger; this note places no orders.
- Freeze exact clocks, historic cohort, holdout, cost/latency scenarios, permitted exposures and economic promotion floors; then implement adapters and reconcile one lifecycle/account trace per market.
- Complete every registered role in the index packet, then rates, then energy/metals, retaining rejected and inconclusive results. Carry only registered survivors into forward paper.

Read with [multi-market design](2026-10-03-multi-market-lattice-design.md), [implementation research plan](../superpowers/plans/2026-10-03-multi-market-lattice-research.md), [grill record](../grill-sessions/2026-10-03-multi-market-lattice.md) and [skeptical strategy review](../strategy-research-review-2026-10-03.md). This note does not alter their files or another workstream's ownership. Eventual heavy panels/backtests run on `home-pc` in detached tmux; none was launched here.
