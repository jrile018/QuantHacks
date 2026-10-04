# Options market learning design and implementation plan

This build learns four supervised targets: call and put midpoint premium percentage
changes, and call and put after-cost long-option returns. A separate derived choice
compares predicted call return, put return and a zero no-trade payoff. Wording
annotations and OCR are inputs only after independent calibration; neither supplies
market outcomes. Existing document reports remain diagnostic and are not automatically
eligible feature exports.

## Frozen experiment

Select contracts from synchronized quotes available at the decision, using one shared
expiry 90–180 calendar days away nearest 120 days (earlier expiry breaks ties).
Choose the call nearest 105% of contemporaneous spot and put nearest 95%; smaller
strike, then contract ID, breaks ties. Select each snapshot's latest valid quote
available by decision, then freeze the selected contract IDs. Entry is the first
valid synchronized snapshot strictly after decision in an options session. Both legs
must be available in that snapshot. Exit uses the last valid synchronized snapshot
at or before the close of the next supplied options session after the entry session,
within the configured age bound. Never skip that session because a later quote is
more convenient. Use the same selected contracts at exit.

Snapshots use a shared `snapshot_at_utc` anchor while preserving original per-leg
option SIP and underlying timestamps. Each source tick must be at or before the
anchor and within the configured age bound; leg-to-leg skew is therefore bounded
by the same age limit. The snapshot becomes available only after its constituent
records are received. Never relabel source ticks to manufacture synchronization.
If `snapshot_at_utc` is omitted, quote timestamp is the anchor, suitable only for
sources whose records actually share that snapshot time. Executable exit records
must be received by session close. Delayed quote receipt excludes the executable
label. Optional event `label_available_at_utc` preserves later target construction
availability; quote freshness is assessed at session close.

Each premium change is exit midpoint / entry midpoint − 1. After-cost return is
`(exit_bid * multiplier - exit_fees - exit_slippage_cost - capital) / capital`,
where `capital = entry_ask * multiplier + entry_fees + entry_slippage_cost`.
Costs are cash per one-contract transaction in the declared currency, not premium
points. Midpoint changes and after-cost returns are reported separately.

## Data contracts

The CLI accepts CSV or JSONL tables; JSONL preserves explicit numeric types. Missing
numeric features use null/empty plus a missing reason, never a manufactured zero.
All timestamps require an explicit timezone. Feature-source timestamps, including
public, receipt, processing and effective start, must be at or before decision;
anticipation features may not reference the target accession and public time must
be strictly before decision. Industry and regime observations obey identical rules.

- Events: `event_id`, `event_group_id` (one economic event including amendments),
  `cik`, `security_id`, `decision_at_utc`, `mode` (`post_release` or `anticipation`),
  `target_accession` (required in anticipation), `currency`, `deliverable`,
  `mapping_evidence`, `mapping_public_at_utc`, `mapping_receipt_at_utc`,
  `mapping_processing_at_utc`, `mapping_valid_from_utc`, `mapping_valid_to_utc`.
  Optional `label_available_at_utc` records target construction/availability after
  exit; it cannot precede exit or outcome receipt and is enforced at fold cutoff.
  Use ordinary scheduled no-event rows too for anticipation. Mapping evidence is a
  source reference, not a boolean declaration. Deliverable must identify the actual
  shares/cash deliverable; adjusted contracts require correctly dated mapping.
- Features, long form: `event_id`, `feature_name`, numeric `value` or null,
  `missing_reason`, `source_id`, `source_record_id`, `source_url`, `definition_version`,
  `public_at_utc`, `receipt_at_utc`, `processing_at_utc`, `valid_from_utc`,
  `valid_to_utc` (optional), `accession` (optional). Exactly one eligible observation
  per event/feature is required; resolve historical versions before export.
