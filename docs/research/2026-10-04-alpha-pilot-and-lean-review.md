# Project review: a small alpha pilot and LEAN

Date: 2026-10-04. Status: recommendation and peer-review receipt, not a new implemented strategy. The user asked the other agents whether the [Sharpe/Monte Carlo plan](../superpowers/plans/2026-10-04-sharpe-confidence-and-monte-carlo.md) fits the whole project, requested a rough anticipated Sharpe, and then asked whether to simplify and use LEAN. No jobs, migration, paid requests, trades or existing-owner cancellations were performed.

**Current selected first arm:** post-release wording-only equity pilot; financial-benchmark surprise next. Finish bounded commitments, then focus new work on the pilot. Report hypothetical USD 1,000,000 results when the costed account data qualify. The later decision/receipt sections record actual user replies; economic performance remains unavailable.

## Decision

**Simplify the first experiment.** The full architecture is useful as a destination, but the next milestone is one accepted, costed, falsifiable decision policy. Keep the project objective of net portfolio growth within hard risk limits. Avoid making all industry, wording, geometry, regime, prediction-market and cross-asset work prerequisites for that first economic test.

The main research question is whether dated company information adds useful economic value beyond a simple information-and-price baseline at feasible entry/exit prices. Sharpe inference evaluates the uncertainty of that policy; Monte Carlo evaluates specified risk scenarios. Neither creates the information advantage.

## Peer review collected so far

Five existing project chats were explicitly asked for fit, dependencies, and a subjective Sharpe prior. The exact titles below identify the reviewed chats; summaries are not substituted for names.

| Chat | Response actually received at this snapshot |
| --- | --- |
| **Track work across project chats** | Supports one event family, one frozen signal, equities, realistic costs and a matched baseline. Recommends first producing one accepted costed replay; a LEAN migration now would duplicate integration work unless it fills a specific execution gap. Warns a failed post-disclosure equity test leaves the pre-event options hypothesis unresolved. |
| **Post Benchmark** | Says the Sharpe plan fits the architecture. Net account ledger comes before Sharpe inference; supported execution/lifecycle rules come before market-path simulations. Its conservative research prior is no positive incremental edge yet. Supports assessing a smaller pilot; detailed engine review is still in progress. |
| **Benchmark** | Reports a delivered financial source packet and no validated portfolio return history from which to estimate Sharpe. This is a source-status response, not a completed numerical Sharpe review. |
| **Benchmark pt. 2 industry spec** | Request delivered; substantive plan review pending. Its current market-adapter work distinguishes last-trade timestamp from quote-update freshness, which remains an economic-data gate. |
| **Assess Lattice repo fit** | Request delivered; substantive plan/LEAN review pending at this snapshot. Do not present pending feedback as agreement. |

An independent statistical reviewer also supports a small post-disclosure equity pilot, explicit stopped-versus-inconclusive rules and a skeptical near-zero Sharpe prior. These are judgments, not additional market observations or independent tests of profitability.

The existing [Post Benchmark handoff](../coordination/handoffs/post-benchmark.md) identifies its canonical checkout as `C:/Users/johnp/.codex/worktrees/8k-cross-asset-validation/QuantHaxs`, with existing `src/research_validation/` contracts/evaluator/portfolio modules. Additions should extend that owner's implementation, not instantiate a competing package in the shared root. Existing root forecast/mark fixtures remain diagnostics. Previously inspected 2024/2025 studies cannot be relabeled as untouched final data.

## Next financial-benchmark test

For the financial-benchmark arm that follows the selected wording-only pilot, use the best-covered eligible liquid-equity slice and **one** clear event family, such as earnings/guidance disclosures. Freeze one simple financial-benchmark surprise signal and one long-only/cash decision rule, with fixed sizing and holding horizon. Compare a simple prices/calendar/public-surprise baseline against that same baseline plus the one proposed signal on identical eligible opportunities. This is the next arm's proposal, not the selected first wording-only rule.

The minimal test still needs:

