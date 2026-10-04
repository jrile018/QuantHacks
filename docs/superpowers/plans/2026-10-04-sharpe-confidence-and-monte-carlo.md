# Sharpe confidence and Monte Carlo implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach a 95% confidence interval to eligible economic Sharpe reports and produce reproducible conditional Monte Carlo validation of the frozen strategy.

**Architecture:** Extend Post Benchmark's existing canonical `src/research_validation/` package, whose goal is set by the [strategy-validation plan](2026-10-03-strategy-validation.md). Its owner checkout and accepted-contract pointers are recorded in the [Post Benchmark handoff](../../coordination/handoffs/post-benchmark.md). File paths below are repository-relative to that canonical owner checkout; do not create a competing package in the shared root. A strict net portfolio return adapter feeds inference; joint market-path scenarios feed the existing engine through a replay callback. A report joins estimates, failure states, selection diagnostics and provenance without creating an ingestion or trading engine.

**Tech Stack:** Existing Python and NumPy/pandas patterns; SciPy distributions only if present in the pinned environment. Core interfaces and result records use dataclasses and JSON-compatible values. Select and pin the exact bootstrap/HAC implementation during Task 2 calibration; do not claim a generic IID library bootstrap implements this procedure.

**Spec:** [Sharpe confidence intervals and Monte Carlo validation](../../research/2026-10-04-sharpe-confidence-and-monte-carlo.md).

**Status:** Researched future integration plan. No tasks below have been implemented or run. The user's requested sequence is upstream completion, incoming agent contract, then integration. The source modules below are proposed files, not current capabilities. This plan does not assign other owners' work or change their shared schemas.

**Project-fit review:** [Small alpha pilot and LEAN decision](../../research/2026-10-04-alpha-pilot-and-lean-review.md). The recommended first milestone is one event family, one frozen equity signal/policy and a matched after-cost baseline. Small inference fixtures may proceed independently, but a full outer-calibration/path-simulation campaign must not delay producing the first accepted costed replay. When a pilot cannot support calibrated Sharpe inference, report the precise limitation; retain the mandatory 95% CI for eligible economic Sharpe reports. Full scope remains available as later separately evaluated layers; this recommendation does not cancel other owners' ongoing work.

**Selected pilot and results request (2026-10-04):** The human selected post-release information value in equities and finishing bounded commitments before focusing subsequent new work on that pilot. They request actual P&L, Sharpe/95% CI, win rate and account/risk results for hypothetical USD 1,000,000 initial equity, and prefer judging the results to supplying a usefulness hurdle now. These choices and scoped messaging receipts are recorded in the project-fit review. Exact source coverage, disclosure family, frozen signal/comparator, quantities/costs and regularly marked account paths remain required. No accepted costed capsule or position/risk limits exist yet; do not fabricate metrics or a promotion rule. The first inspected-data replay/report is development/descriptive, preserving the protected final period. This is the same owned plan, not an additional research/production pipeline.

**Selected minimum-source arm:** The human answered Q4 **wording-only pilot first; financial benchmark next**. Use zero mandatory financial features for the first wording/market arm, separately registered from financial-benchmark surprise. A delayed post-publication arm may use an independently evidenced public upper bound for the exact text/version, plus registered conservative replay latency; earliest news and actual historical receipt/processing remain unknown. SEC acceptance alone is insufficient evidence. Freeze one existing wording aggregation and one research order/sizing/cost policy against a price/calendar/public-metadata comparator and cash; the canonical owner must accept the mode, information/quotes and regularly valued ledger. This choice changes no current eligibility receipt and requires no new producer or NLP model.

## Global constraints