- Quotes: `quote_id`, `snapshot_id`, `security_id`, `contract_id`, `option_type`,
  `strike`, `expiry`, `timestamp_utc`, `snapshot_at_utc`, `receipt_at_utc`, `bid`, `ask`, `bid_size`,
  `ask_size`, `multiplier`, `currency`, `deliverable`, `underlying_price`,
  `underlying_timestamp_utc`, `underlying_receipt_at_utc`. A synchronized snapshot
  has one quote per contract and a common snapshot anchor and underlying as-of
  observation/value. Original option timestamps can differ. Receipt times determine
  when the snapshot can be used. Quote
  IDs and contract terms must be stable and unique; no daily bars are accepted.
- Sessions: `session_id`, `open_at_utc`, `close_at_utc`, `calendar_source`,
  `calendar_version`. Supply the complete ordered options trading calendar spanning
  decision/entry/exit, including holidays and special closes. This importer checks
  structural consistency, not external completeness of the vendor calendar.
- Registry JSON: `{ "features": [{ "feature_name": ..., "source_id": ...,
  "definition_version": ..., "role": "predictor", "independence_evidence": ... }] }`.
  Review formulas without future outcomes; source references and formula versions
  are required. Register fixed numeric industry/regime encodings ahead of evaluation.
- Provenance JSON: `quote_data_kind` (`historical_bid_ask` or `synthetic`),
  `quote_provider`, `quote_provenance_reference`, `feature_provenance_reference`,
  `calendar_provenance_reference`, `experiment_id`, `experiment_frozen_at_utc`.
  Evidence records are user supplied assertions requiring independent vendor audit.
  Synthetic data can exercise software but can never fit an accepted model.
  Preserve `receipt_basis`, `processing_basis` and `availability_assumptions` when
  constructing a historical replay. A SIP exchange timestamp does not establish
  actual historical receipt. Today's downloaded/processed features fail an old
  decision cutoff unless a separately documented replay assumes a historical
  acquisition/processing latency; do not present assumed times as observed history.

## Temporal split and fit

Freeze ordered train-end, validation-end and final-test-end timestamps before
inspecting heldout outcomes. The protocol freeze timestamp may be today's timestamp
for a retrospective study and must be no later than the actual evaluation time.
Models are labeled `retrospective_not_historically_deployable`; backdating the freeze
is unnecessary. All rows from an event group stay in the fold containing the group's
latest decision. Rows outside that fold's decision bounds are purged. A label is
eligible only when exit quote receipt and exit time are available by the fold end.
Purge train/validation rows whose entry-to-exit label interval overlaps any later
fold interval, and optional embargo seconds before the later interval. Record
every exclusion. No random split is provided.

Fit median imputation, missing indicators and standardization on train only. The
first baseline uses train mean targets; the second is multi-output ridge regression.
Choose mean versus ridge and regularization using validation mean squared error
across the four targets. Final test is evaluated once for the selected model.
Export JSON preprocessing statistics, coefficients, target order, provenance,
split IDs and separate metrics for mean, no-trade and the selected model. Do not
refit on validation/test. Direction, class accuracy and descriptive mean realized
after-cost return are distinct from a portfolio backtest. No Sharpe or profitability
claim is supported. Version experiment IDs and retain each run; never reuse the final
test for feature/model tuning. The CLI refuses to overwrite an existing result and
atomically reserves a heldout cohort/window fingerprint before test evaluation in
`data/processed/options_learning/holdout_ledger`. Changing experiment names does not
reset the same holdout. A serialized ledger overlap check also rejects reuse of
any previously reserved security/event group or security/decision pair even when
the new cohort drops rows, provider name changes, or window bounds differ. Retain
this ledger across all trials. Reservations persist
if scoring fails, conservatively requiring review. The ledger is a local guard;
changing its path, deleting it, changing cohort/window identifiers or calling the
Python API directly can bypass it. It cannot prove that an analyst never inspected
heldout data elsewhere. No automatic override is provided.

## Run and inspect

```powershell
.venv/Scripts/python.exe scripts/train_options_model.py `
  --events path/to/events.jsonl --features path/to/features.jsonl `
  --quotes path/to/quotes.jsonl --sessions path/to/sessions.jsonl `
  --registry path/to/registry.json --provenance path/to/provenance.json `
  --config configs/options_learning.json --output data/processed/options_learning/audit-run
```