1. Dated eligibility and earlier public financial observations; released information enters only after evidenced first-public and usable/processing time. Retain missing and excluded events.
2. One frozen decision schedule. Reuse the canonical 15:30 New York/half-day rule if appropriate; any different post-release entry clock requires a separately registered namespace and feasible quotes after usable time.
3. Feasible entry/exit quotes, fees, spread, declared additional slippage, size constraints and one cash/equity ledger. No contemporary universe backdating, last-trade-as-fill assumption, or duplicate spread charging.
4. Development-only choice of features/threshold/horizon, then an actually unseen later period or frozen forward paper. Use a bounded trial ledger and enough distinct economic episodes to make precision useful.
5. Paired after-cost growth/return improvement and its 95% uncertainty, drawdown/concentration/cash use, and the required 95% interval whenever eligible account-level Sharpe is reported. Retain an explicit inconclusive/undefined state when the data or method cannot support it.

For both early equity arms, defer options, futures, automatic switching, advanced geometry, prediction-market inputs, large NLP/ML models and elaborate synthetic market-path campaigns. Preserve them as separately registered later arms. A small known-parameter calibration and justified dependence-aware uncertainty remain necessary when eligible Sharpe is reported; large final calibration and path stress are later promotion work, not prerequisites for examining one costed replay.

This choice tests **post-release information value in equities**. It does not settle pre-event forecasting, option pricing, hedging or every industry family. If the user instead chooses anticipation as the first economic mechanism, use earlier-only features, an ordinary eligible company-day risk set including no-event days, and a separately frozen policy; later filings must not select its test cohort.

## Stop, expand, or remain inconclusive

These are proposed prospective decision rules for a later confirmation. The user subsequently chose to review the first USD 1,000,000 descriptive report personally, without supplying numeric usefulness/risk thresholds. Do not apply invented thresholds to that first report or claim post-result choices were preregistered.

Before seeing final results, specify the minimum worthwhile net improvement and risk limits. Stop the tested arm when an adequately informative, valid frozen comparison shows its upper uncertainty bound below that useful improvement, or valid replay fails the chosen risk constraints. Preserve the negative result and test scope.

Missing usable clocks/quotes, undefined costs, too few independent episodes, near-zero trading or a wide interval are **inconclusive**, rather than proof of no alpha. More option variants or simulation draws do not create independent announcements. Expand only when the simple mechanism survives costs and useful precision, then add one layer at a time against the same baseline. Repeatedly inspecting accumulating final data requires a separately specified sequential design; do not peek until a desired answer appears.

## Rough anticipated Sharpe

The root's forced **subjective planning prior is approximately 0.0 annualized, after-cost, out-of-sample Sharpe**, assuming the policy actually trades and has nonzero excess-return volatility. This is low-confidence judgment, not a measured estimate, a target, or a 95% confidence interval. Negative results remain plausible; no accepted account series justifies assuming 1+ Sharpe in budgets.

The statistical reviewer used a deliberately broad uncalibrated scenario band of -1 to +1. It carries no assigned coverage/probability and should not be presented as a confidence interval. This receipt retains the distinction rather than averaging agents' opinions into a fabricated forecast.

Total portfolio Sharpe and incremental information edge are different quantities. A future base portfolio may earn market/carry premia without the new signal adding value. Compare the same feasible baseline using paired net growth/loss and delta-Sharpe where both ratios are defined. An entirely cash/no-trade excess-return path has undefined Sharpe, not Sharpe zero. Financial source accuracy, OCR quality and forecast loss scores cannot be converted into predicted trading Sharpe.

## LEAN decision

**LEAN is a reasonable execution/accounting engine to consider; it is not necessary to restart this project to run the first alpha test.** Retain the financial/industry/text feature pipeline as timestamped external research input. Prefer the existing canonical replay for the small pilot if it can reproduce the exact feasible ledger. If it lacks a material order/cash/instrument capability and implementing that capability would take longer than a thin LEAN adapter, use LEAN for that frozen pilot and reconcile its fills/cash/equity against a small independently checked fixture.

[LEAN's official repository](https://github.com/QuantConnect/Lean) describes its open-source, event-driven and customizable engine with Python/C# support. [QuantConnect's fill-model documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts) explains configurable prices/quantities/spread/slippage and notes prebuilt backtest models assume complete fills; partial-fill behavior needs a custom model. [Slippage documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts) states the default brokerage uses zero slippage. [Fee models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/key-concepts) are also configurable. Accepting those defaults without matching the actual instrument/broker/quotes would not satisfy this project's economic contract.

