# Evaluation and risk

Universe: live forecast/portfolio helpers and registered numerical diagnostics; planned risk/regime-to-order adapter. Status: partial.

## Owning source

Post Benchmark evaluate.py::evaluate_forecasts, trials.py, portfolio.py::replay_portfolio; Lattice registered comparison code/configs. Research mandate: net growth within hard risk limits, compared asset-specific profiles.

## Contract and invariant

Forecasting, trade selection, sizing and execution are separate. Portfolio replay consumes frozen orders with side/quantity/multiplier; it is not the forecast policy generator. Regime-driven forecast adaptation and risk gating/sizing are separately registered challengers.

Compare simple mean/zero/history/factors with context-only, Lattice-only and combined features on matched opportunities. Text fragments, contract variants and repeated strategy rows do not create independent economic events. Preserve no-edge/no-trade findings.

## Impact and frontier

Target/split changes affect forecast comparisons and promotion. Risk-policy changes affect entry/size/exposure and require exposure-matched controls; they must not silently change the forecast experiment.

No accepted forecast-to-order policy adapter or complete options/futures lifecycle is established by this map. Protection comparator is explicitly gated/unimplemented in current portfolio helper. Numeric mandate/instrument permissions remain human decisions; research profiles are not approved capital allocation.

Diagnostic replay → eligible forecast study → executable portfolio replay are different gates. A graph, software tests or a correct direction prediction establishes none of the later economic claims alone.
