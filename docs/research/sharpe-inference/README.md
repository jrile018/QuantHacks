# Sharpe return-contract research probe

This bounded prototype checks the input needed for later Sharpe inference. It is separate from a ledger adapter, an accepted strategy backtest, calibrated 95% inference and a full Monte Carlo engine. Every result remains unreportable as economic performance; the primary confidence interval is null.

The existing replay in Post's canonical checkout reports account values after trade events. Its intermediate marks use last fills or settlements; it does not yet supply the accepted regular marked account-return panel this statistics plan requires. The data/date audit also reports that the saved wording packet is from early 2023 while the newer frozen protocol uses 2024. Those upstream issues remain with Post and the audit owner.

The human's USD 1m account, long/short permission, maximum 100% gross absolute exposure, equally sized eligible positions and zero idle-cash income are research policy choices. Required actual dividend/action cash and short expenses still belong in account equity and must be attributed. This probe does not calculate those cash flows or fill orders.

## What this slice checks

The caller must supply periodic net account returns and matching reference returns in decimal fractions, explicitly dated UTC valuation intervals, the exact expected valuation calendar, the annualization convention and provenance/status fields. The checker must retain missing, stale, bankruptcy and undefined-variance reasons. It must not remove inconvenient rows, infer a business-day grid, fill missing reference rates with zero or turn caller-provided acceptance flags into verified eligibility.

A declared zero reference is a specified convention, distinct from observing a risk-free series. A zero-yield cash comparator has undefined Sharpe because it has zero return variance. Synthetic formula tests are internal diagnostics and cannot become strategy results.

The probe is deliberately upstream-neutral. Post must supply and accept the net ledger adapter, cash-flow timing/return method, marks, costs and date/identity eligibility. Passing structural checks is not evidence that those upstream claims are true.

## Files and verification

The worker owns contract_probe.py, test_contract_probe.py and return-contract-v1.json. The root owns this README, progress.md and the final verification/handoff record.

Run only the isolated suite from the repository root:

~~~powershell
python -B -m unittest discover -s docs/research/sharpe-inference -p test_contract_probe.py -v
~~~

This is a small standard-library synthetic check, not a repository-wide suite or heavy simulation. The root independently verified8 test methods passing on Python3.11.9, exit0. The [verification receipt](verification-receipt.json) records the exact interpreter, command, log, source hashes and cleared review findings. Supported provenance is copied and frozen; mutable/unsupported values and ambiguous keys are rejected. Nonfinite arithmetic withholds diagnostics explicitly, even when the individual input numbers were finite.

Acceptance requires the hand-derived four-return formula fixture, rejected gaps/duplicates/naive timestamps/missing or invalid values, mismatched references, zero-variance cash, retained bankruptcy/stale-evidence reasons, and invariant unreportable/null-CI results. Tiny fixtures establish implementation behavior only; they do not establish 95% coverage or economic alpha.

## Ownership and next integration

The [existing inference plan](../../superpowers/plans/2026-10-04-sharpe-confidence-and-monte-carlo.md) has three main stages: net-return contract/diagnostics, calibrated 95% bootstrap/paired inference, and economic reporting/engine scenarios. Earlier chat reports of six implementation tasks were incorrect and have been corrected. No production stage is complete from this research prototype.

Use the [inference research](../2026-10-04-sharpe-confidence-and-monte-carlo.md) for the registered method. No generic bootstrap or nominal normal interval may be presented as calibrated 95% inference. The exact ledger adapter and canonical package integration remain subject to the Post-owned interface; no second root production package is created here.

The source performance-mode question is resolved by the direct human reply01a1060a-c9cb-7b91-9a3f-0668dbd47fae in Organize Benchmark Data Push: wait for qualified inputs before reporting performance. Empirical P&L, win rate and Sharpe headlines remain withheld until accepted qualified account evidence exists. Work on this prerequisite does not unlock the protected test. Inspected 2024/2025 remains development. Large calibration, backtests or path simulations belong on home-pc through the existing detached-job/resource policy after their inputs and execution scope are ready.