Add `--fit` to explicitly request fitting and final evaluation after a real-data
audit. A run writes `audit.json`; a successful fit also writes `model.json`.
Blocked fitting writes `failure.json` with a specific reason and returns exit code
2. No forecast is emitted by the existing document-analysis report. The fit artifact
contains `model`, `train_mean_baseline_model`, validation candidates, selected-model
test metrics, train-mean test metrics, split IDs, purges and input SHA256 values.

Default `configs/options_learning.json` freezes training through 2024-12-31,
validation through 2025-12-31 and testing through 2026-09-30. The versioned
`research_cash_costs_usd_v1` assumption charges USD 1 in fees plus USD 2 cash
slippage at entry and again at exit for each one-contract option position; these
are research assumptions, not observed execution costs or a guarantee of conservative
costs. Underlying/option quote age is at most 60 seconds and spread/midpoint at most
0.3. All instrument currencies must match the cost currency. Change and version
assumptions before inspecting heldout outcomes, and test actual broker/vendor coverage
and cost sensitivity outside the final test. Minimum distinct event groups are 30
train, 10 validation and 10 test, with at least two train choice classes. These small
software gates do not demonstrate adequate statistical power.

Python API:

```python
from src.options_learning import build_dataset, split_dataset, train_model, predict
dataset = build_dataset(events, features, quotes, sessions, registry, provenance, config)
splits = split_dataset(dataset['rows'], config)
# Use the CLI for its persistent final-test reservation guard.
fit = train_model(dataset['rows'], config, evaluate_test=False)
predictions = predict(fit['model'], {'registered_numeric_feature': 0.2})
```

Prediction keys must match the complete registered training schema; use `None` for
reviewed missing observations. Freeze industry/regime numeric encodings in the source
registry. The importer never reconstructs current industry membership into the past.
`tests/test_options_learning.py:fixture` supplies complete hand-computed table examples
for software development; those records are synthetic and fitting refuses them.

## Implementation plan

Ownership is limited to `src/options_learning.py`, `scripts/train_options_model.py`,
`tests/test_options_learning.py`, `configs/options_learning.json`, this document,
and `requirements-training.txt`. Other agents are working in the repository.

1. Write failing dataset tests for contract ties, first entry after decision,
   next-session close, cash-cost math, late feature timing and absent actual quotes.
   Implement strict parsing, dataset auditing and target construction; rerun tests.
2. Write failing split and model tests for group purity, overlapping label purges,
   label availability, train-only imputation, insufficient samples/diversity and
   synthetic fitting refusal. Implement NumPy ridge (lazy import), JSON prediction
   and validation selection; rerun tests. NumPy already exists in the project venv.
3. Write failing CLI tests for audit output and fit refusal, implement CSV/JSONL
   loading and explicit output directories, run the focused suite and report gates.

No heavy training or installation is performed. Actual multi-year training runs are
coordinated by the parent task on remote compute. Current repository market data
lacks the required historical synchronized bid/ask outcomes, so this change builds
the pipeline and identifies blockers rather than producing a market-trained model.
An actual API access probe has returned historical option bid/ask records; acquiring
the full paired entry/exit dataset and point-in-time features remains necessary.

Implementation verification: the focused suite covers pricing math, asynchronous
as-of synchronization, quote/underlying staleness, late target receipt, future features,
mapping and currency/deliverable gates, event grouping, embargo, train-only transforms,
class/sample gates, synthetic refusal, JSON prediction, CLI audit and holdout reuse.
Run `.venv/Scripts/python.exe -m unittest discover -s tests -p test_options_learning.py`.
These are software fixtures, not market training or an options backtest.

Train-only preprocessing follows the [scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).
Multiple premium drivers are described by the [Options Industry Council](https://www.optionseducation.org/referencelibrary/faq/option-price-behavior).