- The user requires a **95% confidence interval whenever the strategy's economic Sharpe is reported**.
- Optimize **net portfolio growth within hard risk limits**; Sharpe is one summary.
- Sharpe inference consumes regular, after-cost, cash-flow-adjusted portfolio excess returns with pinned units/calendar/currency/risk-free conversion.
- Unknown marks, timestamps, risk-free values or costs cannot be imputed to zero to pass economic gates.
- Sharpe annualization convention, sampling inference, conditional scenario outcomes and selection corrections remain distinct report fields.
- Keep a genuinely untouched chronological final period. All tuning/calibration uses past development data.
- The primary fixed-policy CI uses the untouched holdout of the single frozen final policy. A stitched walk-forward series needs its own procedure estimand and calibrated inference.
- Point-only development diagnostics remain internal; an eligible economic Sharpe assessment cannot be `complete` before its calibrated 95% interval exists.
- Preserve existing owners' edits and source contracts; the nested `stat-arb/` repository is a separate owner boundary.
- Large bootstrap campaigns, outer calibration, multi-year/path backtests and sweeps run automatically on **`home-pc` through Tailscale in detached `tmux`**, using the existing shared heavy-job lock and current two-thread/4 GiB bounds. Keep bulk data/results remote and retrieve bounded receipts. Tiny deterministic fixtures and formula checks remain local.
- No live trading, paid acquisition or external messaging is needed to execute this validation addition.

## Review focus

1. A zero-variance cash comparator or identical return paths must not create infinite Sharpe or divide by a zero paired SE.
2. Sparse events/volatility clusters can make studentization degenerate; retain invalid draws and withhold uncalibrated CIs.
3. Annualized conventional Sharpe, horizon arithmetic-sum Sharpe and CAGR have different estimands; label them correctly.
4. Calendar gaps, external flows, stale marks, overlap and bankruptcy must not be silently removed to improve results.
5. Path reconstruction may violate contract expiry, option-surface consistency or funding; reject unsupported scenarios rather than report plausible-looking returns.

## Proposed interfaces

These names form the implementation contract for the three deliverables. Adapt the upstream ledger only after its owner provides an accepted schema; do not change decision/label grain to satisfy this contract.

```python
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

@dataclass(frozen=True)
class PerformancePanel:
    timestamps: tuple[str, ...]
    net_returns: tuple[float, ...]
    risk_free_returns: tuple[float, ...]
    periods_per_year: int
    metadata: Mapping[str, object]

@dataclass(frozen=True)
class SharpeAssessment:
    status: str
    n_periods: int
    period_estimate: float | None
    annualized_conventional: float | None
    standard_error_period: float | None
    ci95_period: tuple[float, float] | None
    ci95_annualized_conventional: tuple[float, float] | None
    metadata: Mapping[str, object]
    reasons: tuple[str, ...]

@dataclass(frozen=True)
class ReplayResult:
    scenario_id: str
    equity: tuple[float, ...]
    status: str
    metadata: Mapping[str, object]

ReplayEngine = Callable[[Mapping[str, object]], ReplayResult]
```

`metadata` contains the explicit provenance/assumption fields in spec section 9. Required keys are validated against a versioned contract rather than accepted as an arbitrary unexamined dictionary. Serialize unavailable scalars as null and preserve statuses/reasons.

### Task 1: Net return contract and honest Sharpe diagnostics

**Files:** Create `src/research_validation/performance.py`, `tests/test_strategy_performance.py`. Reuse an existing package initializer if upstream creates it; otherwise add `src/research_validation/__init__.py`. Read upstream ledger/validation handoffs before writing its adapter. Do not modify legacy trade-return scoreboards yet.

**Consumes:** Accepted immutable net portfolio returns and risk-free series, complete calendar, ledger provenance and eligibility receipt.

**Produces:** `PerformancePanel`; `make_performance_panel(timestamps, net_returns, risk_free_returns, *, periods_per_year, metadata)`; internal `assess_sharpe(panel, *, hac_lags)` returning `SharpeAssessment`. Until Task 2, return `status="diagnostic_only"`, reasons including `method_not_implemented` or `calibration_pending`, and no primary CI. Point estimates and HAC/IID diagnostics stay internal; this intermediate task does not produce a user-facing eligible economic Sharpe report or a `complete` assessment.

