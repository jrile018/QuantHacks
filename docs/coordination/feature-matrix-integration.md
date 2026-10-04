# Feature matrix in the shared solution

Owner: Track work across project chats. Design clarification: 2026-10-04 UTC. This records source-inspected implementation and the remaining acceptance boundary; it adds no runtime implementation or economic qualification.

## Purpose and placement

A feature matrix is the decision's information snapshot: what we knew about a company or instrument, when we could use it, and why each value is included or missing. It belongs after retained source evidence, dated identity and availability checks, and before forecast fitting/evaluation. It is an input to the company benchmark and forecast; it is not itself a trading signal, target or portfolio return.

Use this sequence:

1. Retain raw evidence, revisions, hashes, rights and quarantine.
2. Produce dated financial, industry, text and market observations with exact definitions.
3. Map the required observations through a reviewed adapter into the existing canonical registry and decision-time FeaturePanel.
4. Fit/evaluate registered baselines and challengers on matched eligible opportunities.
5. Evaluate a separately frozen forecast-to-order/risk policy with executable prices and the shared cash ledger.

A pre-release panel uses only information available at that decision. Released text can enter a separate post-release decision after its evidenced usable time; it cannot revise the earlier snapshot. Scheduled issuer rows must include eligible firms/dates without later news. Market/futures scope remains distinct rather than duplicating macro data as issuer evidence.

Why here: upstream placement preserves provenance and prevents hindsight; one central eligibility gate gives models comparable inputs; downstream separation allows correct forecasts to be rejected when prices/costs make trading unattractive.

## Existing producer and canonical consumer

| Component / owner | Existing contract | Acceptance limit |
|---|---|---|
| Benchmark: src/feature_matrix.py::build_matrix | Inputs: decisions, long observations, declared feature names. Outputs: wide matrix rows and long cell provenance | Producer snapshot; not the canonical execution availability gate |
| Benchmark: financial_validation_bridge.py + export_native_canonical_features.py | Native long observations, native registry and source-hash-locked invocation of Post modules | Producer readiness smoke uses long observations; it does not import matrix.csv |
| Post Benchmark: research_validation/features.py::export_features | Canonical decisions + observations + registry -> decision_id rows with features, lineage and missing_reasons | Exact registered unit/scope/period/source, identity/rights and observed or explicit replay availability |
| Post Benchmark: financial_handoff.py::import_financial_handoff | Reconciled evidence bundle -> candidate observations/registry/audit | Separate path limited to four instant entity USD GAAP tags; fixture/bundle acceptance is scoped |
| Post Benchmark: evaluator and portfolio layer | Paired targets/forecasts, then independent order/cost/cash replay | A feature export is neither a forecast result nor an executable portfolio backtest |

Benchmark's implemented wide row key is (CIK, decision_timestamp_utc, horizon_id, feature_version). CIK is zero-padded to ten digits. Long observations carry feature_name, value, unit, source_id, source_record_id, source_url, period_end, public_at_utc, retrieved_at_utc, valid_from_utc, definition_version and quality_status. The source value remains a string in this producer.

The producer chooses a same-CIK/name observation with public_at_utc strictly before the decision and valid_from_utc at or before it, selecting the latest public version. It emits a status per cell plus provenance. Matrix feature_version and observation definition_version are distinct. Missing/not-yet-published/unmatched/source-error values do not become zero.

**Important implementation boundary:** retrieved_at_utc does not gate this producer selector; the basic matrix has no received/processed/assumed-availability fields and its allowed-name list is not the canonical typed-unit registry. The consumer must validate values/units and require actual receipt/processing or a registered historical replay basis. A public date or retrieval timestamp alone does not establish trading readiness.

## Adapter mapping to freeze for each accepted run

Do not add another registry or silently rename sources. The source-inspected paths currently name sec-native-xbrl (Benchmark bridge), sec_as_filed (general Post config), and benchmark_native_as_filed (Post bundle importer). These names can coexist in distinct routes. They must not be assumed equivalent.

The packet and consumer capsule must pin:

- Exact chosen route: native bridge readiness smoke, reconciled bundle importer, or a newly reviewed wide-matrix adapter.
- Original producer row/record IDs -> canonical decision_id, dated issuer/security/instrument and scope.
- Feature/source IDs, definition/formula versions, unit/currency/scale, period/amount kind and mapping/registry hash.
- Raw source and parser hashes, quarantine/adjudication state and value/null reason.
- First-public, receipt, processing/effective availability and observed-versus-replay basis, without inventing unknown clocks.
- Eligible/excluded counts and reasons, consumer source/config hashes and actual acceptance receipt.

The source trace confirms the producer smoke invokes canonical code with its own native registry. It does not confirm an accepted general matrix CSV import. A native fixture diagnostic hard-setting unknown availability/false eligibility is also not that acceptance.

## Grill iterations and resulting checks

1. **What does a row predict?** Resolve from the row key and schedule, not the future filing. Keep a decision/risk set and separate independently available labels. More cells/strategies/horizons do not create more independent company events.
2. **Can matrix.csv simply become the model input?** Current path says no direct import is established. Reuse long observations and Post's canonical FeaturePanel; preserve the wide export as a producer/debug view. Any later wide adapter needs an explicit accepted mapping.
3. **Does earlier public_at prove we could act?** No. Consumer eligibility also needs evidenced observed processing or registered replay latency, exact identity and source permissions. Preserve unknowns.
4. **Should every source block the first pilot?** No. Start with the smallest qualified feature/asset slice and a simple registered baseline. OCR, industry extensions, odds, geometry and regime challengers enter separately, evaluated on the same eligible rows against that baseline. Frozen transformations fit only the training fold; new families must show incremental forecast and after-cost value.

These are repository/evidence-resolved branches, not fabricated human answers. Existing human choices already specify a small validated costed slice first and an honest no-trade result for a valid negative comparison. Numeric risk and instrument choices stay unresolved.

## Intuitive output and completion

Use the existing expectations-card plan: a company/decision card shows financial condition, dated industry exposure, market expectations, feature freshness, lineage and exclusions. Present observed values, frozen predictions and later outcomes separately. A coverage view explains why a feature cannot be used; source record counts are not sample sizes or trade readiness.

Completion for this boundary requires a tiny accepted real producer -> consumer fixture and disconfirming cases (future/revised information, wrong unit/definition/scope, unknown availability, quarantine, duplicate/conflicting values and unmapped identity), with exact mappings/hashes and explicit exclusions. It can finish diagnostics-only while economic gates remain open. The first economic milestone still needs eligible observations, matched tradable quotes, lifecycle/cost/cash/risk evidence and the registered comparison.

## Source navigation

Financial owner checkout: C:/Users/johnp/.codex/worktrees/point-in-time-feature-matrix/QuantHaxs.
Read README.md's point-in-time foundation, docs/feature-matrix-readiness.md, docs/sec-facts-matrix.md, src/feature_matrix.py, src/financial_validation_bridge.py and scripts/export_native_canonical_features.py.

Canonical owner checkout: C:/Users/johnp/.codex/worktrees/8k-cross-asset-validation/QuantHaxs.
Read configs/feature_sources.json, src/research_validation/features.py, financial_handoff.py, clocks.py and records.py. These are local managed-checkout implementations; source presence is not merged GitHub state or validated economic runtime.

Shared routing: [architecture contract](architecture-contract.md), [features and targets](objects/features-and-targets.md), [first backtest](processes/first-backtest.md), [strategy plan](../superpowers/plans/2026-10-03-strategy-validation.md).
