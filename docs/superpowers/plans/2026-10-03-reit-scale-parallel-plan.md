# REIT Sources, Loan Networks and Arbitrage Research: Parallel Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans after the grilling decisions and final plan review are settled. Checkboxes below are planned work, not completed implementation.

**Status:** Execution authorized on 2026-10-03. The user now requests building, broader quality-audited sources and necessary Databento spending below $250. The coordinator enforces a conservative $249.99 total including the existing approximately $23.14 project ledger. Implementation and official discovery acquisition have started; measured execution evidence is in `2026-10-03-reit-scale-execution-ledger.md`. Earlier planning-only and spending-pending statements below are historical and superseded by this authorization. No claim of a completed historical backtest or profitable strategy is made.

**Goal:** Build a reproducible dataset of disclosed REIT loans, financing, cash movements and company relationships; test whether it helps identify executable pricing discrepancies or expected repricing in equities, options and relevant futures. Evaluate those two objectives separately.

**Architecture:** One acquisition broker feeds immutable source snapshots to independent extraction/history workers. Versioned contracts distinguish observations, instruments, legal entities, events and supported relationships. One publisher creates point-in-time datasets. Independent interpretation evaluation precedes two separately scored market-research tracks using a shared execution/capital ledger.

**Tech Stack:** Existing Python collector/analyzer and cached document text; standard-library SQLite/JSONL/CSV for state and snapshots. Large offline jobs use home-pc through detached tmux. OCR is assumed correct.

**Spec:** The contract and acceptance sections in this draft; settled decisions are recorded in `docs/reit-scale-grilling.md`. The implementation-ready task breakdown follows the interview rather than treating proposed defaults as settled requirements.

## Existing evidence

- Source research: 15 URLs and explanations in `docs/reit_document_urls.txt` and `docs/reit_document_url_explanations.txt`.
- Direct options-universe overlap: AMT under the current SIC screen. The 174 ticker rows and 53 CIKs are candidate screens, not a verified active common-stock REIT universe.
- Live pilot: four companies, 35 documents and 187 CompanyFacts observations; collection complete.
- Broader analysis: 638 parsed filing observations, 4,470 review records, 1,927 candidates and 4,051 candidate omissions; analysis partial.
- Realty Income PDF: 14 original checked assertions correctly classified. This does not measure other issuers or the full report.
- Existing consolidation is within a filing. Historical submissions traversal, instrument lineage and dependable parallel acquisition are missing.
- Offline integrity audit: all 36 retained raw files/text identities, 35 SEC URL identities, 59 cached SEC receipts, four CompanyFacts hashes and three analyzer output hashes passed. One exhibit's period remains unresolved. Integrity does not establish financial accuracy, completeness or current live reachability; see `docs/reit-collection-integrity-2026-10-03.md`.
- Existing market outputs concern a CFO-event study, not a complete REIT market universe: 34 events/89 expiry groups in one 2024–2025 manifest; an exact-contract Databento backfill and sampled quote pilots are separate datasets. No inspected manifest establishes REIT-wide equity/options quotes or futures coverage.
- The current study's equity proxy is derived from option parity. A strict discrepancy test needs independently observed stock prices rather than deriving both sides of its comparison from the same option quotes.
- A configured 2026 OOS window is not evidence of a completed locked REIT test. Previously examined 2026 examples are not automatically untouched evaluation data.

## Decisions that control the plan

| Decision | Recommended starting choice | State |
|---|---|---|
| Company universe | All validated US listed REITs, expanded in batches; retain an options-overlap view | Confirmed |
| Initial history | Backtest decisions from January 2024 onward; collect earlier opening evidence as needed | Confirmed; OOS required |
| Company intersections | Direct supported relationships with REIT/non-REIT parties, plus separately derived shared-counterparty overlap | Confirmed scope; technical policy below |
| Research objective | Strict hedged pricing discrepancies and document/network expected repricing, scored separately | Confirmed |
| Horizons and risk settings | Mechanism-led candidate ranges, economical screening, nested validation and stress testing | User delegates research/optimization; researched initial grid below |
| Market-data budget | Exact quotes, durable reservations, necessary Databento acquisition | Authorized below $250 total; $249.99 conservative project ceiling |
| Primary deliverable/query format | Versioned dataset with CSV/JSONL exports and a queryable local snapshot | Recommendation; interview later |
| Disclosed aggregate versus individual loans | Store both at their disclosed granularity; never invent loan-level detail from totals | Recommendation; interview later |
| Paid/model interpretation | Rules first; any targeted inference needs an explicit budget and a demonstrated benefit | Interview later |
| Accuracy, minimum coverage and review workload | Agree per issuer/document category using a frozen benchmark | Interview later |
| Refresh cadence | Incremental refresh after reliable snapshot/resume behavior is verified | Interview later |
| Historical issuer eligibility | Preserve dated eligibility/security classifications, entrants/exits and name changes | Required by confirmed all-REIT historical scope |

Neither elapsed time nor a recommended option is a user answer. The final plan will replace open choices with recorded decisions.

## Global constraints