The [current official CLI deployment guide](https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment) requires membership in an organization on a paid tier for the CLI and describes Docker-based local backtests and external/imported data. That requirement concerns the supported CLI workflow; the engine repository is open source. Data rights, security mapping/corporate actions, real release times and bid/ask coverage still require project-specific evidence. No installation, subscription, download or migration was initiated.

If adopting LEAN later, export immutable decision-time signals with identity/version/availability hashes, configure fill/fee/slippage/cash models explicitly, and compare the same tiny economic fixture before widening scope. Preserve the protected evaluation split, trial registry, outside-engine Sharpe confidence procedure and detached `home-pc` workflow for heavy runs. A new engine must not become another parameter search.

## Change to the Sharpe plan

The 95% interval requirement is retained. Stage the addition behind one accepted costed pilot, build inference on the canonical owner's account ledger, and add full engine/path Monte Carlo only after the relevant execution/lifecycle interface is supported. Small method fixtures can proceed independently. These are refinements to the validation sequence; this review does not cancel other owners' work or broaden trading authority.

## Human decisions and coordinated pilot — 2026-10-04

The user has now answered the first interview round:

- Q1, first mechanism: **Post-release information value (recommended)**.
- Q2, sequencing: **Finish bounded work, then focus on the pilot (recommended)**.
- Q3, usefulness/risk preferences: the user instead requests the actual results for a hypothetical **USD 1,000,000 starting portfolio**, including P&L, Sharpe and win rate, and wants to evaluate those results personally. No numeric usefulness hurdle, drawdown limit or position/exposure cap was supplied. Do not invent those limits or treat the capital assumption as permission for live capital.
- Q4, narrower mechanism: **Wording-only pilot first; financial benchmark next (recommended)**. This supersedes the earlier financial-surprise-first recommendation for the first arm; the financial benchmark remains the next separate experiment.

Preserve the previously selected daily/next-session and historical-proof-then-forward-paper sequence. The disclosure family, exact frozen signal and comparator, feasible order/sizing/cost policy and evaluation window must be bound to the owners' actual eligible data before a replay. Earnings/guidance is a candidate family, not a newly confirmed user choice. Inspected 2024/2025 data remain development data.

The selected practical question is: does one existing simple frozen wording signal, available after an evidenced public bound and declared replay latency, improve net account results over a matched price/calendar/public-metadata comparator? A wording-only failure cannot reject financial-benchmark surprise, pre-event or relationship mechanisms. Keep one matched eligible opportunity set, the cash comparator, one ordinary public/price comparator and at most one wording challenger. The comparator needs its own evidenced as-of information; later revisions and full later filings cannot supply it.

### Coordination receipts and ownership

The user explicitly authorized telling all project agents and jointly planning simplification. The scoped notice was delivered to **Track work across project chats**, **Benchmark**, **Benchmark pt. 2 industry spec**, **Assess Lattice repo fit**, **Organize Benchmark Data Push**, **OCR** and **HiPerGator**. The two dormant source/compute chats received a notice with no restart or new analysis request. The five current owners also received the actual Q1/Q2 decisions. Delivery is not agreement or consumer acceptance.

Direct delivery to **Post Benchmark** failed on three attempts with the app error `Cannot steer conversation ... without an active turn id`; no delivery or acceptance is claimed. The coordinator received this exception and the current USD 1,000,000 results request. Post Benchmark still owns canonical replay/integration; a tool delivery failure does not transfer its ownership.