- [ ] Write focused contract tests. Use `[0.01, 0.02, -0.01, 0.0]` with zero risk-free rates: mean 0.005 and sample variance `1/6000`, so period Sharpe is `0.005/sqrt(1/6000)`. Test irregular/missing timestamps, missing risk-free data, nonfinite values, duplicate dates and percent/decimal metadata mismatch. Use declared UTC consecutive valuation timestamps and a fixture calendar to avoid manufacturing a session.

```python
def test_period_sharpe_uses_sample_volatility(accepted_panel):
    import math
    import pytest
    from src.research_validation.performance import assess_sharpe
    report = assess_sharpe(accepted_panel, hac_lags=0)
    assert report.status == "diagnostic_only"
    assert "method_not_implemented" in report.reasons
    assert report.period_estimate == pytest.approx(0.005 / math.sqrt(1 / 6000))
    assert report.annualized_conventional == pytest.approx(
        math.sqrt(252) * report.period_estimate
    )
    assert report.ci95_period is None  # primary bootstrap not yet provided
```

- [ ] Run `python -m pytest tests/test_strategy_performance.py -q`; confirm the new import/function failures before implementation. The `accepted_panel` fixture must contain the four returns above, their calendar/risk-free provenance and positive account equity; it is synthetic and not evidence of economic readiness.
- [ ] Implement panel validation and the formulas in spec sections 2–4. Compute influence-series HAC with recorded Bartlett lag/covariance conventions. Keep annualized conventional and any horizon statistic explicitly distinct. Validate near-zero/zero variance, short samples and nonpositive/nonfinite SE. Reject ineligible panels; retain economic bankruptcy and missing-mark reasons from the ledger.
- [ ] Add tests for constant excess returns, all-cash comparator, capital-flow adjustment receipt, gaps and bankruptcy. A two-leg overlapping-trade fixture must produce one equity return per valuation interval, never two pseudo-independent trade observations. Test influence-HAC against a hand-computed lagged vector and verify squared-return dependence is included.
- [ ] Run the focused tests and existing relevant ledger/evaluation tests identified in the incoming capsule. Inspect all outputs; do not broaden into a slow suite locally.
- [ ] Commit only explicit owned files after status review: `git add src/research_validation/performance.py tests/test_strategy_performance.py` plus the initializer only if created; `git commit -m "feat: define net portfolio Sharpe assessment contract"`.

### Task 2: Calibrated 95% bootstrap and paired inference

**Files:** Create `src/research_validation/simulation.py`, `tests/test_strategy_sharpe_inference.py`, `scripts/calibrate_strategy_inference.py`. Extend the result contract in `performance.py` without changing upstream schemas. Add versioned calibration configuration under `configs/research_validation/sharpe_calibration.json` and its documented schema.

**Consumes:** Valid `PerformancePanel`, paired baseline panel on the identical accepted calendar, frozen block/HAC/quantile protocol and calibration-only development data.

**Produces:** `bootstrap_sharpe(panel, *, block_length, replicates, seed, protocol)`; `compare_sharpe(panel, baseline, *, block_length, replicates, seed, protocol)` returning `SharpeAssessment` with an explicitly named paired estimand. `protocol` includes kernel/lag and bootstrap-specific studentization version, invalid-draw rule, quantile convention and calibration reference. A centered fixed-policy test is a separate field/function, not a positive-replicate fraction.

- [ ] Write failing tests for seeded block indices, aligned paired paths, exact sample length/truncated final block, conventional CI scaling, invalid replicate retention and a degenerate identical-path delta. Use small deterministic arrays and injected replicate/statistic fixtures for CI inversion arithmetic; use at least one real small bootstrap execution for the composition.

```python
def test_conventional_ci_scales_the_same_period_estimand(panel, protocol):
    import math
    import pytest
    from src.research_validation.simulation import bootstrap_sharpe
    report = bootstrap_sharpe(
        panel, block_length=2, replicates=128, seed=73, protocol=protocol
    )
    assert report.metadata["ci_level"] == 0.95
    if report.status == "complete":
        lo, hi = report.ci95_period
        annual_lo, annual_hi = report.ci95_annualized_conventional
        assert annual_lo == pytest.approx(math.sqrt(252) * lo)
        assert annual_hi == pytest.approx(math.sqrt(252) * hi)
    else:
        assert report.ci95_period is None
        assert report.reasons
```