- User now authorizes implementation, quality-audited source expansion and necessary Databento purchases below $250. A recurring subscription or trading authorization is not implied. Heavy offline research uses the authorized remote compute route.
- Assume OCR works; evaluate financial interpretation and source coverage instead.
- Preserve original source files, original 14-assertion gold key and prior run outputs.
- Public reports provide disclosed activity, not every company bank transfer.
- Keep original currencies and exact periods; FX conversion and derived quarterly flows require separate decisions and provenance.
- CompanyFacts comparisons cannot become additional events or transactions.
- No automatic entity/instrument match based only on equal amounts, rates or similar names.
- Shared checkout has concurrent unrelated changes. Assign module ownership; no bulk staging, cleanup or shared-plan edits.
- One broker owns aggregate SEC traffic; proposed default is two requests per second across all workers/hosts. One publisher owns dataset publication.
- Company-document coverage and market tradability are separate. Keep an eligible issuer in the document dataset when its options/borrow/quotes are unavailable; mark its market test as unsupported rather than silently dropping it.
- Account size and acceptable loss are not discoverable investor preferences. Research can estimate feasible capital, stress losses and a risk/return frontier; the plan cannot infer a personal risk mandate by maximizing historical profit.
- Broad experimentation is permitted in development. Every attempted family/horizon/parameter choice enters a trial register; the final test is not used to retune them.

## Shared contract before parallel integration

The coordinator owns `src/reit_contracts.py`, contract fixtures and the resolved scope configuration. Settle schema and selection rules together:

1. **Observation:** immutable statement from a source, with issuer, legal entity/scope, amount, original currency/unit/scale/precision, concept, amount kind/basis, reporting period/as-of date, source hash, evidence locator and parser version.
2. **Instrument:** explicitly identifiable facility, tranche or individual loan. Aggregate portfolios remain aggregates. Party, agreement and instrument identifiers carry evidence.
3. **Link:** supported observation-to-instrument, instrument lineage or typed party relation, with status, evidence, rule/reviewer version and unresolved alternatives. Derived company intersections retain the IDs of their input relations and are stored separately.
4. **Event:** explicitly disclosed origination, draw, repayment, amendment, extension, refinancing or termination. A balance change alone is not an event.
5. **Time:** reporting/effective time, SEC acceptance, claimed publication, evidenced public availability, retrieval and backtest usability are separate. Collection time cannot masquerade as original publication time; acceptance is not proof of instantaneous public availability.
6. **Coverage:** acquisition, processing, interpretation and history-completeness statuses are independent. Account for missing history pages/exhibits and every parsing/resource/indexing limit.
7. **Views:** preserve all source assertions, but provide distinct policies for originally disclosed values, latest supported assertions and nonoverlapping reported flows. Annual and YTD amounts cannot be summed indiscriminately.
8. **Amendments:** supersession applies to supported affected assertions; a 10-K/A cannot silently replace every original debt fact.
9. **Entity:** stable internal identity, legal name/type, nullable CIK/LEI and evidenced aliases/parentage. Separate issuer, operating partnership, subsidiary, bank affiliate and trust; keep effective and knowledge dates plus unresolved alternatives.
10. **Exposure:** retain original currency, amount kind, gross/proportionate scope and allocation evidence. Syndicated facility capacity is not assigned in full to every lender; undisclosed shares remain unknown.
11. **Market observation:** independent instrument/security identity, historical contract definition, bid/ask/size/conditions, event/receipt timestamps and their meanings, corporate-action status and quote-age/latency policy. Exchange data timestamps do not establish historical receipt by this project.
12. **Experiment:** immutable universe/source/feature snapshot, mechanism, candidate family, horizons, selection/trial register, chronological partitions, processing/entry/exit clocks, cost/capital assumptions and separate track-specific outcomes.

Interface contracts will use the existing observation fields where possible:

```python
def build_inventory(scope: dict, metadata: list[dict]) -> dict: ...
def acquire_inventory(inventory: dict, run_state_path: str, policy: dict) -> dict: ...
def interpret_document(raw: bytes, document: dict, extracted: dict, policy: dict) -> dict: ...
def link_observations(observations: list[dict], agreements: list[dict], prior_links: list[dict]) -> dict: ...
def build_history(observations: list[dict], links: list[dict], events: list[dict], policy: dict) -> dict: ...
def publish_dataset(shard_manifests: list[dict], output_dir: str, policy: dict) -> dict: ...
def evaluate_dataset(dataset_manifest: dict, answer_key: dict, policy: dict) -> dict: ...
```

These are planned contracts, not existing callable functions. Each result includes its schema/version and source/implementation fingerprints. Inventory includes selected/excluded reasons and missing predecessor/agreement evidence. History workers can submit bounded evidence requests back through the acquisition broker.

## Cross-sector company relationships

The history lane owns planned `src/reit_entities.py` and `src/reit_relationships.py` alongside instrument linking. It must distinguish:

- Borrower, lender, administrative agent, guarantor, operating partnership, subsidiary, joint-venture participant, buyer/seller, refinancing counterparty, sponsor, servicer and trustee. A named agent is not automatically a lender.
- Direct disclosed interactions versus derived intersections. If two REITs use the same bank, store a shared-bank intersection supported by both edges; it does not establish money moving between the REITs.
- Instrument/transaction scope and allocated versus unallocated amounts. Portfolio totals, collateral values, retained interests and issued notes remain separate kinds of exposure.
- Relationship effective time versus when it became knowable. A later disclosure of an old agreement becomes a feature only after its verified availability, never retroactively.