| Owner | Smallest requested contribution | Boundary |
| --- | --- | --- |
| Track work across project chats | Shared priority/decision register and one critical path, including resolving the Post Benchmark delivery exception | Preserve existing master plan and owner assignments |
| Post Benchmark | One costed equity research capsule and account/return outputs | Existing canonical package and owner checkout; no competing replay |
| Benchmark | Minimum native financial definitions, exact packet and clock/coverage exclusions | Producer evidence must pass the consumer |
| Benchmark pt. 2 industry spec | Minimum dated equity identity, quotes and cost/context coverage | Last-trade time is not quote-update freshness; no new paid orders |
| Assess Lattice repo fit | Ordinary comparator and one optional challenger; retain negative controls | Complexity must show incremental value on matched opportunities |
| Organize Benchmark Data Push | Minimal research source allowlist and release labels | Publication readiness is separate from economic readiness |
| This Sharpe lane | Account-statistics contract, uncertainty/calibration and this decision interview | One owned implementation plan; no duplicate ingestion or execution |

The coordinator's [first-pilot decision register](../coordination/first-pilot-decision-register.md) was subsequently read from disk. It records the human choices and critical path: native consumer acceptance, eligible clocks/instruments/quotes/costs, a minimal comparison protocol, one economic replay, then uncertainty and review. Benchmark and industry have acknowledged the smaller-pilot sequence in their current chat updates. Lattice and the publication owner continue their bounded commitments; no completed feasibility recommendation or economic acceptance is inferred from those progress updates.

Finish current bounded commitments and redirect subsequent new effort toward these dependencies. Larger models, options/futures, relationship networks, strategy switching and broad synthetic campaigns remain later arms. This is sequencing, not cancellation of running jobs or deletion of results.

### What the current evidence can report for USD 1,000,000

A focused read of the canonical owner's current reports, configuration and `portfolio.py` found **no accepted costed strategy/account capsule**. The canonical grid has 2,008 document-only decisions and zero qualified costed targets; the integrated run has no tradable decisions and censored outcomes. The separate 16:00 price diagnostic reports 752 predictions over 188 dates/four tickers and ridge MSE 4.26% worse than the zero baseline. That is a forecast diagnostic, not a traded strategy or a dollar return.

`replay_portfolio(forecasts, quotes, sessions, experiment)` accepts a positive `initial_cash`, so the requested nominal capital can be represented. It requires frozen orders and quantities, supported instrument definitions, qualified quotes/sessions and an explicit cost policy; it does not infer a signal or sizing rule. The current strategy configuration supplies no accepted sizing policy. Existing tiny synthetic tests are not strategy assumptions. A terminal account-return scalar and last-fill valuation alone do not provide the regular marked account-return series needed for valid Sharpe inference or drawdown reporting.

| Requested field | Current reportable value/status |
| --- | --- |
| Starting capital | USD 1,000,000, user-specified hypothetical input |
| Ending equity; total net P&L; net return | Unavailable: no accepted costed account replay |
| Incremental net P&L versus comparator | Unavailable: no matched economic account paths |
| Sharpe and 95% confidence interval | Unavailable: no eligible periodic net excess-account returns or calibrated report |
| After-cost closed-trade win rate and win/loss counts | Unavailable: no accepted strategy trade ledger |
| Drawdown, time underwater, exposure, turnover and costs | Unavailable: no accepted regularly valued account ledger |

Unavailable values must remain null with reasons, rather than zero, a scaled mark diagnostic or a simulated performance forecast. The earlier subjective Sharpe prior is not an empirical result. Do not multiply diagnostic returns by USD 1,000,000: quantity, spread, commissions, participation, cash and market impact must be replayed under the declared capital policy.

The eventual report should disclose its actual dates and development/holdout status, initial/final equity, realized/unrealized/total after-cost P&L, financing and fees/spread/slippage, baseline and incremental results, eligible/excluded opportunities, fills/rejections, trade counts and after-cost win rate, daily equity/returns, cash/gross/net exposure, drawdown and risk breaches. Define the win-rate denominator as closed position episodes under the owner's netting/accounting contract; keep daily-positive-return and forecast-direction hit rates separate. A no-trade excess-return Sharpe is undefined. Retain failed/no-fill opportunities.

The user will evaluate these descriptive research results; no numeric stop/expand or production promotion rule has been accepted. A later confirmatory trial needs prospective thresholds or a specified sequential design, frozen policy and untouched data. Choosing a threshold after examining this report does not turn it into a preregistered confirmation. Still report uncertainty and data limitations; a wide interval or failed eligibility gate remains inconclusive.