The 128 draws exercise composition only; they do not validate inferential precision. Pin a panel with nonzero variance and no unresolved degenerate studentization in the passing branch, and separately assert each expected failure state rather than allowing this conditional check to replace them.

- [ ] Run `python -m pytest tests/test_strategy_sharpe_inference.py -q` and confirm new-function failures. Implement symmetric studentized circular-block inference, recomputing the appropriate SE per draw. Use paired influence differences/covariance; record exact method/version. Add a stationary-bootstrap sensitivity only as a separately named procedure.
- [ ] Implement calibration configuration and command `python scripts/calibrate_strategy_inference.py --config configs/research_validation/sharpe_calibration.json --output-dir data/processed/research_validation/sharpe_calibration`. Confirm that output directory is ignored before writing run data. Its parser takes literal paths, records configuration/hash, and refuses final-holdout inputs. Run a tiny fixed-seed smoke configuration locally.
- [ ] Populate the full outer/inner calibration matrix from spec section 8. Record Gaussian/AR/VAR known population mean/variance, finite-fourth-moment skew/t/GARCH parameters, paired dependence, sample-length/block grids, failure cases and `M/B`. Keep nonstationary/infinite-moment examples explicitly outside advertised coverage. Implement binomial coverage/null-rejection intervals and CI quantile convergence reports.
- [ ] Transfer the pinned bundle to the agreed remote workspace and start the full campaign through detached `tmux` on `home-pc`, using a unique task/session name and log/exit marker. Poll session/log status; retrieve outputs. If access fails, report Tailscale/host failure and preserve the prepared bundle instead of running locally. Remove the finished session after retrieval.
- [ ] Review calibration evidence before accepting the primary method. Check block-length/studentization sensitivity and invalid-draw rates; materially insufficient coverage or precision must withhold a primary CI. Run focused tests plus the Task 1 tests. Save all measured calibration artifacts in ignored data/artifact storage, and small synthetic configuration fixtures in version control.
- [ ] Stage only the explicit Task 2 files and any owned contract extension, then commit `feat: add calibrated block bootstrap Sharpe intervals`. Report exact focused test commands and the remote calibration command/status separately.

### Task 3: Economic report and engine-based scenario validation

**Files:** Create `scripts/report_strategy_robustness.py`, `tests/test_strategy_robustness_report.py`, `tests/test_strategy_scenario_replay.py`, `docs/strategy-robustness-report.md`. Extend `simulation.py` for scenario orchestration and `performance.py` for the accepted ledger adapter. Add the incoming engine adapter in its agreed owner location only after that concrete interface is supplied; reuse its execution logic.

**Consumes:** Accepted immutable upstream capsule, Task 1/2 assessments, a `ReplayEngine`, coherent dated market-state reconstruction, costs/lifecycle/risk mandate, complete trial ledger and protected split.

**Produces:** `run_scenarios(scenarios, replay_engine)` returning `tuple[ReplayResult, ...]`; a JSON/Markdown report with primary 95% CI or explicit unavailable reasons, paired comparisons, conditional scenario metrics, selection-diagnostic availability and reproducibility receipt. The CLI accepts `--capsule`, `--protocol` and `--output-dir` literal paths and must emit valid JSON with no NaN/Infinity.

- [ ] Write failing report tests: an ineligible upstream capsule must produce `insufficient_data` with null economic metrics; an accepted assessment retains CI/method/annualization metadata; undefined cash-benchmark Sharpe never fabricates a delta. Hash/clock/calendar/unit mismatches fail closed, preserving reasons and excluded opportunities.
- [ ] Write failing engine-replay tests using a deterministic fake engine that records received scenario IDs and common shocks. Assert the engine is called once per path, aligned assets receive the same common shock, original frozen policy/hash is retained, failed/no-fill paths remain present, and costs are charged once. Add coherent option-expiry/deliverable and cash/margin/ruin counterexamples; unsupported reconstruction must be `scenario_unavailable`.