Minimum entity fields: `entity_id`, `legal_name`, `entity_type`, nullable identifiers, evidenced aliases, `valid_from/to`, `known_from/to`, `resolution_status`, `candidate_matches`.

Minimum relationship fields: `relation_id`, `subject_id`, `object_id`, `relation_type`, nullable `instrument_id`/`transaction_id`, effective dates, availability/basis, evidence IDs, assertion status, rule version and superseded assertion ID. Derived intersections include input relation IDs and uncertainty.

Record directly evidenced counterparties outside the REIT industry, including private/foreign entities. Fetch narrowly relevant agreement/amendment/ownership/trust evidence through the broker. Record seed/hop/reason/budget/terminal state; do not recursively acquire every bank's entire history. Graph metrics are reconstructed from the evidence and identity resolutions available at the decision.

## Source validation and universe policy

The saved list remains exactly 15 entries. Treat it as a starting catalog; it is not a complete driver for all companies/history. Preserve numbered explanations and attach a dated validation register.

Each URL gets separate states for live access, expected content/issuer/document identity, cached-byte integrity, authority/relevance and known coverage. Save redirects, status/MIME, check time and source hash/receipt when available. A 200 response can be a landing page or access notice. A 403, robots restriction or tool error establishes an access limitation, not a dead source. Replacements require authoritative identity evidence and retain the original URL history.

The current Nareit directory is a discovery aid, not a complete historical US REIT membership list. Validate exchange listing, security class, documented REIT status/subtype, domicile, CIK and dated eligibility from primary evidence. Preserve entrants, delistings, mergers, aliases and excluded security rows. Do not equate SIC 6798, a current options list or current directory membership with historical eligibility. Establish opening loan context from pre-2024 evidence where necessary.

Validation outputs for this planning turn: `docs/reit-collection-integrity-2026-10-03.md`, `docs/reit-source-validation-2026-10-03.md` and a text register. The live audit normalized 181 original strings to 173 concrete source URLs, separating parameter templates and citation punctuation/duplicates. All 173 endpoints were attempted: 95 rendered content and 78 produced access/tool errors. These include one explicit AGNC 403 and a BXMT page-size cap; the remaining errors expose no HTTP status. The official AGNC context page additionally rendered and confirmed its presentation link. Rendered content is not equivalent to verified issuer eligibility, accurate financial statements or transport-metadata verification. Auxiliary research references are included in this broader inventory.

## Two separately evaluated research tracks

### Track 1: Strict hedged pricing discrepancies

Start research with same-underlying stock/options replication and supported option bound violations. Specify each actual hedge and its cash flows; American exercise, dividends, stock borrow/recall, funding, settlement, adjusted deliverables and fees can change a theoretical comparison. A parity residual alone is a candidate, not an executable arbitrage.

Futures enter only through verified listed contracts and historical definitions/liquidity. Current CME evidence identifies distinct real-estate index families XAR and RX/JR; the market-data report also cites the October 2024 RX/JR options-listing notice. These are not individual-REIT futures or exact hedges of every REIT. Product/advisory evidence does not prove quote liquidity throughout January 2024 onward. Exact basket/futures cash-and-carry requires dated constituents/weights and replication of the same underlying; single-company versus sector/rate-futures positions generally retain basis risk and belong in the relative-value/prediction track unless an exact hedge is established.

Use independent synchronized quotes, buy-side asks/sell-side bids, supported size, venue/condition filters, stale/locked/crossed quote checks and declared latency. Analyze leg/partial-fill risk rather than assuming simultaneous fills. Minute samples and trade bars can screen candidates; they cannot validate fleeting executable tick discrepancies. Missing borrow/dividend/execution evidence produces `candidate_only` or `unsupported`, not a positive strict-arbitrage conclusion.

Strict classification requires an analytical hedge/cash-flow bound over admissible exercise, dividend, settlement and financing states, with feasible intermediate cash requirements. A favorable finite stress sample is insufficient to prove arbitrage; use stress paths as additional operational tests. State every condition under which the payoff bound holds. Observed quote crossing is a modeled execution assumption until corroborated by order/fill evidence.

Score net executable edge per unit and committed capital, persistence, supported size, costs, financing/borrow, settlement/exercise contingencies and worst-case hedge failure. Separate model-screened discrepancies from paper/live fill evidence. Document features may explain candidate frequency/exposures; they do not replace the hedge proof.

### Track 2: Expected repricing and relative value

Use the broader strategy's dated financial-data sheet, prior guidance/expectations and loan/network exposure to forecast economically specified arrival/surprise/response. Evaluate pre-disclosure and post-disclosure decisions separately; only the latter may use the new release. An unscheduled-event predictor needs the contemporaneous eligible non-event risk set, not just retrospectively selected events.

Compare market-only, financial-only and combined financial/network models using identical dates, contracts, costs and capital. Add source and network ablations; ensure network additions improve results beyond duplicated observations or common sector/rate exposure. Begin with small interpretable baselines before expensive models. Keep stock, volatility, credit/rate, sector and basis-risk exposure visible.

Score forecasting calibration/error where applicable, net realized portfolio return on committed account capital, drawdown/tail loss, turnover, capacity and uncertainty. Positive P&L by itself is not evidence of information alpha or strict arbitrage. Use economically appropriate factor/hedge benchmarks and shared calendar-block uncertainty across related issuers.