### Grill-me method and remaining decision tree

#### New minimum-source proposal and clock clarification

Benchmark subsequently delivered its minimum-source handoff. This lane read the actual `docs/financial-pilot-scope.md` and `examples/financial-pilot/minimum-source-scope.json` in `C:/Users/johnp/.codex/worktrees/point-in-time-feature-matrix/QuantHaxs`; their SHA256 values match `3893b1635a5c326e17454e2b8b2fa346a24eca3194cf14ea01718992906a8bb5` and `0adccafa523fe86d168672a94cd937443d325678e603e6b2363f4207785f7c79`. This verifies the delivered proposal files, not the whole native packet or economic eligibility. It records 45 distinct original issuer/accession pairs and four native definitions; repeated daily cells and comparative numeric groups are not additional independent alpha events.

The proposal permits **zero mandatory financial features** for a first wording-and-market pilot. One simple wording signal plus a price/calendar/public-metadata comparator could test a narrower post-release text mechanism. The original financial-benchmark surprise hypothesis remains a separate next arm; a wording-only failure cannot reject it. Optional liabilities/assets stays disabled until its distinct definition and causal availability are accepted. No new producer, OCR/LoRA/API model or universal leverage ranking is required for the wording proposal.

An independent statistical review corrected an overly broad clock prerequisite: a **delayed post-publication test** can use independent evidence that the *specific text/version used* was public by a conservative upper-bound time, plus explicitly registered historical processing latency and the next eligible executable quote. Exact earliest news need not be known for this narrow mode. Preserve unknown earliest-public and actual historical receipt/processing times; label the output a conditional conservative replay. SEC acceptance alone is not public-bound evidence. A day-level bound cannot become an early intraday timestamp; use the end of the supported publication window and the next eligible decision/quote. Revised text cannot leak backward.

Both policies must use the same eligible events, decision time, available price/public information, quotes, cost and account rules. Retain all excluded/unknown-clock opportunities. This mode tests useful wording value at the chosen conservative delay; it cannot establish first-news speed, actual historical automation, pre-event alpha or financial-benchmark surprise. Observed forward paper still needs actual receipt/processing evidence. The canonical owner must accept and register this mode; this clarification does not populate missing timestamps or certify a current economic capsule.

**Q4 is resolved by the user:** wording-only first, financial benchmark next. Register the first arm distinctly from the original financial-benchmark hypothesis. This selects the mechanism; it does not supply an exact feature aggregation, order/sizing/cost policy or accepted input capsule. Those must be made concrete through the existing canonical owner, with explicit research assumptions and provenance. Source qualification can continue without new financial-feature expansion.

No installed grill-me/remote-compute skill was found in the checked local roots. The requested [published grill-me wrapper](https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md) and [grilling method](https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md) were read directly; this is an explicit public-source method fallback, not a local installation. Ask decisions in dependency order, collect environmental facts from owners, and retain unanswered branches rather than assuming user agreement.

```text
Known objective: net portfolio growth within hard risk limits
  -> first arm: post-release information value in equities [user selected]
  -> sequence: finish bounded commitments, then focus new work [user selected]
  -> report capital: USD 1,000,000 hypothetical [user selected]
  -> wording-only first; financial-benchmark surprise next [user selected]
  -> exact source/clock/identity/quote coverage [owner facts pending]
       -> choose one feasible disclosure family and causal comparator/signal
       -> freeze explicit research order/sizing/cost policy and daily valuation
       -> replay inspected development data as development, with exclusions
       -> net dollar/return/trade/risk report and eligible 95% inference
  -> user reviews results [requested; economic outputs not yet available]
       -> decide usefulness, risk/position limits and next experiment
       -> new frozen confirmation/forward-paper stage, then separate promotion
```

Continue only the existing [Sharpe implementation plan](../superpowers/plans/2026-10-04-sharpe-confidence-and-monte-carlo.md) in this lane and the canonical owner's existing pilot plan. Heavy replay/calibration uses `home-pc` over Tailscale, detached `tmux`, the shared heavy-job lock and current two-thread/4 GiB bounds. No bulk local output, full-suite rerun, new engine installation, paid request or production action was performed here.