```python
def test_failed_paths_are_retained():
    from src.research_validation.performance import ReplayResult
    from src.research_validation.simulation import run_scenarios
    def engine(scenario):
        return ReplayResult(
            scenario_id=scenario["scenario_id"], equity=(100.0, 0.0),
            status="ruin", metadata={"policy_hash": "synthetic-fixed-policy"}
        )
    results = run_scenarios(({"scenario_id": "common-shock"},), engine)
    assert len(results) == 1
    assert results[0].status == "ruin"
    assert results[0].equity[-1] == 0.0
```

- [ ] Run `python -m pytest tests/test_strategy_robustness_report.py tests/test_strategy_scenario_replay.py -q` and confirm missing-new-module/function failures. Implement the adapter/report and callback orchestration. Economic eligibility remains the upstream consumer's decision; raw target labels cannot bypass it.
- [ ] Register joint block/historical stress paths, generator-fit data boundaries, execution stress magnitudes, horizon, risk thresholds, seed substreams and convergence tolerances from the supplied contract. If a full engine/coherent market reconstruction is unavailable, still report accepted return inference and expose the scenario mode as unavailable with the unmet dependency; do not label return bootstrap as a full engine backtest.
- [ ] Attach complete trial-ledger evidence before DSR/PBO/search-aware null results. Unknown trial history yields unavailable diagnostics. Distinguish zero mean differential, zero Sharpe and equal-Sharpe nulls; a best-of-many test must replay the actual selection. Protect the final period while registering this protocol. Gate the primary fixed-policy CI to that frozen final policy's untouched holdout. Treat stitched walk-forward output as a separate retraining/evaluation-procedure estimand, requiring dedicated calibration/refits or unavailable CI; causal folds alone do not establish stationarity.
- [ ] Run deterministic local composition checks, then execute the full campaign on `home-pc` in detached `tmux`. Record code/data/protocol hashes, remote environment, exact command, session/log, output hashes and retrieval receipt. Check simulation-only intervals, batch convergence and retained failures before interpreting tails.
- [ ] Produce the reviewable report with equity/drawdown and interval figures when outputs are eligible. For the selected pilot, use the user's hypothetical USD 1,000,000 initial equity, explicit quantities/cost/valuation assumptions and inspected-data development label; show net P&L, comparator increment, account returns, eligible Sharpe/95% CI, closed-position win/loss counts, cash/exposure/turnover, costs, drawdown and exclusions. An accepted full-period return alone cannot replace regular marks. Do not proportionally rescale a diagnostic price return or assume a usefulness/risk limit from the nominal capital. Let the user evaluate this descriptive result. Candidate/inconclusive/no-useful-benefit or promotion classifications require separately frozen thresholds and risk mandate; post-result choices are not preregistration. A valid negative confirmatory result completes its evaluation; incomplete data cannot establish no edge.
- [ ] Run the four new focused test modules and the existing relevant adapter tests from the accepted capsule. Also run `python -m pytest tests/test_lattice_strategy_evaluation.py tests/test_contextual_lattice_evaluation.py tests/test_multi_market_evaluation.py -q` to preserve current target/cohort/clock/date-block scope; offload if that run is heavy. Stage only explicit owned files, commit `feat: report Sharpe uncertainty and conditional strategy scenarios`, and request an independent statistical/integration review of measured evidence before any promotion decision.

## Incoming contract and execution handoff

The research document's section 10 specifies the missing inputs without guessing their schemas. When the other agent provides the accepted capsule, bind those inputs to these interfaces and preserve the three deliverable boundaries. New details may refine adapter placement or protocol settings; the 95% interval requirement remains mandatory. This plan is ready for that coordination stage; the unchecked tasks represent implementation/calibration work, not completed backtests.