## Historical timing, optimization and OOS policy

1. Backtest decisions begin January 2024. Collect the earliest necessary opening balances/agreements before then and sufficient later market outcomes for each eligible holding period. Labels whose exits have not occurred by the evaluation cut-off are excluded as immature and counted.
2. Keep `report_period_end`, `event_effective_at`, `sec_accepted_at`, `claimed_published_at`, `first_public_at` with evidence, `retrieved_at` and `backtest_available_at`. For unknown intraday public availability, use a predeclared conservative anchor/latency scenario or abstain. Date-only data needs an explicit next-session policy. Processing latency applies after availability.
3. Maintain separate extraction held-out cases and chronological financial OOS. Group duplicate releases, amendments and related instrument lineages for extraction evaluation. A fresh reviewer does not make previously examined financial dates untouched.
4. Propose 2024 development and 2025 chronological validation/walk-forward as a starting partition. Audit exposure to 2026 data before designating any 2026 portion as locked final OOS; if it has influenced design, report it as validation and reserve a later/prospective period. Freeze exact boundaries after horizons, label maturity and sample size are established.
5. The user permits broad horizon research. Use a financially motivated coarse family grid, screening cheaply before targeted quotes. Selection occurs within nested chronological development folds, with purging/embargo derived from overlapping label lifetimes, only past data in fit/normalization/graph construction, and an outer test of the entire selection procedure.
6. Log all tried models, horizons, features and thresholds. Adjust inference for selection/multiple comparisons; retain rejected/null results. Limit computational expansion by evidence of incremental value, not by silently forgetting failed trials. The final untouched test is run after rules are frozen; modifications require a new test period.
7. Estimate feasible capital from worst-case cash flows, borrow/assignment liabilities, margin, simultaneous positions, liquidation capacity and stress losses. Optimize only within predeclared constraints; show a feasible risk/return/capital frontier. Account size and acceptable drawdown cannot be identified from return-maximization alone.
8. Use raw actual futures contracts for execution/P&L, dated roll rules and corporate actions. Continuous adjusted histories may be features with an explicit construction policy; they cannot substitute for executable contract prices.

This policy controls and measures major sources of bias; it cannot promise zero bias. Exact grids, stress assumptions and data tiers will be supported by the independent economic/market-data research reports.

## Economic research adopted into the first experiment contract

See `docs/reit-arbitrage-economic-grill-2026-10-03.md` for primary sources, assumptions and the independent challenge/revision audit. These are initial research candidates, not already optimized values:

| Economic mechanism | Candidate outcome horizons | Primary test |
|---|---|---|
| Hedgeable replication/bound discrepancy | Immediate quote/leg completion; contractual settlement if held | Supported net payoff over admissible financing/exercise paths, rather than a favorable later market move |
| Newly disclosed financing/amendment surprise | 30 minutes, next session, 5 sessions | Move begins after evidenced availability and feasible processing/entry |
| Counterparty credit/refinancing transmission | 1, 5, 21 sessions | Material dated exposure adds information beyond market/sector/rate controls |
| Maturity/covenant exposure | 5, 21, 63 sessions | Slower reassessment survives carry, unrelated news and risk controls |

Holding horizon, option expiry and entry clock are distinct. Test economically supported combinations, not their unrestricted Cartesian product. Choose a primary horizon within development; all diagnostics/refinements stay in the trial register. Expand the grid only if the economic hypothesis and available data justify it. For a prediction available on the first January 2024 decision, obtain earlier training/warm-up inputs or use a fully prespecified rule; otherwise mark that interval unavailable for learned predictions rather than backfilling a later-trained model.

Map extracted facts to economic exposures before features: loan proceeds create cash and a liability; a loan balance is not profit. Floating-rate interest scenarios depend on reset dates, caps and hedges. Credit-loss scenarios distinguish exposure, default probability and loss severity. Futures hedge ratios require measured factor/yield sensitivity, not matching debt and futures dollar notionals. Shared counterparty names alone do not establish financial transmission.

For a simple exposure, use `quantity <= min(loss-budget/stressed-loss-per-unit, free-equity/initial-margin-per-unit, liquidity-capacity, borrow-capacity)` as a screening bound. The portfolio gate additionally requires positive equity above maintenance margin plus cash buffer across retained stress paths, funding for settlement/assignment and concentration limits. Margin is collateral capacity, not a loss cap or another fee.

Report hypothetical account-size breakpoints from indivisible lots, fixed costs, margin and capacity; do not label them recommended deposits. Show trading economics before and after recurring data/operating overhead, separately from one-time research/backfill expenditure. Compare constrained utility/tail-risk objectives and no-trade alternatives within training. Long-option, defined-risk spread, covered-equity, short-stock and unrestricted-short-option scenarios have different liabilities; reject infeasible scenarios rather than assuming investor permission or treating terminal spread loss as the largest intermediate cash requirement.

Stress issuer gaps, joint credit/REIT shocks, IV/skew changes, dividends, borrow recall, partial fills, halts, margin changes and futures cash calls using full nonlinear positions. Report a risk/return/capital frontier, uncertainty and failure cases. Exact personal tolerance and deployment permissions remain outside what backtest optimization can determine.

## Paid market-data research and cost control

See `docs/reit-arbitrage-market-data-plan-2026-10-03.md` for dated official provider sources. Prepare three priced alternatives: broad issuer coverage for screening, targeted synchronized quotes for specified experiments, and event-level quote/depth detail only where it resolves an actual execution question. Separate one-time historical orders from recurring monthly feeds and licensing.

Use the existing Databento/Massive plumbing where contracts fit, but create a fresh dated REIT security/contract manifest. Historical option data are charged by scope/volume under applicable provider terms; request exact dataset/schema/symbol/date estimates before acquiring. A prior CFO-study invoice cannot establish a whole-REIT quote cost. Existing subscriptions/credits are verified without exposing credentials.

Coarse screens, liquidity filters and exact-contract choices use only past data or a rule frozen in development. Outcome-dependent shortlisting cannot choose outer/final-test opportunities. Strict-arbitrage sampling includes preregistered ordinary/no-disclosure windows as well as disclosure windows; an event-only sample cannot establish general opportunity frequency. Publish denominators and missingness across the full issuer/date scope. OPRA event-level quote data help assess synchronization/age/persistence; they do not contain individual-order queues or prove this strategy's fills. Futures depth is a different dataset with its own evidence and cost gate. A frozen paper stream can measure order decisions and quote-based simulation; paper fills alone are still not observed broker live fills.

The user will supply a monthly ceiling; a one-time historical backfill allowance is a separate budget choice. No paid request is launched before the concrete order, rights and spending limits are settled. Market-data access/price snapshots are dated estimates, not a promise of coverage or liquidity.

## Compute and collection optimization

- Cache immutable bytes and extracted representations by source hash plus parser/version. Reuse verified native text/structured facts where present; use the assumed-correct OCR only when the chosen input requires it. Do not repeat OCR or reprocess unchanged filings.
- Preserve alternate HTML/PDF versions as provenance, group their common filing/assertion lineage and avoid treating duplicate representations as independent financial events or evaluation samples.
- Route JSON, XBRL, ordinary HTML tables/narratives and PDF text to compatible interpretation paths. An HTML exhibit failing an XML parser should be reported/routed explicitly; it cannot silently count as interpreted financial coverage.
- Acquire historical filing metadata before larger sources, follow materially relevant exhibits/predecessors, and record bounded omissions. Incremental requests use the shared cache/broker and durable checkpoints.
- Publish reusable indexed observations/relations rather than asking a language model to reread the entire document collection for every query. Rules/structured meanings precede targeted inference; any later model escalation needs a measured benefit and explicit cost limit.
- Screen market-data coverage cheaply, acquire exact contracts/windows under an outcome-blind policy, and refine a coarse development grid only when mechanisms/data support it. Broad scientific coverage does not require acquiring every option series or every parameter combination.
- Benchmark first-cohort time/memory/output sizes, then choose shard sizes and concurrency. Heavy offline processing/sweeps go to home-pc; acquisition and publication retain their single owners. Measure quality and full-scope missingness alongside compute saved.

## Four lanes in parallel

Four available concurrency slots mean three specialist workers plus the coordinator. The coordinator runs lane D and integrates the others. A fresh independent reviewer uses a slot after a worker completes; the plan does not assume unlimited simultaneous agents.

### Lane A: Companies, sources, history discovery and durable acquisition

**Owner:** acquisition worker. New modules: `src/reit_universe.py`, `src/reit_inventory.py`, `src/reit_acquisition.py`, `src/reit_run_state.py`; corresponding `tests/test_reit_*.py`. Coordinator alone changes existing collector wiring.

**Consumes:** scope configuration, current options/industry/CIK screens, source catalog and shared contract.

**Produces:** verified/date-aware issuer list, complete selected filing/document inventory, receipts, immutable cached sources and durable task states.

- [ ] Validate issuer CIK, security class, REIT subtype and dated eligibility from authoritative evidence; record exclusions and retain the options-overlap slice.
- [ ] Reconstruct historical entrants/exits and pre-2024 opening context. Separate document eligibility from dated options/futures/borrow tradability.
- [ ] Classify the 15 source entries by discovery, filing, supplement, agreement or conditional deal/property use. A static URL list is not a complete ingestion driver.
- [ ] Revalidate live availability/content identity and cached receipts/hashes independently; retain redirects, access limitations and source replacement history.
- [ ] Traverse historical submissions files for the chosen date range, include supported amendments, and account for referenced exhibits/predecessor agreements.
- [ ] Build one leased request broker/cache owner; workers submit fetch requests instead of creating independent SEC clients.
- [ ] Checkpoint task selection and attempts durably. Continue independent companies after ordinary failures; bound retries and pause aggregate requests on access rejection.
- [ ] Test historical pagination gaps, excluded securities, cache hits/offline operation, duplicate tasks, global throttling, interruption/resume and company failures.

**Gate:** every selected document has an accounted terminal state, receipt and hash; missing history/evidence remains visible. Discovery completeness is measured separately from acquisition success.

### Lane B: Financial meanings across tables and narratives

**Owner:** extraction worker. Own existing `src/reit_money_records.py`, `src/reit_pdf_money.py` and their tests; add `src/reit_table_money.py` and `src/reit_candidate_index.py`. Coordinate evidence-only table/fact changes explicitly. Coordinator alone changes analyzer wiring.

**Consumes:** cached sources, document metadata, shared contract and development examples. The frozen evaluation key stays outside runtime extraction.

**Produces:** observations with amount/year/unit/entity evidence, unresolved records, full bounded candidate locator index and explicit limit reports.

- [ ] Prioritize the unresolved disclosure families already present in the four-company corpus rather than building adapters from assumed formats.
- [ ] Route each retained source format explicitly and reuse cached native/structured/OCR representations; preserve unsupported coverage rather than treating every HTML exhibit as XBRL.
- [ ] Add supported quarterly/YTD table periods, additional cash-flow row forms, debt/loan schedules and explicit custom meanings using reviewed development examples.
- [ ] Distinguish debt principal, loan assets, carrying/fair values, collateral, notional amounts, commitment, unused capacity and actual cash movement.
- [ ] Extract borrower, rate and maturity only when tied to the same supported instrument/row; keep unknown attributes unknown.
- [ ] Extract typed parties and legal-entity scope with evidence; separate lender/agent/guarantor/trustee and disclosed syndicate shares from unknown allocations.
- [ ] Separate candidate indexing from excerpt display limits. Record enumeration limits/unindexed regions rather than claiming the index finds every financial assertion.
- [ ] Test quarter versus YTD, multi-table boundaries, units/signs, mixed currencies, entity/tranche separation, ambiguity and unsupported transformations.

**Gate:** each accepted value has amount-specific source evidence and required context. Unsupported shapes remain review items. Resource bounds remain visible in coverage.

### Lane C: Instrument histories and dataset publication

**Owner:** histories/data worker. New `src/reit_entities.py`, `src/reit_relationships.py`, `src/reit_instrument_links.py`, `src/reit_history.py`, `src/reit_dataset.py`, `scripts/export_reit_dataset.py`; corresponding tests. Develop against contract fixtures while A/B are being built.

**Consumes:** observations, agreement evidence, prior explicit links, filing inventory and coverage states.

**Produces:** instruments, sourced links/events, unresolved history cases, selection views and a versioned query/export snapshot.

- [ ] Link repeated explicitly identified agreements across 10-K, 10-Q and 8-K, while preserving tranches and legal-entity scope.
- [ ] Keep same-size facilities distinct without identity evidence; preserve candidate/rejected link alternatives.
- [ ] Store supported REIT/non-REIT typed relations and dated identities; derive shared-counterparty intersections separately with source-edge IDs and knowledge dates.
- [ ] Bound source expansion to economically relevant direct counterparties/agreements; retain discovery reason, hop depth, budget and omitted evidence.
- [ ] Apply effective-dated amendments/refinancing only when explicitly disclosed. Missing disclosure never establishes repayment or termination.
- [ ] Preserve source assertions and implement agreed original/latest/nonoverlapping-flow views without deleting comparative values.
- [ ] Return bounded missing-evidence requests through lane A and mark unresolved cases `history_incomplete`.
- [ ] Build a single leased publisher: verify immutable shards, stage a versioned snapshot, atomically publish the current-version pointer, retain old snapshots.
- [ ] Test cross-company nonmerges, scope/tranche nonmerges, partial amendments, comparative restatements, missing evidence, conflicting links and competing/crashed publishers.
- [ ] Test agent versus lender, operating-partnership borrower versus parent guarantor, same-name affiliates, unknown syndicate allocations, trust roles, mixed currencies, backdated later disclosures and graph features that update only after availability.

**Gate:** no unsupported accepted link/event, no double-counting in named aggregation views, and no mixed-version publication. Dataset formats remain an interview decision.

### Lane D: Independent benchmark, integration and scale controls

**Owner:** coordinator, with a fresh independent reviewer for label/leakage audit and final integration. Planned new `src/reit_evaluation.py`, `scripts/evaluate_reit_dataset.py`, contract/integration tests and versioned benchmark artifacts.

**Consumes:** retained source sample and outputs from A/B/C. Owns existing `scripts/collect_reit_financials.py` and `scripts/analyze_reit_money.py` integration points to prevent overlapping edits.

**Produces:** frozen development/held-out split, accuracy/coverage report, runnable integration, bounded batch/remote run manifests and promotion decisions.

- [ ] Partition real source cases by issuer/filing/disclosure family before adapter evaluation; reserve held-out cases and negative/ambiguous examples.
- [ ] Keep extraction evaluation separate from chronological financial OOS; group duplicate copies/amendments/lineages and audit previously inspected dates before claiming an untouched test.
- [ ] Freeze labels, evidence, field definitions and scorer. A fresh reviewer audits label correctness and leakage; root ownership alone does not make evaluation independent.
- [ ] Measure exact amount, sign, currency/scale, period, scope, meaning and link correctness separately from recall, abstention and document/candidate omissions.
- [ ] Wire the collector/analyzer through the shared broker and contract. Workers write isolated immutable shards; a single publisher combines them.
- [ ] Test crashes at each boundary, stale/corrupt caches, schema changes, retries, competing owners, incomplete inventories and complete processing with partial interpretation.
- [ ] Benchmark bounded offline processing before selecting shard sizes, process/memory limits or runtime estimates.
- [ ] Route genuinely large offline jobs to home-pc through detached tmux with portable relative paths, explicit snapshot/shard IDs, logs and hash-checked returned artifacts. Remote workers make no SEC requests; unavailable Tailscale is reported rather than bypassed.
- [ ] Run staged cohorts and incremental updates only after the agreed quality/coverage and operational gates pass. Refresh schedule follows the user's decision; planning does not create an automation.

**Gate:** source/model/parser versions and all limitations are reproducible. No quality pass/fail claim is made before the human agrees acceptance thresholds.

## Second wave: Market data and the two financial tests

Reuse the three worker slots after the document/network contract and first integration are stable. This wave is not launched during planning. Planned paths below are proposals; check concurrent work before creating them and integrate with existing market-data/strategy modules where their actual contracts fit.

| Lane/owner | Planned responsibility and paths | Can work independently on | Dependency before scoring |
|---|---|---|---|
| E: market-data worker | `src/reit_market_inventory.py`, `src/reit_market_quotes.py`; historical security/contract maps, quote/borrow/dividend/margin inventories and priced requests | Provider coverage/cost estimates and dated contract fixtures | Approved budget, dated universe, exact family/time requirements, acquired independent quotes |
| F: strict-arbitrage worker | `src/reit_arbitrage.py`; cash-flow/hedge definitions and bounded discrepancy detector | Economic bound fixtures, exercise/assignment/financing cases, candidate schema | Verified instruments, synchronized prices and shared execution/capital ledger |
| G: prediction worker | `src/reit_signals.py`; interpretable financial/network features, pre/post baselines and nested horizon selection | Past-only feature fixtures, non-event risk set, baseline experiment definitions | Published point-in-time observations/network plus market coverage and frozen chronological design |
| Coordinator | `src/reit_execution.py`, `src/reit_backtest.py`, `scripts/backtest_reit.py`; shared costs/capital, OOS runner and integration | Scenario ledger, label maturity, trial registry and immutable experiment manifests | All dependency gates; independent economic/leakage review before final scoring |

- [ ] Price full-coverage versus staged acquisition using vendor estimates; distinguish one-time history costs, monthly refresh fees, licensing and broker access. No purchase before the spending limit and exact quote are approved.
- [ ] Validate quote provenance/age/conditions, independent underlying prices, adjusted option deliverables, historical delisted contracts, futures definitions/rolls and explicit missingness.
- [ ] Predeclare hedge cash flows, fill/latency scenarios, financing/borrow, dividends, fees, margin and stressed assignment/partial-fill/recall cases. Require a favorable supported lower-bound net payoff before marking a strict candidate executable.
- [ ] Implement pre-disclosure and post-disclosure forecast baselines separately, with source/network ablations and common-risk comparisons. Do not initialize a pre-release financial-data sheet with the release it is predicting.
- [ ] Run a coarse mechanism-led horizon/threshold search within development folds, refine only promising supported families, log all trials and freeze the resulting selection procedure before the outer evaluation.
- [ ] Simulate overlapping positions in one capital ledger, including variation margin/collateral, funding, available borrow, assignment liabilities and forced liquidation. Per-event return rows cannot be summed into an account equity curve.
- [ ] Report each track's coverage, failure/abstention counts, net economics, uncertainty, capacity and capital/risk frontier. Keep prospective opportunities and hindsight theoretical candidates separately named.
- [ ] Route multi-year simulations/parameter sweeps and large quote processing to detached home-pc tmux jobs with immutable offline input manifests and hash-verified returned results. Broker/vendor acquisition remains controlled and checkpointed.

**Gate:** a backtest is scoreable only after data support and timing/contract/selection rules are frozen. If execution/borrow evidence is insufficient, publish the gap and candidate-only analysis. A final OOS result is never used to choose new parameters under the same test label.

## Sequence and dependency gates

1. **Interview and contract:** scope/history/network and the two-track objective are settled. Complete economic/market-data research, record the spending ceiling, resolve essential acceptance/query choices and freeze shared schema plus selection/supersession/timing fixtures.
2. **Parallel construction:** A acquires/inventories; B interprets development sources; C builds histories/publication against fixtures; D freezes the benchmark and prepares integration.
3. **Four-company integration:** run the full path on the already retained corpus and preserve the original PDF sample as a regression anchor. Feed demonstrated missing evidence back through A.
4. **Fresh review and measured promotion:** audit held-out results, false automatic classifications, unresolved workload, omitted content and crash recovery. Fix failures before advancing.
5. **Broader dated cohorts:** expand all validated REITs in measured batches, publish document/history/market coverage and archive every snapshot. Start with the four retained issuers plus Realty Income as regressions, then stratify by equity/mortgage subtype, disclosures and data availability; measure a small cohort before choosing later batch sizes.
6. **Market research construction:** run E/F/G plus coordinator in parallel against agreed contracts, then integrate on a supported bounded cohort. Price/acquire missing data only under the spending decision.
7. **Development and validation:** run economically constrained nested chronological experiments on home-pc; audit leakage, all attempted choices, costs, label maturity and feasible capital before freezing the final rules.
8. **Final OOS/prospective evaluation:** evaluate untouched eligible dates once; publish both tracks and negative results separately. Any later optimization starts a new version with a new evaluation period. Refresh/scheduling follows a later explicit cadence decision.

Histories can be developed in parallel against fixtures, but real histories require real observations and identity evidence. Integration and publication have dependency gates; all tasks cannot safely write to the same outputs at once.

## Second critique and adopted revisions

The company-network review and market/OOS facts changed the draft further:

- Added legal-entity identity, typed roles and allocated exposure; shared lender intersections are derived evidence, not direct cash movements.
- Bounded non-REIT expansion and added missing-agreement feedback rather than recursively collecting every counterparty.
- Replaced an acceptance-time trading shortcut with evidenced public availability, latency and date-only session rules.
- Separated interpretation held-out cases, chronological prediction OOS and strict-arbitrage execution evidence.
- Added dated historical issuer/security membership, label maturity and a contamination audit before assigning 2026 as an untouched holdout.
- Added independent synchronized equity/options/futures prices and a shared execution/capital ledger; the unrelated CFO study is not REIT market coverage.
- Added a second parallel wave for market data, hedge proofs and prediction baselines within the actual four-slot limit.
- Treated broad optimization as a recorded selection procedure evaluated on untouched data; investor risk tolerance is not a free parameter selected by historical profit.

The independent economic grill/final review additionally required outcome-blind quote acquisition, ordinary-window arbitrage controls, distinct history/monthly spending gates, and analytical hedge bounds rather than finite-stress proof. Those changes are incorporated above. OPRA quote information is explicitly distinguished from venue order queues and observed fills.

## First critique and revisions

Independent planning review identified and revised these issues:

- **Schema alone did not prevent double counting.** Added named original/latest/nonoverlapping-flow views and assertion-level supersession rules.
- **A complete download batch did not guarantee a complete loan history.** Added historical/agreement inventory, bounded evidence feedback requests and `history_incomplete`.
- **One completion flag hid financial gaps.** Split acquisition, processing, interpretation and history statuses and account for indexing/resource limits.
- **Single broker/publisher were unenforced policies.** Added leases, durable attempts, isolated shards, staged snapshots and atomic publication/recovery tests.
- **Coordinator-authored labels were not independent.** Added frozen held-out labels/scorer plus fresh leakage/label review.

## Sources and interview method

- [Published grill-me wrapper](https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md) invokes the [grilling interview](https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md). This is a remotely read skill, not a claim of local installation. Questions are settled in dependency-aware rounds; user decisions remain pending until answered.
- [SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data): published ceiling is ten requests per second; this plan proposes one shared two-per-second budget and declared contact headers.
- [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces): historical submissions files extend the recent history; CompanyFacts provides a limited standard/entity-wide view. Original filings remain necessary for custom and detailed observations.
- [SEC webmaster FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions): acceptance and website availability differ; SEC does not publish an exact first-availability timestamp. This requires explicit availability/latency assumptions in historical replay.
- [Options Industry Council: put/call parity](https://www.optionseducation.org/advancedconcepts/put-call-parity): replication relationships depend on dividends, financing, exercise and transaction/borrow constraints. This supports screening; each proposed real trade still needs a full cash-flow and execution test.
- [CME real-estate sector futures](https://www.cmegroup.com/markets/equities/select-sectors/e-mini-sp-real-estate-select-sector-index.contractSpecs.html): the described exposure is a sector index including equity REITs and other real-estate companies. Historical contract definitions and liquidity remain acquisition gates; the fetched static page did not expose numeric specifications.
- [CME product slate](https://www.cmegroup.com/markets/products) and [October 2024 RX/JR options notice](https://www.cmegroup.com/content/dam/cmegroup/notices/ser/2024/10/ser-9441.pdf): distinguish Dow Jones real-estate index futures from XAR and establish dated product evidence. Study-period contract/quote availability is still checked individually.
- Local broader-strategy context: `docs/strategy-research-review-2026-10-03.md`. Keep financial-data expectations, pre-release forecasts and post-release surprise/response tests distinct.

## Completion definition to settle through grilling

Dataset completion requires a validated dated universe, an accounted selected inventory, reproducible observations/loan histories/company relations, accepted interpretation/coverage thresholds, useful exports and verified resume behavior. Research completion additionally requires priced and supported market coverage, frozen economic/execution/selection rules, sufficient matured outcomes and separately reported untouched OOS results. It does not require finding profitable arbitrage: a reproducible null result or unsupported-market gap is a valid research outcome. Unresolved cases remain visible; undisclosed bank movements or individual loans are not invented.

## Reviewable decisions for the next execution phase

- Adopt the two-wave ownership plan and versioned CSV/JSONL plus SQLite snapshot proposal.
- Keep individual and aggregate disclosures at their original granularity; unresolved links, unknown allocations and access gaps remain queryable.
- Use the researched mechanism grid and hypothetical capital/frontier scenarios for development, then freeze each chosen research protocol before final evaluation.
- Build/validate the dated universe and small first historical cohort before selecting larger batch sizes or quoting all-chain data.
- Agree the concrete interpretation benchmark/promotion thresholds after its stratified sample and error costs are visible; a successful collection alone is not promotion evidence.
- Obtain the monthly and separate historical-data spending ceilings, then present exact provider order estimates/rights before any paid acquisition.
- Resolve deployment permissions/personal loss tolerance only if moving from research to a trading mandate. None is inferred from this plan.

These are proposals to review, not a record of approved implementation or an assertion that every grilling branch is closed.
