# ADR: Geometric Market Manifold — Equity Relationship Geometry for Statistical Arbitrage (C++ Edition)

- **Status:** Accepted and implemented through M10. **The ADR-013 gate has now been run against a matched control and is NOT passed** (amendment below, dated 2026-09-24). Amended in place as findings arrive; each amendment is dated.
- **Date:** 2026-08-29 (remodeled same day: full C++ implementation); last amended 2026-09-06
- **Owner:** johnp
- **Scope:** US equities first — a point-in-time S&P 500 pool of ~900 names over 2010–present, of which the ~100 most liquid at any date are scored — built so that further universes (futures, FX, crypto, credit) plug into the same pipeline (ADR-023)
- **Language:** C++20, single codebase from ingestion to visualization
- **Read with:** [PRIOR-ART.md](PRIOR-ART.md) — what has been tried elsewhere and what the evidence supports; [HYPOTHESES.md](HYPOTHESES.md) — every claim this instrument has been pointed at, with its status; [BLOCKED.md](BLOCKED.md) — every limit that cannot be closed from inside this repository, with the measurement behind it

---

## 1. Purpose

Build an **internal research instrument** for a small fund: a system that represents a universe of instruments as points in a geometric space derived from how they actually behave, wraps a surface around the region of **normal** behavior, and shows a researcher — on screen, scrubbed through sixteen years — when an individual name leaves that region, how far, and in the company of what.

Its purpose is to find *candidate* dislocations and make them legible. It is not a trading strategy, and it is not judged by one. The output of the instrument is a researcher's attention pointed at the right place, together with everything the system knows about why that place is unusual.

The system answers four questions:

1. **Where is this name right now, relative to everything else?** — its coordinates in relationship space.
2. **Is it behaving normally?** — is its point inside or outside the learned normality surface, and by how much.
3. **Has the space itself changed?** — the surface is refit on a rolling window, so it deforms over time. A sudden deformation is a regime change, and is itself a finding.
4. **Why is it there?** — what the company does, who it is economically wired to, what it is worth against its own history (ADR-022), and what happened the last times it sat where it sits now. This is co-equal with the first three, not a secondary goal: a point outside a surface with no explanation attached is a picture, not a finding.

**The hypothesis the instrument exists to test** is mean reversion: that a name which exits its normal region without a fundamental cause tends to be pulled back inside, and that the geometry identifies such exits better than a name's own price history would. That hypothesis is *tested*, not assumed — ADR-013 is the measurement, and its amendment records both what has been measured and what has not. A backtest exists (ADR-014) as one supporting check with its sample size attached; it is not the verdict.

**Scope is designed to widen.** The first universe is US equities. The pipeline's stage boundaries, artifact contract and instrument identity (ADR-023) are chosen so that a second universe — futures, FX, crypto, credit — is a new `gm-universe` and `gm-ingest` adapter and a set of normalisation conventions, not a second pipeline. Whether such universes share one geometry or get one each is deliberately undecided (ADR-023, *Not decided here*).

---

## 2. The core idea in plain language

Two stocks that move together get placed near each other. Two that move differently get placed far apart. Do that for all ~100 names and you get a cloud of points floating in space — a map of the market where distance means "unrelatedness."

Now draw a surface around the region where behavior is normal.

- A point **inside** the surface is doing what it usually does. Ignore it.
- A point that **pokes outside** has left its normal operating range. That is the dislocation.
- The **surface itself breathes** — expanding when stocks act independently, clenching when everything moves as one, and tearing when the market's structure genuinely breaks.

Three different surfaces answer three different questions, all fit over one shared feature store (ADR-008).

---

## 3. Engineering principles

These govern every decision below. They are the priorities of a production quant codebase, in order:

1. **Correctness is provable, not assumed.** Every numerical routine has reference test vectors — analytic cases, published examples, or synthetic data with known answers. No routine ships on "it looks right."
2. **Determinism.** Same inputs + same config + same binary ⇒ bit-identical outputs. No wall-clock, no unseeded RNG, no `-ffast-math`, no order-dependent parallel reductions in scored paths.
3. **One-way data flow.** Stages communicate only through immutable, versioned artifacts on disk. No stage reaches backward; the viewer never computes.
4. **The hot path is boring.** Exceptions and allocation are fine at setup; the per-frame loops are allocation-free, exception-free, and profiled.
5. **One formula, one object file.** Every stage that consumes a number consumes it from the same compiled code that produced it in every other stage; the viewer draws what `gm-boundaries` wrote and computes nothing. There is no "research version" of any formula. (An earlier wording of this principle spoke of an "eventual live engine". None is planned; the principle is about the absence of a research-versus-production seam, not about trading.)
6. **Everything is replayable.** A manifest pins config, git commit, compiler, flags, and input-data hashes for every run.

---

## 4. Glossary

| Term | Meaning |
|---|---|
| **Universe** | The ~100 tickers under study at a point in time. Point-in-time, never today's list applied to history. |
| **Frame** | One trading day's complete geometric state: correlation matrix, embedding, boundaries, scores. |
| **Feature vector** | The row `x(i, t)` describing equity `i` on day `t`. The "point." |
| **Manifold / normality surface** | The fitted boundary enclosing the region of normal behavior. Not a manifold in the strict differential-geometry sense; the name is kept because it matches how the concept is used. |
| **Excursion** | An episode where a point sits outside its surface: a start, a peak depth, an end. |
| **Excursion depth** | Signed normalized distance from the boundary. Negative = inside, positive = outside. |
| **Peer basket** | The synthetic hedge portfolio built from an equity's nearest neighbours in relationship space. |
| **Spread** | Log-price of the equity minus weighted log-price of its peer basket. The tradable residual. |
| **Stage** | One pipeline executable consuming and producing artifacts (ADR-006). |
| **Run** | One full pipeline execution under a fixed config, written immutably to `runs/<run_id>/`. |

---

## 5. Decision records

### ADR-001 — Universe: top ~100 by liquidity, point-in-time

**Context.** "Most popular equities" is ambiguous; retail-attention feeds are no longer publicly available at useful fidelity. Liquidity is the durable proxy for popularity and the property that matters for tradability.

**Decision.** Top 100 names by trailing 60-day median dollar volume, drawn from `S&P 500 ∪ Nasdaq-100 ∪ small manual high-attention list`, reconstituted annually with **point-in-time membership**.

**Consequences.** Avoids the "AI winners only" distortion of projecting today's list onto 2010. Requires reconstructing historical index membership (§7.1). Delisted names remain a partial gap (ADR-016).

**Rejected.** Hand-picked 30 names (too thin for geometry). Full S&P 500 in phase 1 (kills iteration speed while designing; the C++ engine makes scaling to it later a config change, not a rewrite).

---

### ADR-002 — Daily bars, 2010–present, free data sources

**Decision.** Daily adjusted closes, 2010-01-01 → present, from free sources (§7). No paid feed in phase 1.

**Consequences.** Holding periods of days-to-weeks. ~15 years spans the 2011 euro crisis, 2015 vol shock, 2018 Q4, COVID, the 2022 rate regime, and the 2023+ AI concentration regime — enough regimes to fit on some and validate on others. Free-data quality risk is handled explicitly (ADR-015).

**Rejected.** Intraday (paid, ~2 orders of magnitude more data; revisit only if daily proves the concept). Paid daily (revisit specifically to fix survivorship, ADR-016).

---

### ADR-003 — Language: C++20 across the entire system

**Context.** The original design was Python notebooks + a web viewer. The remodel directive: everything in C++, planned as a senior quantitative developer would.

**Decision.** C++20 (not 23 — MSVC/GCC parity on the remote box is cleaner at 20) for every component: ingestion, validation, feature computation, geometry, boundary fitting, signals, backtest, artifact export, and the interactive viewer. No Python anywhere in the build or runtime.

**What this buys.**
- **One codebase, no seam.** The formula that scored a frame in the viewer is the object file that scored it in the backtest and in the reversion study. The research→production rewrite risk — the classic quant-shop failure mode — is eliminated by construction, and that holds whether or not anything is ever traded.
- **Determinism** is achievable in a way interpreted stacks fight against: pinned toolchain, controlled floating-point, no dependency drift under the run.
- **Throughput** where it matters: parameter sweeps (thousands of full-history replays), persistent homology across ~3,800 frames, and headroom to run the full S&P 500 without architectural change.
- **A native viewer** with sub-millisecond frame scrubbing across 15 years of geometry.

**What this costs — stated honestly.**
- Development velocity: expect **2–3× the effort** of the Python design, concentrated in the data layer and the viewer, not the math.
- Loss of the scientific-Python ecosystem: robust covariance, one-class SVMs, and MDS arrive via a C++ library or get implemented and tested by hand (ADR-011, ADR-012).
- Ad-hoc exploration is slower. Mitigated by a fast artifact→viewer loop and a report generator (ADR-007), not by shell escapes into other languages.

**Consequences.** The dependency set, testing burden, and milestone plan below are all sized for this decision.

**Rejected.** Python/hybrid (directive); Rust (weaker numeric/sci-viz ecosystem for this workload, no team familiarity signal); C++23 (toolchain parity risk between MSVC on the dev box and GCC on the remote box).

---

### ADR-004 — Toolchain: CMake + vcpkg, pinned; Windows (MSVC) + Linux (GCC) first-class

**Decision.**
- **Build:** CMake ≥ 3.27 with `CMakePresets.json` defining `windows-msvc-release`, `windows-msvc-debug`, `linux-gcc-release`, `linux-gcc-asan`. One-command configure+build on both machines.
- **Dependencies:** vcpkg in **manifest mode** (`vcpkg.json` with a pinned baseline commit). Builds are reproducible from a clean clone; no system-installed libraries.
- **Compilers:** MSVC 19.4x on the dev box; GCC 13+ on the remote box (`john-riley@192.168.0.136`). Both build in CI-style scripts from day one, because the sweep engine runs on Linux and "works on my machine" is not a milestone.
- **Floating point:** strict conformance (`/fp:precise`, no `-ffast-math`). Double precision throughout scored paths.
- **Warnings:** `/W4` / `-Wall -Wextra -Wconversion`, warnings-as-errors in CI scripts.
- **Sanitizers:** ASan+UBSan preset on Linux; the full test suite passes under both before any milestone closes.

**Consequences.** Slower first build (vcpkg compiles Arrow once); every subsequent build is cached. Cross-platform discipline from day one is what makes remote sweeps free later.

**Rejected.** Conan (fine, but vcpkg's MSVC integration is smoother on this dev box). Header-only-everything (Arrow and the viewer stack make that impossible anyway). Bazel (overkill for one developer).

---

### ADR-005 — Third-party dependency policy: small, boring, pinned

**Context.** Every dependency is a supply-chain and maintenance liability. A senior codebase buys leverage, not variety.

**Decision.** The approved set, by role (vcpkg names in parentheses):

| Role | Library | Why this one |
|---|---|---|
| Linear algebra | **Eigen 3** (`eigen3`) | Header-only, the C++ standard for dense linalg; self-adjoint eigensolvers and SVD cover MDS, RMT, Procrustes. |
| Columnar storage | **Apache Arrow / Parquet** (`arrow`) | The artifact format (ADR-017); language-agnostic on-disk contract. |
| HTTP client | **cpr** (`cpr`, wraps libcurl) | Boring, portable TLS fetching for Stooq/SEC/FRED. |
| JSON | **simdjson** (`simdjson`) parse, **nlohmann-json** (`nlohmann-json`) write | Fast parse of large SEC files; ergonomic manifest writing. |
| Config | **toml++** (`tomlplusplus`) | Typed, comment-friendly configs; TOML over YAML to avoid YAML's type-coercion traps. |
| Logging | **spdlog** (`spdlog`) | Structured, fast, boring. |
| CLI | **CLI11** (`cli11`) | Declarative stage interfaces. |
| Dates | **Howard Hinnant date** (`date`) | Civil-date arithmetic; NYSE calendar built on top in-house (ADR-010 note). |
| Tests | **Catch2** (`catch2`) | Sections + matchers suit numeric testing. |
| Benchmarks | **google-benchmark** (`benchmark`) | Regression-guard the hot loops. |
| Small QP (basket weights) | **OSQP** (`osqp`) | Tiny constrained least-squares problems (k≈8); a tested solver beats a hand-rolled active set. |
| Special functions | **Boost.Math** (`boost-math`) | Normal/chi-squared CDFs for p-values and the Deflated Sharpe Ratio. |
| Parallelism | **oneTBB** (`onetbb`) | `parallel_for` over frames and sweep cells; deterministic reduction patterns where scores are produced. |
| Persistent homology | **Ripser** (vendored single header) | The reference TDA implementation *is already C++*; phase-3 lens costs no FFI. |
| Viewer | **Dear ImGui + ImPlot + GLFW + glad** (`imgui[glfw-binding,opengl3-binding]`, `implot`, `glfw3`, `glad`) | The standard in-house-trading-tool stack; immediate-mode UI + raw OpenGL for the 3D cloud/mesh. |

**Explicitly implemented in-house** (with reference tests, ADR-020): Ledoit–Wolf shrinkage, Marchenko–Pastur clipping, classical MDS, orthogonal Procrustes, weighted KDE boundary, FastMCD robust covariance (ADR-011), OU fitting, walk-forward engine, Deflated Sharpe, NYSE trading calendar, CSV parsing (formats are known and fixed; a hand-rolled RFC-4180 reader with tests beats a dependency).

**Rejected.** dlib/mlpack/Shark for the ML pieces (each drags a large surface for one or two functions; the functions we need are individually small and testable). Qt and VTK for the viewer (capability is real, but dependency weight and API surface are disproportionate to four tabs; ImGui+GL is the trading-desk idiom). xtensor (Eigen suffices).

---

### ADR-006 — Pipeline = staged CLI executables with artifact handoff (replaces notebooks)

**Context.** The original design used notebooks as orchestration. Notebooks do not exist in a C++ world, and their real value — inspectable intermediate state — must be preserved by other means.

**Decision.** The pipeline is a chain of small executables, each with a single responsibility, communicating **only** through Parquet/JSON artifacts:

```
gm-universe   → universe.parquet                (point-in-time membership)
gm-ingest     → prices.parquet + quality report (fetch, cache, validate)
gm-features   → features.parquet               (returns, betas, momentum, …)
gm-geometry   → geometry/, edges.parquet       (corr → distance → MDS → Procrustes)
gm-boundaries → surfaces/, scores.parquet      (ellipsoid + kernel fits, all views)
gm-signals    → spreads.parquet, excursions.parquet, signals.parquet
gm-backtest   → backtest/                      (walk-forward, costs, DSR)
gm-report     → reversion_study.json,           (the ADR-013 gate statistics;
                 excursions_tagged.parquet        no HTML — see ADR-007 amendment)
gm-sweep      → orchestrates cells of the above across a parameter grid
gm-view       → interactive viewer (read-only, ADR-018)
```

Each stage: reads one TOML config + upstream artifacts, validates schema versions on load, writes its outputs plus a stage manifest, and is idempotent (re-running with identical inputs is a no-op or byte-identical rewrite). `gm-run` drives the whole chain and assembles the run manifest.

**Consequences.** Intermediate state is *more* inspectable than notebooks (every hand-off is a typed file on disk, viewable in `gm-view` or any Parquet reader). Partial re-runs are free: a boundary-parameter change re-executes only `gm-boundaries` onward. The "exploration loop" becomes: edit config → run affected stages (seconds at N=100) → look in viewer.

**Rejected.** One monolithic binary with flags (loses partial re-run and blast-radius isolation). Embedded scripting (Lua/cling) for exploration (violates the single-language directive and adds a soft second language).

---

### ADR-007 — Reporting: `gm-report` emits static, self-contained HTML

**Context.** Notebooks also served as the *record* of an analysis. That role needs a C++-native replacement.

**Decision.** `gm-report` renders each run's diagnostics — data-quality tables, eigenvalue spectra, alignment residuals, excursion/reversion statistics, backtest tearsheet — to a single static HTML file with inline SVG charts generated by our own small plotting module (axes, lines, scatters, heatmaps; ~1kLOC, tested). No JS frameworks, no external assets, no server.

**Amendment, 2026-09-24 — closed as a RENDERER, not a stage.** The decision above was never implemented: `gm-plot` did not exist and `gm-report` emitted JSON and parquet. Rather than build a plotting stage, this closes as `tools/render_study.py`, which turns a run's `reversion_study.json` into one self-contained HTML page with no dependencies and no network.

Three reasons the renderer is the better shape, and they are the reasons the original decision was wrong:

- A presentation layer that can fail a pipeline run is a liability. As a tool it has no manifest, no place in the dependency graph, and cannot break a run.
- It reads only the artifact, so it cannot disagree with the numbers. A stage that recomputed anything for display would be a second implementation of the study carrying its own bugs.
- The interactive record is `gm-view`, which already exists and does what a plotting module would have done worse.

What is dropped from the original scope: eigenvalue spectra, alignment residuals and the backtest tearsheet are not rendered. They are in the artifacts and in the viewer. This entry is closed on the reversion study because that is the part somebody reads and sends to somebody else.

**Consequences.** Every run is accompanied by a human-readable artifact that can be archived or shared. The plotting module is deliberately minimal: publication charts are not the goal, decision-grade diagnostics are.

**Rejected.** Generating Plotly/vega HTML (embeds a JS stack — against the spirit of the directive and adds an untested rendering dependency).

**Amended (2026-09-06) — this ADR describes something that was never built.** There is no `gm-plot` library in the tree and `gm-report` has never emitted HTML. What it emits is `reversion_study.json` (the ADR-013 statistics, now with the horizon grid) and `excursions_tagged.parquet`; the eigenvalue spectra, alignment residuals and backtest tearsheet this ADR lists live in stage manifests and `backtest_results.json`, readable but not rendered. The viewer (ADR-018) became the human-readable record instead, which is a reasonable outcome for a research instrument — but it means a run's diagnostics are not archivable as a single file, and the decision above still reads as if they were. **Status: open.** Either build the HTML report as specified, or retire this ADR and say the viewer is the record. Not silently the latter.

---

### ADR-008 — One shared feature store, three boundary fits

**Context.** Three plausible definitions of "the object" — market cross-section, own history, peer-relative residual — look like competing designs but share all expensive computation.

**Decision.** Compute one feature table `X[equity, day, feature]` once (`gm-features` + `gm-geometry`). Fit three boundaries over it (`gm-boundaries`):

| View | Fit to | Answers | Role |
|---|---|---|---|
| **A — Market** | All equities at time t | "Is this name structurally odd vs the market's current shape?" | Visual centerpiece; regime detector |
| **B — Self** | One equity's trailing history | "Is this name outside *its own* normal range?" | Per-name normality with an honest base rate |
| **C — Peer-relative** | Equity-vs-peer-basket spread | "Has the tradable residual stretched?" | The actual trade signal |

**Amended by ADR-022.** A fourth view was added later: **D - Valuation self**, the same per-equity trailing-history fit as View B but over point-in-time valuation yields rather than embedding coordinates. It shares this ADR's premise exactly - it is another fit over the one shared feature store, not a second pipeline - which is why it cost a view rather than a stage.

**Consequences.** Marginal cost of all three over any one ≈ 15%. Cross-validation for free: a signal confirmed by B and C while A shows a stable (non-tearing) shape is materially higher-confidence than any single view.

---

### ADR-009 — Correlation estimated with shrinkage + RMT denoising, never raw

**Context.** With N=100 and window W=60, q = N/W ≈ 1.67: the sample correlation matrix is rank-deficient and its small eigenvalues are estimation noise. Geometry built on it jitters randomly day to day.

**Decision.** Every correlation matrix passes through (a) Ledoit–Wolf shrinkage toward a structured target, then (b) Marchenko–Pastur eigenvalue clipping (noise bulk replaced by its mean, diagonal re-normalized). Both in-house on Eigen, both reference-tested. RMT-clipped is the default for geometry; raw is retained for diagnostics only. The top eigenvector (market mode) is separated and optionally removed for the peer-relative view.

**Amendment, 2026-09-24 — the RIE is implemented, and it changes nothing here.** Shrinkage and MP clipping are two *competing* estimators of the same corrected spectrum, not two halves of one pipeline (amendment of 2026-09-06). The rotationally-invariant estimator the literature converged on instead is now implemented (`libs/gm-geometry/rie.hpp`, Bun–Bouchaud–Potters 2017) and selectable with `geometry.correlation_estimator = "rie"`. The default stays `shrink_clip`, because nothing yet justifies changing it.

Measured on the full panel (`runs/rie-baseline` against `runs/pit-survivorship`): it genuinely changes the distance matrix — excursions 7,110 → 7,423, matched pairs 1,322 → 1,571, covariate balance 0.0128 → 0.0024 — and changes no conclusion. Kaplan–Meier base rates move under a point (H5 0.452 → 0.459). The gate verdict is identical with a smaller largest-|t| (1.60 → 0.49).

That rules out "the ADR-013 null is an artifact of the double-cleaning", which was a live objection. It does not establish that either estimator is better: the outcome they are measured against is itself null, so there is no signal here for a better estimator to sharpen. Logged as H4 in [HYPOTHESES.md](HYPOTHESES.md); re-run if any entry rule ever produces a positive result.

**Rejected.** Raw Pearson (unstable). EWMA-only (kept as an alternative estimator flag, insufficient alone at this q).

**Amended (2026-09-06) — the two cleaning steps are alternatives, not a sequence.** Shrinkage and MP clipping are not complementary stages of one procedure; they are competing estimators of the same corrected eigenvalue spectrum, and neither derivation assumes the other has already run. Linear shrinkage moves every eigenvalue by a common factor. The true bias is eigenvalue-dependent — larger eigenvalues biased up, smaller ones down, by different amounts — which is what clipping crudely approximates and what nonlinear shrinkage solves properly. Applying both in series is not a belt-and-braces improvement; it is two corrections for one bias, interacting in a way neither paper analyses.

Current best practice is a single **rotationally-invariant estimator** — Bun, Bouchaud & Potters, *Cleaning Large Correlation Matrices* (Physics Reports 666, 2017), or equivalently Ledoit & Wolf's analytic nonlinear shrinkage (2017). The comparative literature ranks them: raw sample < linear Ledoit–Wolf ≈ MP clipping < nonlinear shrinkage/RIE, with the gap widening as `q = N/W` grows. At N=100, W=60 — and worse at the 500–900 name cross-section — that is squarely the regime where the difference is largest.

One consequence is specific to this project rather than general. RIE deliberately corrects **only the eigenvalues and keeps the empirical eigenvectors**, because eigenvector instability under sampling noise is a separate and independently damaging error that no eigenvalue correction addresses. Classical MDS (ADR-010) builds its coordinates out of precisely those eigenvectors, so the geometry inherits that instability whatever the cleaning does.

**Decision.** Implement RIE as a third estimator and make it the default for geometry, retaining the current shrink-then-clip path behind a config flag so the two can be compared on the same run rather than argued about. Until that comparison exists this remains the documented state, not a silent switch. See [PRIOR-ART.md](PRIOR-ART.md) §3.1.

---

### ADR-010 — Embeddings: classical MDS, Procrustes-aligned across frames

**Decision (two coupled choices).**
- **Classical MDS** (eigendecomposition of the double-centered squared-distance matrix, Eigen `SelfAdjointEigenSolver`) is the embedding. Deterministic, linear, preserves global distances — which is what "how far outside" depends on.
- **Every frame is orthogonally Procrustes-aligned** to the previous frame (SVD of the cross-covariance), periodically re-anchored to a long-window reference to stop drift. Without this, rotation/reflection invariance makes the animation thrash while nothing real changes. The post-alignment residual — change that rotation *cannot* explain — is retained as the **structural change metric**, a first-class regime series.

**Amendment, 2026-09-24 — the embedding is not in the signal path, so the baseline requirement was grading an absent component.** The 2026-09-06 amendment required the embedding to beat a Mahalanobis baseline on RMT-cleaned residuals before any claim rested on the geometry. Reading `apps/gm-geometry/main.cpp` to implement that comparison, the embedding turns out not to participate in the signal at all:

```
returns -> correlation -> clean -> Mantegna distance D
        -> knn_and_mst_edges(D) -> edges.parquet -> peer baskets -> z
```

The k-NN graph is built on the full-precision distance matrix, deliberately and with a comment saying so, because View C's peer selection needs precision the embedding compresses when `embedding_dims < n-1`. The MDS coordinates feed the viewer and the persistence/tear-flag detector, and nothing else.

So the ADR-013 result below is a verdict on **correlation-distance peer baskets**. It is not a verdict on the manifold, which never entered. Making the original requirement testable needs a peer-selection path genuinely built on embedding coordinates — k-NN in the embedding rather than in D — run through the same gate. Until that exists there is nothing to compare. Logged as H3 in [HYPOTHESES.md](HYPOTHESES.md), status *untestable as stated*.

A tested in-house **NYSE trading calendar** (holidays + half-days, 2010→present, from published exchange history) underlies all windowing; day-count bugs are the quietest way to corrupt every downstream number.

**Rejected.** UMAP/t-SNE (stochastic, globally distorting, frame-unstable — and no C++ implementation worth trusting for scored output).

**Amended (2026-09-06) — what the embedding is for, and the baseline it has to beat.** Classical MDS on a correlation-distance matrix is mathematically close to PCA on the same matrix: both are eigendecompositions of a related Gram matrix. The survey in [PRIOR-ART.md](PRIOR-ART.md) §3.2 found **no published evidence that embedding into geometric coordinates adds predictive information beyond what the cleaned eigenstructure already contains.** The correlation-network literature (Mantegna, Onnela, Tumminello) demonstrates the descriptive value of low-dimensional geometric views — sector recovery, crisis contraction — and essentially nothing about predictive value; MST-derived portfolio strategies characteristically fit in-sample and fail out of it.

This is not an argument against the embedding or the viewer. A diagnostic a human can read is a real deliverable (ADR-018), and the geometry is what makes the structure legible at all. It is an argument against assuming the embedding is where the signal lives, which nothing here has yet shown.

**Decision.** Before any claim that the geometry carries information, run the null it has to beat: **Mahalanobis distance on RMT-cleaned factor residuals, with no MDS and no Procrustes step** — same universe, window, boundary logic and horizon measurement (ADR-013). If the embedded version does not beat that out of sample, the embedding is earning its keep as a visualisation rather than as signal, and the README and any internal description say so.

---

### ADR-011 — Boundary estimators: robust Mahalanobis + kernel level set, always both

**Context.** An ellipsoid is interpretable but convex-only; a kernel boundary is shape-flexible but statistically mute. In C++ neither arrives for free.

**Decision.** Two estimators per view, both surfaced:
- **Robust Mahalanobis ellipsoid.** Phase 1 ships shrunk-covariance Mahalanobis with MAD-standardized inputs (simple, testable). Phase 2 upgrades to **FastMCD** (Rousseeuw & Van Driessen), implemented in-house and validated against published reference results — MCD is the deliberately-scheduled hard numerical deliverable of the project. Depth is reported in sigmas with a chi-squared p-value.
- **Kernel level-set boundary.** Weighted Gaussian KDE with Scott/Silverman bandwidth; the surface is the density contour containing (1−α) of training mass. Rendered via marching cubes (in-house, ~500 LOC, tested on analytic shapes) for the viewer mesh.

Disagreement between the two is a first-class output: it marks genuinely non-elliptical regions of "normal."

**Rejected.** OCSVM (needs an SMO solver — a large dependency or a large in-house effort for marginal benefit over a KDE level set at these dimensions). Isolation Forest / autoencoders (score without geometry: nothing to render, no "inside").

---

### ADR-012 — Topology (persistent homology) as a phase-3 lens, via Ripser

**Decision.** Vendor Ripser (single C++ header, the reference implementation) to compute H0/H1 persistence per frame. Outputs: persistence summary features joined to the feature store, and the Wasserstein distance between consecutive diagrams as a "shape change rate." Primary role is a **veto**: when the shape is tearing, mean-reversion signals from views B and C are suppressed — the definition of normal is actively invalid.

**Consequences.** This is the one place the C++ directive is a pure win: the best tool was already C++, and running it across all ~3,800 frames is a `parallel_for`.

**Implementation note (M6 tear-veto fix).** The veto is implemented as: `gm-signals` tags every `spreads.parquet`/`baskets.parquet` row with the `tear_flag` of its date (never drops rows there, so `excursions.parquet` - built from the full, untruncated z-score series - always has a matching `spreads.parquet` row), and `gm-backtest` is the one that actually rejects a tear-flagged candidate from trading, into its own `rejected_tear_veto` counter, at entry time, in the same place and the same way View A's structural-change veto and View B's outside-boundary check are already enforced. An earlier version of this veto dropped rows directly in `gm-signals`, which silently desynced `spreads.parquet` from `excursions.parquet` and miscounted 819/7,376 real tear-vetoed excursions into `gm-backtest`'s `rejected_no_spread_data` - a counter documented as catching a genuine cross-stage data-integrity failure, not a policy decision (see `apps/gm-signals/main.cpp` and `apps/gm-backtest/main.cpp` for the full comment trail).

Scope: the veto is **entry-gated only** - it blocks a candidate whose excursion *starts* on a tear day, but does not force-close a position already open when a later day tears. Read literally, "mean-reversion signals from views B and C are suppressed" describes suppressing new signal emission, which is what entry-gating does; the ADR is silent on what should happen to a position already open when a tear occurs mid-holding. Entry-only gating is the reading implemented here, consistent with how View A and View B are *also* both entry-only checks in this same engine - not a special case invented for this veto. Roughly 41% of excursions in the real 16-year run have a holding window that contains a tear day without ever starting on one, and are therefore untouched by this veto; whether they *should* be is a real open question this ADR does not answer, left for a future decision rather than silently assumed either way.

---

### ADR-013 — Reversion must be verified before it is traded (the gate)

**Context.** "Outside the normal region" is an anomaly detector. Anomalies split into noise (reverts → profit) and news (the surface was wrong → falling knife). No anomaly strategy survives without separating them.

**Amendment, 2026-09-24 — THE GATE HAS BEEN RUN AND IT IS NOT PASSED.**

The four things this entry needed and never had are now built: a matched control, name- and calendar-clustered inference, an outcome measured in realised return rather than in the indicator, and competing-risk accounting. The answer is negative, and is recorded here whichever way it fell.

**Zero of five horizons show a significant positive difference between flagged excursions and matched controls**, at any of four calipers, over matched samples from 435 to 5,137 pairs. Largest |t| anywhere is 1.60 (0.49 under the RIE). Covariate balance is good throughout — worst standardized difference 0.021 against a 0.10 bar — so this is not a failure to construct comparable groups. Where anything reaches significance it points the wrong way: at the tightest caliper the flagged names did *worse* than their twins out to twenty days.

| caliper | pairs | H5 | H10 | H20 | H40 | H60 |
|---|---|---|---|---|---|---|
| 0.15 | 435 | −0.0038 (−1.9) | −0.0037 (−2.3) | −0.0064 (−2.6) | −0.0000 (−0.0) | +0.0043 (+0.8) |
| 0.25 | 1322 | −0.0011 (−1.6) | +0.0001 (+0.1) | −0.0017 (−1.0) | +0.0000 (+0.0) | +0.0008 (+0.3) |
| 0.50 | 3497 | −0.0004 (−0.7) | +0.0006 (+0.7) | +0.0003 (+0.3) | +0.0018 (+0.9) | +0.0020 (+0.9) |
| 1.00 | 5137 | −0.0005 (−1.1) | +0.0006 (+0.6) | −0.0006 (−0.5) | +0.0007 (+0.4) | −0.0005 (−0.2) |

**So the base rates were regression to the mean.** The Kaplan–Meier figures are real (overall 0.452 by day 5, 0.953 by day 20; the depth and news splits are large and monotonic) and they are not evidence of anything, because matched controls that were never flagged do the same thing. A base rate is not an edge, and this entry's original statistic could never have distinguished the two.

Design decisions worth keeping, because they are where the first attempt went wrong:

- **The outcome is a return, not the indicator.** A z-score can cross its exit threshold because its own rolling denominator moved, with no price having done anything a position could capture. The outcome is the forward basket-relative log return with entry-day weights held fixed, minus a round-trip cost charged to both arms.
- **The primary specification does NOT match on the peer-relative move.** That is not a confounder, it *is* the treatment — being far from your peers is what the boundary detects — and the first version controlled for it, matching 11% of treated units and producing a balance table already near zero before matching. The regression-to-the-mean objection is about the *absolute* move, so the primary matches on `returns_21d`, idiosyncratic volatility and beta, exact on date and sector. The over-controlled version is kept as a deliberate lower bound.
- **Competing risks are measured, not assumed.** Aalen–Johansen alongside Kaplan–Meier: zero episodes classified as delisted against 13 censored out of 7,110, so the two agree exactly. That is a property of the liquid top hundred, not of the method; the estimator stays wired in for a wider universe.

**What this does and does not mean.** It means the excursion-reversion hypothesis built on correlation-distance peer baskets is not supported by this panel. It does not mean the geometry is uninformative — see the ADR-010 amendment: the embedding never entered. The open candidates are logged as H5 (run the gate inside the news-free bucket, the one conditioning variable that separates the population sharply) and H6 (the entry rule, with a pre-committed holdout rule recorded *before* any sweep) in [HYPOTHESES.md](HYPOTHESES.md).

Artifacts: `runs/*/gm-report/reversion_study.json`, with `manifest.gate_verdict` carrying the one-field answer. `tools/render_study.py` renders it.

---

**Decision (original).** `gm-signals` + `gm-backtest` must report, out-of-sample, before anything is traded:
- `P(point returns inside within H days | exit depth ≥ d)` — the empirical reversion base rate;
- the same, **conditioned on** an earnings date or 8-K inside the window;
- fitted OU half-life distribution of the spreads;
- performance net of realistic transaction and borrow costs.

If excursions do not revert materially better than the unconditional base rate, the geometry ships as a visualization tool and **is not traded**. That outcome is explicitly acceptable.


**Amended (2026-09-06) — the horizon was specified here and lost in implementation.** This ADR asks for `P(point returns inside within H days | exit depth >= d)`. `gm-report` dropped the `within H days` and reported the fraction of excursions whose `reverted` flag was true. That flag is set in `libs/gm-signals/include/gm-signals/excursion.hpp` and means *closed before the price series ran out* — no horizon at all. Over sixteen years a rolling-window z-score essentially always crosses back eventually, so the study reported **99.8% in every bucket**: overall, in all four peak-depth quartiles, with earnings and without. A figure that flat across every conditioning variable is a property of the definition, not a fact about markets, and "it comes back eventually" is neither tradable nor interesting.

Measured with the horizon restored — Kaplan–Meier per bucket, 7,110 excursions, run `pit-survivorship`:

| Bucket | n | Median | H=5 | H=10 | H=20 | H=40 |
|---|---|---|---|---|---|---|
| q1 shallowest | 1777 | 4 d | 61% | 86% | 98% | 100% |
| q2 | 1777 | 6 d | 48% | 77% | 96% | 100% |
| q3 | 1777 | 7 d | 37% | 67% | 94% | 100% |
| q4 deepest | 1779 | 8 d | 35% | 66% | 92% | 100% |
| without earnings/8-K | 4053 | 5 d | 54% | 82% | 98% | 100% |
| with earnings/8-K | 3057 | 8 d | 33% | 63% | 92% | 100% |

Two things the horizonless measure could not see. Depth orders the curves monotonically and **in the opposite direction to the naive thesis** — deeper excursions revert *slower*, not harder, with non-overlapping intervals. And the news split is as large as the depth split, which is ADR-022's argument appearing as a number for the first time. Everything reverts by day 40 regardless, which is exactly why the old measure said nothing.

**Kaplan–Meier rather than a count**, because excursions still outside the band when the data ends are right-censored. Counting them as failures invents outcomes never observed; dropping them biases the other way, since an episode is censored precisely because it was still dislocated. Here it is 13 of 7,110, so it barely moves these numbers — it is in for correctness, not effect. `libs/gm-signals/survival.hpp`, nine tests, the first against the published Freireich 6-MP example.

**What this is still not.** A base rate is not an edge, and the gate is not passed. Three things are required before any claim of predictive value, in order (see [PRIOR-ART.md](PRIOR-ART.md) §6):

1. **A matched control** — same day, similar size, sector, volatility, and similar magnitude of prior move, differing only in whether the boundary flagged it. Selecting on an extreme value of a noisy statistic produces apparent reversion under a true null, so without a control that also just moved a lot, plain regression to the mean is an unexcluded explanation of the entire table above.
2. **Dependence-corrected inference** — excursions for one ticker overlap and cluster heavily in calendar time. Cluster by name and calendar block, or use a calendar-time portfolio, and report effective N beside the episode count.
3. **The same analysis on realised return**, net of costs, not only on the indicator. A z-score can cross back because its own denominator moved. A detector that scores on the indicator and not on the return is measuring its own definition.

Also unaddressed: a delisting or acquisition is a **competing risk**, not ordinary censoring — a name dislocated because it is a takeover target will never revert, and treating that as censoring assumes an independence that is false.

---


### ADR-014 — Walk-forward only, Deflated Sharpe mandatory

**Decision.** Boundaries are fit on trailing data and scored strictly out-of-sample (View B's fit never contains today's point). Every reported Sharpe is accompanied by the **Deflated Sharpe Ratio**; `gm-sweep` counts trials automatically into the run manifest — the number of configurations tried is recorded by machinery, not recalled by memory.

**Consequences.** Headline numbers look worse and are believable.

---

### ADR-015 — Two-source price validation

**Decision.** Prices fetched from the primary source are validated against an independent-lineage secondary (§7.2) on a rotating sample. Automated screens flag: |return| > 50% unmatched by a known corporate action, zero-volume days, gaps > 3 trading days, and series that change retroactively between fetches. All raw pulls are cached with fetch timestamps; a run reproduces even after upstream data drifts.

**Consequences.** In an anomaly-detection system, a single bad tick *is* a fake signal. This is the defense.

---

### ADR-016 — Survivorship bias: bounded and reported, not fully solved in phase 1

**Decision.** Point-in-time index membership is reconstructed from published index-change history, so names that left are included while they were in — to the extent their prices remain retrievable. Per-year retrievability coverage is a **reported dataset statistic**. Full resolution needs a paid point-in-time source (Sharadar/Norgate/CRSP) — a phase-5 spend, contingent on the gate (ADR-013) passing.

**Amended (ADR-022 implementation).** That applies to *universe membership* and *delisted price history*, which remain the genuine gap. It does **not** extend to fundamentals: SEC XBRL carries real filing dates, so the fundamentals half of point-in-time discipline is already solved for free (§7.3, §6.6). The paid-source question is therefore narrower than this ADR originally implied — it is about prices and membership for names that left the index, not about knowing when a figure was published.

**Amended again (2026-09-06) — membership does not need a paid source; prices still might.** The previous amendment left *membership* and *delisted prices* together as one paid-source problem. Measurement separates them, and the membership half turns out to be free.

§7.1 recorded, correctly and by direct fetch, that the article's "selected changes" table is gone — re-verified on 2026-09-06, still gone. What that finding missed is that the article's **revision history** is free, reaches back past 2010, and each revision carries the full constituent table as it stood that day. Sampling it monthly reconstructs membership directly (`tools/sp500_membership_history.py`):

| | |
|---|---|
| Revisions parsed | 211 (2008-12-31 … 2026-08-19), 0 skipped |
| Tickers ever a member | 919 |
| In the index today | 503 |
| **Departed — the survivorship gap** | **413** |

The size of what was being lost, per date, comparing the current-snapshot universe against the reconstructed one:

| Date | Snapshot universe | Point-in-time | Missing |
|---|---|---|---|
| 2010-01-04 | 266 | 499 | 233 (47%) |
| 2013-01-02 | 298 | 500 | 202 (40%) |
| 2016-01-04 | 329 | 504 | 175 (35%) |
| 2020-01-02 | 406 | 505 | 99 (20%) |
| 2024-01-02 | 456 | 503 | 47 (9%) |
| 2026-08-28 | 503 | 503 | 0 |

In January 2010 the universe held 266 of the 499 names actually in the index, and every one of the 233 missing is a name that later left — the exact population that drags returns down. Across the panel it is 1,566,334 ticker-days against 2,106,845, a quarter of the universe absent.

**What the free source does not fix.** Membership is only half. A name in the universe with no price series is a hole, not a tradable name, and the price source is a separate question — asked directly rather than assumed (`tools/delisted_price_coverage.py`): of a 60-name sample of departed tickers, queried over a window in which each was genuinely a member, **only about a third come back with a usable series**. That shortfall is the honest remaining scope of this ADR, and it is narrower than "survivorship": the *denominator* is now correct and reported, so the residual is a measured coverage figure rather than an unknown.

**Consequences.** `gm-universe` gains `universe.membership_csv`. Set, it emits point-in-time membership including departed names; unset, it falls back to the current snapshot so runs that predate the history file still reproduce, and the manifest records which was used (`membership_source`) together with `tickers_departed` and the row counts that lack metadata. Departed names have no security name, sector or CIK in the current table, so those rows carry `metadata_available = false` rather than a plausible-looking blank — a downstream stage that needs a CIK can refuse loudly instead of treating an unknown name as a known one.

**What 413 is and is not.** It is an upper bound on genuine departures. A ticker **rename** is indistinguishable, in this data, from one name leaving and another arriving: Bank of New York Mellon became `BNY` in May 2026, so `BK` appears in 207 observations and then stops, exactly as a removal would — which is also why the price probe could not retrieve it, the old symbol no longer resolving. A prefix-matching sweep of the departed list finds around twenty candidate pairs (`AOC`→`AON`, `CBG`→`CBRE`, `RTN`→`RTX`, `WMI`→`WM`, …), several of them coincidences and the sweep missing `BK`→`BNY` entirely, so the true rename count is on the order of a few percent of 413 rather than a large fraction of it. Two consequences, both in the conservative direction for the claims made here: the survivorship gap is slightly smaller than 413, and the measured price coverage of departed names is slightly better than a third, since a renamed symbol counts as unretrievable. Resolving renames needs a name- or CIK-based join the constituent table does not carry for names it no longer lists, which is a genuine limit of the free source rather than a shortcut taken here.

**On sampling monthly.** Index changes are announced in advance and take effect on a known date, so monthly sampling can misdate a join or a removal by up to a month. That is a real limitation, and much smaller than the one it replaces: being three weeks wrong about a join date is not comparable to a name being absent from sixteen years of history. The observation date each answer came from is in the file, so the uncertainty is visible rather than implied.

---

### ADR-017 — Artifacts: Parquet + JSON manifests, immutable, schema-versioned

**Decision.** Tables are Parquet (Arrow C++); boundary meshes are a compact versioned binary (header + vertex/index buffers); manifests are JSON carrying `schema_version`, full config, git commit, compiler + flags, library versions, input hashes, and timings. `runs/<run_id>/` is immutable — a changed parameter is a new run. Every consumer validates `schema_version` and refuses what it doesn't understand.

**Consequences.** Any figure traces to the exact binary and data that produced it. Parquet keeps the artifacts readable by anything, which future-proofs the data even against this ADR's own language decision.

---

### ADR-018 — Viewer: native Dear ImGui + OpenGL, strictly read-only

**Decision.** `gm-view` is a native desktop application: GLFW window, OpenGL 3.3 core, Dear ImGui panels, ImPlot 2D strips, in-house orbit-camera renderer for the point cloud, MST edges, trails, and the marching-cubes surface mesh (solid + wireframe). It memory-maps run artifacts, holds an LRU cache of decoded frames, and targets < 1 ms frame decode so the 15-year time scrubber is instant. It computes **nothing** financial — it draws what `gm-boundaries` wrote (ADR-006).

**Consequences.** The viewer is real engineering work (~a third of phase-1 effort) but becomes the primary research instrument: scrubbing 3,800 frames at 60 fps is exploration Python never offered.

**Rejected.** C++ HTTP server + three.js (JavaScript, against the directive). Qt/VTK (per ADR-005).

---

### ADR-019 — Error handling, logging, and numeric hygiene

**Decision.**
- **Errors:** `tl::expected<T, Error>`-style returns (vendored single header) across module boundaries; exceptions permitted only during startup/config; hot loops are `noexcept`.
- **Logging:** spdlog, structured; every stage logs its config hash, input hashes, row counts, and timing at INFO — a run's console output is itself an audit trail.
- **Numerics:** `double` everywhere in scored paths; no fast-math; parallel reductions over scored quantities use fixed-order or compensated summation; every eigendecomposition checks convergence status; NaN is never a sentinel (explicit validity masks in tables).
- **IDs:** strong types (`TickerId`, `Date`, `FrameIndex`) — no bare `int`/`string` crossing interfaces; the compiler enforces what code review would otherwise have to catch.

---

### ADR-020 — Testing strategy: reference vectors, golden files, property tests, benchmarks

**Decision.** Four layers, all in CI scripts on both platforms, ASan/UBSan clean:
1. **Unit + reference tests.** Every in-house numeric routine validated against published or analytically-derived answers: Ledoit–Wolf on a fixture with a precomputed shrinkage intensity; MP clipping on synthetic random matrices; MDS recovering planted coordinates from their own distance matrix; Procrustes recovering a known rotation; FastMCD against the published Rousseeuw examples; OU parameters recovered from simulated paths; DSR against the paper's worked example; NYSE calendar against exchange-published holiday lists.
2. **Golden pipeline tests.** A frozen 10-ticker, 2-year fixture dataset runs the entire chain; outputs are byte-compared to committed goldens. Any numeric drift is a reviewed, deliberate golden update.
3. **Property tests.** Correlation matrices PSD after every transform; distances satisfy the triangle inequality; alignment never changes inter-point distances beyond tolerance; View B scores are causal (recomputing with future data truncated changes nothing).
4. **Benchmarks.** google-benchmark on the frame loop (corr→MDS→align→fit→score) and on viewer frame decode; regressions >10% fail the milestone.

---

### ADR-021 — Parallelism and the remote box

**Decision.** oneTBB `parallel_for` over independent frames (geometry, boundaries, homology) and over sweep cells; determinism preserved because frames are independent and per-frame work is sequential. `gm-sweep` shards a TOML-defined grid across cores; on the remote box (`john-riley@192.168.0.136`, 8 cores/30 GB, Linux+GCC preset) sweeps run detached under `tmux` with logged output per the standing remote-compute convention; results rsync back as ordinary run directories. Same binaries, same artifacts, different machine.

---

### ADR-022 — Relative valuation as a second geometry per equity (View D)

**Context.** Every coordinate in this system is derived from price co-movement. That makes two economically opposite situations look identical: a name can sit far from its usual place in the embedding because it got *cheap*, or because the business is *deteriorating*. Price geometry cannot distinguish them, and that distinction is exactly what ADR-013's reversion gate turns on — a divergence that reverts and one that keeps going are the same shape until something non-price is measured. §6.3's feature vector contains no valuation content at all.

**Decision.** Give every equity a **second geometric figure**, in valuation space, fitted with the same estimator as View B. Four commitments:

**1. The coordinates are yields, not multiples.** The three axes are earnings yield `E/P`, `EBITDA/EV`, and free-cash-flow yield `FCF/P`. Inverted deliberately. `P/E` diverges as `E → 0` and flips sign across zero earnings, which puts an unbounded, sign-flipping coordinate into a covariance estimate — the same near-degeneracy the FastMCD conditioning work (ADR-011) was about. `E/P` passes smoothly through zero and stays bounded. The fix belongs in the choice of coordinate, not in the estimator that has to swallow it.

   *Correction, recorded rather than quietly patched: that argument covers `E/P` and `FCF/P`, whose denominator is market capitalisation and therefore strictly positive. It does **not** cover `EBITDA/EV` — enterprise value is `mcap + debt − cash`, which goes negative for a company trading below its net cash, so the third coordinate can still flip sign. The two failure modes in that denominator get deliberately different treatment; see §6.6.*

**2. The figure is per-equity and self-referential — View D, the valuation analogue of View B.** Fit to that ticker's own trailing `L` days (default 756, matching View B) of `(E/P, EBITDA/EV, FCF/P)`, strictly causal. Depth answers "how cheap is this name *relative to its own history*", not "relative to the market". The cross-sectional analogue — a valuation View A — is deliberately **not** decided here; see Consequences.

**3. The numerators step, the denominators move daily.** Fundamentals restate four times a year; price and enterprise value move every session. So the valuation point moves *every day*, and a 756-day window holds 756 distinct points rather than 12 — which is what makes a robust ellipsoid a meaningful object over it at all. Known artifact: each earnings release puts a step in the cloud, so it carries roughly twelve shelves per window. That is a measurable property of the data, not a defect to suppress; whether the shelving distorts the ellipsoid enough to matter is an empirical question (§12).

**4. It is a new view, not a tenth stage.** View D lives inside `gm-boundaries`. It is the same *kind* of object as View B — a robust ellipsoid over one ticker's trailing cloud — so it reuses the same FastMCD call path and the same `scores.parquet` schema with a new `view` value. A separate executable would duplicate the fitting machinery to gain nothing. `gm-run`'s stage list is unchanged and ADR-006's partial-re-run property is preserved: changing a valuation parameter re-executes `gm-features` onward.

**Data flow.** Five touch points, in stage order:

| Stage | Change |
|---|---|
| `gm-ingest` | New `fundamentals.parquet`. Every row carries **two** dates: `period_end` (the fiscal period the figures describe) and `available_date` (the date they were published). |
| `gm-features` | `features.parquet` gains the three yield columns, computed as-of `D` under the rule below. |
| `gm-boundaries` | `scores.parquet` gains `view = "D"` rows. Same columns, same estimator. |
| `gm-signals` | A new optional condition (§6.5 condition 6). |
| `gm-view` | Renders both figures per equity. |

**Point-in-time is the load-bearing constraint, not a detail.** Any computation simulating day `D` may read only fundamentals rows where `available_date <= D`, per the rule documented in README.md. Until a paid point-in-time source exists, `available_date` is *estimated* — SEC filing dates from the Submissions API where retrievable, otherwise `period_end` plus a conservative lag — the manifest records `fundamentals_availability = "estimated" | "reported"`, and **no View D output may promote a trade while that flag reads `"estimated"`**. It is a research view until the data is right. This is the same phase-5 spend ADR-016 makes contingent on the gate.

**Consequences.**

- Marginal cost is small: one more per-ticker-per-day FastMCD fit, on an existing code path, over a cheaper coordinate space than the embedding.
- It is the **first non-price information in the system**. That is the point, and it is also the risk: everything about its value depends on data this project does not yet own.
- What it does not buy: a cross-sectional valuation geometry. Comparing yields *across* names requires a sector-normalization decision (a software company's steady-state `E/P` is not a utility's), and making that decision badly would produce a figure that looks informative and encodes only industry membership. Deferred until View D has been measured on its own.
- Fundamentals quality has no free two-source check. ADR-015's two-source price validation has no analogue here; SEC XBRL is authoritative but its tags are applied inconsistently across filers, so per-field coverage becomes a reported dataset statistic in the manner of ADR-016.
- With an estimated `available_date`, any edge measured from View D is **not evidence**. This ADR is explicitly build-the-machinery-now, buy-the-data-later; the machinery is testable without the data, the conclusions are not.

---

### ADR-023 — Instrument identity is a permanent opaque key, not a ticker

**Context.** Every stage keys on the ticker string. That is only correct for a universe of perpetual, single-venue, single-currency instruments — US equities, and not even reliably those. It has already produced a wrong answer: `BK` became `BNY` in May 2026, and the membership reconstruction (ADR-016) read one name leaving and another arriving, which is also why the price probe could not retrieve `BK` for a window in which the company was plainly listed.

Adding a second asset class makes this structural rather than occasional. A futures contract has a finite life and a roll; an option expires; a crypto asset trades on several venues at once under near-identical symbols. Retrofitting identity after the fact means rewriting every artifact ever produced, which is the migration this decision exists to avoid.

**Amendment, 2026-09-24 — implemented on the CIK, and the blind spot is measured.** `universe.parquet` carries an `instrument_id` (`libs/gm-core/instrument.hpp`). The key is the SEC CIK where one exists, not OpenFIGI: a CIK is permanent per issuer, free, and already in the panel, where OpenFIGI needs an API key and a request per instrument.

On the real panel: 894 instruments from 919 tickers, 394 of them provisional (`TICKER:` stand-in, no CIK), 3 aliases, 0 reused tickers. **All three aliases are dual share classes** — GOOG/GOOGL, FOX/FOXA, NWS/NWSA — because a CIK is per-issuer, not per-security. The key is a tagged string precisely so a share-class namespace can be added later without invalidating anything already written.

**Zero renames found, and that is the finding.** The old ticker of a rename is exactly the one with no CIK — gone from the current constituents table, hence no metadata row, hence a stand-in, hence invisible. The `BK` → `BNY` case that motivated this entry is still not resolved by it, and neither are `ANTM` → `ELV` or `FB` → `META`. `tools/detect_ticker_renames.py` reaches them by shape instead of metadata (one ticker's last observation immediately followed by another's first) and reports candidates with their handoff crowding rather than resolving: 1,469 handoffs, 46 one-for-one, roughly a fifth of those real. See [BLOCKED.md](BLOCKED.md) entry 5.

**Decision.** Introduce a permanent, opaque instrument key, assigned once and never reused, distinct from three things it is routinely confused with:

- the **display symbol**, which changes;
- the **venue-native symbol**, which differs per venue and must be preserved verbatim for wire calls (the Nautilus pattern);
- the **continuous series**, which is a modelling choice, not an instrument — a back-adjusted and a ratio-adjusted front-month series are two different objects built from the same contract chain, and neither is the chain.

Where OpenFIGI covers an instrument, use the FIGI: FIGIs never change and are never reused, persist through corporate actions, and are retired rather than recycled. Where it does not, generate a key locally. Ticker-at-a-date resolves to the key through a dated mapping (the LEAN map-file pattern), so historical answers stay correct as symbols change.

**Consequences.** Finite-life instruments are modelled as a **chain**: a logical continuous instrument referencing an ordered sequence of physical contracts, each with its own key, roll date and adjustment factor. The continuous series does not get a permanent key of its own, precisely because the adjustment method is a choice that should be revisable without invalidating downstream identity. Return-based work (correlation, geometry) reads the ratio-adjusted series; anything touching settlement or margin reads the raw per-contract series. One series cannot serve both, and naive front-month concatenation puts a price jump at every roll — which this system would faithfully flag as a dislocation.

**Not decided here.** Whether asset classes share one geometry. The survey ([PRIOR-ART.md](PRIOR-ART.md) §5) argues against a single flat embedding as the first step, on two grounds: without per-class normalisation it would largely rediscover asset-class membership, and cross-asset dependence structure reorganises under stress — exactly when the flag is meant to be trustworthy. The shape indicated is one geometry per universe plus a coarser cross-universe layer, treated as lower-confidence by construction. That is a design note, not yet a decision.

---

## 6. Mathematical specification

Unchanged in substance from the original design; restated with implementation bindings.

### 6.1 Returns and correlation

Daily log returns from adjusted close: `r_i(t) = ln(P_i(t)/P_i(t−1))`, on the in-house NYSE calendar. Rolling window `W` (default 60, swept {40, 60, 90, 120}) → sample correlation `C(t)`, then:

1. **Ledoit–Wolf shrinkage** toward a structured target → `C_LW(t)`.
2. **MP clipping**: eigenvalues inside the Marchenko–Pastur bulk for q = N/W replaced by their mean; re-normalize to unit diagonal → `C*(t)`. (Eigen `SelfAdjointEigenSolver`.)
3. **Market mode**: top eigenvector retained separately; removing it yields `C_res(t)` for View C. Both kept — whether removal helps is an open empirical question (§12).

### 6.2 Distance, embedding, alignment

Mantegna metric `d_ij = sqrt(2(1−ρ_ij))` ∈ [0, 2]. Classical MDS on `D(t)` → `Y(t) ∈ R^{N×k}` (k=3 display, up to 10 for scoring). Orthogonal Procrustes per frame: `R* = argmin_R ‖Y(t)R − Ỹ(t−1)‖_F, R'R=I`, solved by SVD (Eigen `BDCSVD`); `Ỹ(t) = Y(t)R*`. The scale-normalized residual `‖Ỹ(t) − Ỹ(t−1)‖_F` is the **structural change metric**.

### 6.3 Feature vector `x(i,t)`

| Group | Features |
|---|---|
| Position | Aligned coordinates `Ỹ(t)[i]` |
| Centrality | Distance to cloud centroid; to own cluster centroid; MST degree and betweenness |
| Risk | Beta to market eigenvector; idiosyncratic vol; idio/total variance ratio |
| Momentum | 5/21/63-day cumulative return, cross-sectionally standardized |
| Peer-relative | Spread z; spread velocity; OU half-life |
| Flow *(ph. 4)* | ETF co-membership centrality; short-interest percentile |
| Topological *(ph. 3)* | H0/H1 persistence summaries |
| Valuation | Earnings yield `E/P`; `EBITDA/EV`; free-cash-flow yield `FCF/P` (ADR-022 — point-in-time, and **not** cross-sectionally standardized; see §6.6) |

Cross-sectionally standardized per day (MAD-based) before any boundary fit.

### 6.4 Boundaries

- **View A:** fit both estimators to `{x(i,t) : all i}` per frame; score = signed normalized boundary distance; ellipsoid p-value from chi-squared (Boost.Math).
- **View B:** per equity, fit to trailing `L` days (default 756), strictly causal.
- **View C:** k nearest neighbours under `D(t)` (default k=8); basket weights by constrained ridge (`w ≥ 0, Σw = 1` — a tiny QP via OSQP); spread `s_i = ln P_i − Σ w_j ln P_j`; OU fit via exact AR(1) MLE mapping → half-life `ln 2/θ` and z-score `z = (s−μ)/(σ/√(2θ))`; boundary is a level set on `(z, ż)`.

### 6.5 Signal (all conditions required)

1. View C: `|z| > z_entry` (default 2.0) and half-life in the tradable band (3–30 days);
2. View B: outside its own surface — unusual *for this name*, not merely cross-sectionally;
3. View A: structural change metric below veto threshold (the shape is not tearing);
4. No scheduled earnings inside the expected holding horizon;
5. Liquidity/borrow feasibility on every leg;
6. *(ADR-022, OFF by default)* View D: the cheap leg is also cheap against its own valuation history. Separates "diverged because it got cheap" from "diverged because the business is deteriorating". Cannot be enabled while the run manifest reports `fundamentals_availability = "estimated"`.

Exit: `|z| < z_exit` (default 0.5), or horizon stop at 3× half-life, or hard adverse-excursion stop.

---

### 6.6 Valuation geometry (View D)

Fundamentals are a two-date table: `period_end` is the fiscal period the figures describe, `available_date` is when they were published. For a simulated day `D` and ticker `i`, let `F(i, D)` be the row with the greatest `period_end` among those satisfying `available_date <= D`. Rows are never read by `period_end` alone.

Valuation coordinates, all inverted so they stay bounded and sign-continuous through zero:

```
v(i, D) = ( E(i,D) / P(i,D),  EBITDA(i,D) / EV(i,D),  FCF(i,D) / P(i,D) )
```

with numerators from `F(i, D)` and denominators from day `D`'s price and enterprise value, so `v` moves every session even though `F` steps quarterly. `EV = market cap + total debt − cash & equivalents`, all balance-sheet terms from `F(i, D)`.

View D is then View B's construction on `v` instead of on `Ỹ(t)[i]`: per equity, FastMCD (ADR-011) over the trailing `L = 756` days of `v(i, ·)`, strictly causal, scored as signed normalized boundary distance with a chi-squared p-value. Depth is *cheapness relative to this name's own valuation history* — negative inside its normal range, positive outside it.

Unlike §6.3's feature vector, `v` is **not** cross-sectionally standardized. Standardizing it across names would convert it into a statement about industry membership (see ADR-022, Consequences).

**Enterprise value can cross zero, and the two ways it does are not the same problem.**

- `0 < EV ≪ mcap` — the coordinate becomes very large. **Left alone.** View D fits each ticker's own history with FastMCD, whose entire purpose is to ignore a minority of extreme points, so a brief episode of an enormous yield is precisely the contamination the estimator exists to absorb. Clamping the denominator to keep the number tidy would be the eigenvalue-floor mistake in a new location.
- `EV <= 0` — the coordinate flips **sign**, and robustness does not help: a sign-flipped value is not an outlier, it is a different quantity pointing the wrong way, and no breakdown point recovers from including it. That ticker-day carries **no valuation coordinate at all** — not floored, not imputed, not silently zero — and the exclusion is counted and published, the way ADR-016 already handles price retrievability. Per-status counts (`ok`, `no_fundamentals_available`, `non_finite_input`, `non_positive_market_cap`, `non_positive_enterprise_value`) go into the `gm-features` manifest so coverage is a reported number rather than something a reader infers from missing rows.

**Price basis: unadjusted close, never `adjclose`.** Market capitalisation is `close(i, D) × shares_outstanding(i, D)` using the *unadjusted* close. This is the easy mistake to make here, because every other feature in `gm-features` is built from `adjclose`: `adjclose` is back-adjusted for splits and dividends while a reported share count is not, so multiplying the two yields a market cap wrong by every split since the filing. Everything above is an aggregate dollar figure over an aggregate dollar figure — dollar earnings against dollar market cap — so no per-share adjustment basis has to be reconciled at all.

## 7. Data sources (all phase-1 needs are free)

### 7.1 Universe membership (point-in-time)

| Source | Access | Cost | Notes |
|---|---|---|---|
| S&P 500 current constituents + join date | `en.wikipedia.org/wiki/List_of_S%26P_500_companies` | Free | **Amended during M1 (2026-08-30).** The ADR originally assumed this page carries a separate "changes" table (additions/removals with dates) sufficient for full point-in-time reconstruction. As of the live page fetched during M1, that table is no longer present — verified by direct fetch, not assumed from memory (`data/raw/sp500_wikipedia.html`, retrieved 2026-08-30). What the page *does* still provide, and what M1 actually uses: a 503-row current-constituent table with a `Date added` column per member, snapshotted to `data/reference/sp500_constituents.csv`. This answers "was ticker X a member on date D" correctly for any name still in the index today (`D >= date_added`). It cannot answer that question for a name that was **removed** from the index before today — that gap is real, but it is not new: it is the same survivorship gap ADR-016 already scoped and already assigned to a paid point-in-time source (Sharadar/Norgate/CRSP) as a later-phase decision. This finding sharpens ADR-016's estimate rather than contradicting it. **Superseded in part (2026-09-06):** the changes table is indeed gone, but the article's *revision history* is free and carries the full constituent table at every revision, so point-in-time membership **is** recoverable without a paid source — 211 monthly revisions, 919 tickers ever a member, 413 departed (`tools/sp500_membership_history.py`, `data/reference/sp500_membership.csv`). Delisted *prices* remain the genuine paid-source question; see ADR-016. |
| Nasdaq-100 membership | ~~Wikipedia~~ deferred | Free (source TBD) | **Amended during M1.** Same live-fetch check found no components table on the current Nasdaq-100 Wikipedia page either (no dedicated "List of Nasdaq-100 companies" article exists as a fallback). Rather than force a fragile scrape against a page that clearly reorganizes over time, this is deferred: **M1's base pool is S&P 500 current constituents only**, explicitly narrower than ADR-001's original `S&P 500 ∪ Nasdaq-100 ∪ manual list`. Nasdaq's own official listings page is the more likely durable free source and is the next thing to try when this is revisited, not another Wikipedia scrape. |
| Ticker → CIK map | `www.sec.gov/files/company_tickers.json` | Free | Official; handles ticker changes; joins prices to filings. |
| Liquidity ranking | Computed | Free | Trailing 60-day median dollar volume from the price panel itself. |

### 7.2 Prices — **C++-driven source ordering (a real remodel change, amended again during M1)**

The Python design used `yfinance` (Yahoo primary). `yfinance` exists to negotiate Yahoo's unofficial crumb/cookie/session dance; reimplementing that dance in C++ is fragile maintenance against an undocumented target. A senior call: **make the trivially-fetchable source primary.** At the C++ remodel, that meant demoting Yahoo below Stooq.

**Amended during M1 (2026-08-30), verified by direct fetch, not assumed:** Stooq's `/q/d/l/` CSV endpoint now serves a client-side JavaScript proof-of-work challenge (a SHA-256 hashcash script) before returning any content. This blocks every plain HTTP client uninformly — `curl`, and identically `cpr::Get` from our own C++ code — not a `cpr`-specific gap. There is no lightweight fix: solving it requires executing JavaScript, which means a real or headless browser, which is out of scope for a compiled HTTP client. Stooq is therefore **not usable as the primary source** as designed, full stop, regardless of implementation language.

Meanwhile, Yahoo's unofficial chart JSON endpoint — the one explicitly demoted to "tertiary spot-checks only" specifically because it was expected to be the fragile one — was fetched directly and works cleanly with a plain `curl`/`cpr::Get`: no auth, no cookies, no JS challenge. A single request with `period1`/`period2` query params returned 4,189 daily bars for AAPL spanning 2010-01-04 through 2026-08-28 (`open`/`high`/`low`/`close`/`volume` plus a separate `adjclose` series), which is the entire history this project needs in one call per ticker.

**Revised ordering for M1 onward:**

| Source | Access | Cost | Role |
|---|---|---|---|
| **Yahoo chart endpoint** | `query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=…&period2=…&interval=1d&events=div,splits` — JSON, no auth | Free | **Primary**, promoted from tertiary. Verified working via plain HTTP; one request per ticker covers the full 2010-present range. Unofficial and undocumented, so gm-ingest's ADR-015 validation screens are the safety net, not a nice-to-have — this is exactly the kind of source that can break without notice. |
| Stooq | `stooq.com/q/d/l/` CSV | Free, but **currently blocked** by a JS proof-of-work challenge | **Demoted, not removed.** gm-io's CSV parser (already built) is ready for it the moment this is resolved (a different endpoint, a solved-challenge proxy, or Stooq relaxing the check) or for any other CSV-shaped free source found later. Not load-bearing for M1. |
| **Tiingo** | REST + free API key, documented JSON | Free tier | **Secondary/validator**, unchanged in role — still the intended independent-lineage cross-check against Yahoo (ADR-015) once a free API key is obtained. Not yet wired into M1's ingest run; the two-source validation requirement is real and open, tracked as an M1 follow-up rather than silently dropped. |
| Alpaca | REST, free tier (IEX feed) | Free | Only relevant if this ever goes live for execution. |
| Polygon.io | REST | Paid — verify pricing | The intraday upgrade path, if ever. |
| Sharadar SEP (Nasdaq Data Link) | REST | Paid — verify pricing | The survivorship fix (ADR-016), phase 5. |

This is the second live-fetch-contradicts-the-plan finding in the same M1 session (the first being §7.1's Wikipedia changes table). Both are recorded here rather than silently worked around, per the project's own engineering principles (§3): a design doc that quietly stops matching reality is worse than one that gets corrected in the open.

### 7.3 Fundamentals & identity — the "learn about it" panel

| Source | Access | Cost | Notes |
|---|---|---|---|
| **SEC XBRL Company Facts** | `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | Free | Authoritative fundamentals; descriptive `User-Agent` header required. **Carries a `filed` date on every fact**, so `available_date` is reported rather than estimated (ADR-022, §6.6) — measured, not assumed. Note it reports no Q4: `fp` runs Q1/Q2/Q3/FY, so trailing-twelve-month figures must be constructed by roll-forward, never by summing four quarterly entries. Parsed with nlohmann/json, matching the existing SEC readers in `gm-signals` and `gm-profiles` rather than introducing simdjson for one call site. |
| SEC Submissions | `data.sec.gov/submissions/CIK##########.json` | Free | Filing history incl. 8-K dates — **required** by ADR-013 to tag news-driven excursions. |
| SEC Financial Statement Data Sets | Quarterly bulk ZIPs | Free | Bulk alternative to per-company calls. |
| SIC code | In the submissions JSON | Free | Official, stable; adequate for sector coloring with the profile text. |
| Company profile text | SEC 10-K Item 1 / Wikipedia intro | Free | Business description for the panel. GICS (paid) not required. |

### 7.4 Economic relationships — the supply-chain layer (descriptive in phase 1)

| Source | Access | Cost | Notes |
|---|---|---|---|
| **ETF co-membership** | Issuer holdings CSVs (iShares/SPDR/Invesco product pages) | Free | **Recommended first layer.** Stocks held by the same ETFs are mechanically co-traded by flows; daily CSVs, trivial C++ ingestion. |
| 10-K major-customer disclosures | EDGAR full-text + parsing | Free | ASC 280 mandates disclosure of >10%-of-revenue customers → a genuine customer/supplier graph. Noisy text extraction; highest-value free option; phase 4. |
| Compustat Customer Segment | WRDS (academic) | Institutional | The Cohen–Frazzini dataset, if ever accessible. |
| FactSet Revere / Bloomberg SPLC | Enterprise | Expensive | Out of scope; listed for completeness. |
| Wikidata | API | Free | Ownership/subsidiaries for the panel; never systematic. |

### 7.5 Context & regime

| Source | Access | Cost | Notes |
|---|---|---|---|
| **FRED** | `api.stlouisfed.org` (free key) | Free | VIX, 10y–2y, credit spreads — overlaid on the Evolution tab's strips. |
| FINRA short interest | Bulk downloads | Free | Bi-weekly; crowded shorts explain a distinct excursion class. |
| Earnings dates | SEC 8-K dates (primary), Yahoo calendar (spot-check) | Free | **Required** by ADR-013 — an unmasked earnings gap is a beautiful, untradeable "dislocation." |

---

## 8. System architecture

```
 FREE SOURCES              STAGED C++ PIPELINE (each box = one executable)         VIEWER
 ------------              --------------------------------------------           ------

 Yahoo chart   ─┐   ┌────────────┐  ┌────────────┐  ┌────────────┐
 SEC EDGAR      ├──►│ gm-universe│─►│ gm-ingest  │─►│ gm-features│─┐
 FRED, FINRA    │   └────────────┘  └────────────┘  └────────────┘ │
 ETF holdings  ─┘         artifacts (Parquet + manifests) flow →   ▼
                    ┌────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────┐
                    │ gm-geometry│─►│ gm-boundaries│─►│ gm-signals │─►│ gm-backtest│
                    └────────────┘  └──────────────┘  └────────────┘  └────────────┘
                                          │                  │               │
                                          ▼                  ▼               ▼
                                   ┌──────────────────────────────────────────────┐
                                   │            runs/<run_id>/  (immutable)       │
                                   └──────────────┬───────────────────┬───────────┘
                                                  │ read-only         │
                                            ┌─────▼─────┐       ┌─────▼─────┐
                                            │  gm-view  │       │ gm-report │
                                            │ ImGui/GL  │       │ JSON+pqt  │
                                            └───────────┘       └───────────┘
```

### 8.1 Repository layout

```
equities/
  ADR.md                          <- this document
  PRIOR-ART.md                    <- what the evidence says; not decisions
  README.md
  CMakeLists.txt  CMakePresets.json  vcpkg.json
  .github/workflows/ci.yml        three configurations + benchmark gate
  config/
    params.toml
  data/
    raw/          immutable timestamped source pulls (gitignored)
    reference/    sp500_constituents.csv (current snapshot),
                  sp500_membership.csv (point-in-time, ADR-016)
  libs/                           each with its own tests/ (ADR-020 layer 1)
    gm-core/      strong types, calendar, errors, config, manifest
    gm-io/        parquet read/write, mesh format, csv, http+cache
    gm-data/      universe, membership history, fundamentals reader,
                  liquidity, retroactive-change screen (ADR-015)
    gm-geometry/  shrinkage, RMT, distance, MDS, procrustes, MST
    gm-boundaries/ mahalanobis, fastmcd, kde, marching tetrahedra
    gm-topology/  ripser wrapper, persistence features
    gm-signals/   baskets (OSQP), OU, excursions, earnings, survival
    gm-backtest/  walk-forward, costs, DSR
    gm-profiles/  SEC company profiles for the learn panel
    gm-sweep/     parameter-grid sharding and trial counting
  apps/                           one executable per stage (ADR-006);
                                  gm-features' market model and valuation
                                  live here rather than in a lib
    gm-universe/ gm-ingest/ gm-features/ gm-geometry/ gm-boundaries/
    gm-signals/ gm-backtest/ gm-report/ gm-profiles/ gm-sweep/ gm-run/
    gm-view/
  third_party/
    ripser/  tl-expected/            (vendored, pinned, licensed)
  tests/
    golden/       end-to-end against the built binaries: pipeline,
                  causality, determinism
    benchmarks/   frame-loop benchmarks + baseline.json
  tools/          reproduction scripts for every measured table in
                  these documents (membership, coverage, mesh shape)
  runs/<run_id>/                    immutable outputs (ADR-017)
```

*(Corrected 2026-09-06 against the tree: there is no `gm-plot`, no `libs/gm-features`, no `config/universe.toml` or `sweeps/`; `gm-profiles` and `gm-sweep` exist and were unlisted.)*

### 8.2 Run artifact contract

```
runs/2026-08-29__w60_k3_mds_rmt/
  manifest.json        config, git commit, compiler+flags, lib versions,
                       input hashes, trial count, timings
  universe.parquet     date, ticker, security_name, gics_sector, cik,
                       metadata_available  (false for a departed name the
                       current constituent table no longer describes)
  prices.parquet       validated adjusted OHLCV panel
  features.parquet     the feature store  (§6.3)
  geometry.parquet     date, ticker, x, y, z, dim3..dim{k-1},
                       cluster_id, mst_degree   (x/y/z ARE dims 0/1/2;
                       columns past the third appear only when
                       geometry.embedding_dims > 3)
  edges.parquet        date, ticker_a, ticker_b, distance, in_mst
  fundamentals.parquet ticker, period_end, available_date, net_income_ttm,
                       ebitda_ttm, free_cash_flow_ttm, total_debt,
                       cash_and_equivalents, shares_outstanding
                       (gm-ingest; opt-in via ingest.fetch_fundamentals)
  valuation.parquet    date, ticker, earnings_yield, ebitda_ev_yield,
                       fcf_yield  (gm-features; each coordinate
                       independently present or absent - §6.6)
  surfaces/            boundary meshes (versioned binary, §8.3)
    {date}_A.gmmesh              View A: the market's envelope that date
    {date}_B_{ticker}.gmmesh     View B: one ticker's own tube
  scores.parquet       date, ticker, view, estimator, depth, pvalue, inside
  view_c_scores.parquet  the SAME schema, written by gm-signals rather
                       than gm-boundaries: View C is fitted to the
                       z-series, which does not exist until gm-signals
                       computes it, and gm-boundaries runs before it
                       view is "A" (market cross-section), "B" (one name's
                       own embedding history) or "D" (one name's own
                       valuation history, §6.6); depth is a SIGNED margin,
                       distance minus the critical distance, so negative
                       means inside. Which views a run scored is in the
                       manifest as views_scored.
  excursions.parquet   ticker, start_date, end_date, peak_depth,
                       duration_days, reverted  (reverted=false means
                       still outside when the series ended: censored)
  excursions_tagged.parquet  the same rows plus had_earnings (gm-report)
  reversion_study.json the ADR-013 gate: P(reverted by H) per bucket with
                       Greenwood intervals and the risk set at each
                       horizon; the horizonless ever_reverted figures kept
                       beside them for comparison
  spreads.parquet      date, ticker, z, half_life, tear_flag
  baskets.parquet      date, ticker, peer, weight
  regime.parquet       date, structural_change, h0_total_persistence,
                       h1_total_persistence,
                       wasserstein_distance_from_prev_frame, tear_flag
                       (no VIX: FRED is not ingested — §7.5 is aspiration)
  backtest_results.json  sharpe, DSR, n_trials, and one counter per veto
                       (view A, view B, tear, earnings, half-life band,
                       valuation gate ×3) — the vetoes are the useful
                       part; the Sharpe is a supporting check
  daily_returns.parquet  date, return  (the series the Sharpe is from)
  meta/profiles.json   per-ticker description, SIC, links (learn panel)
```

### 8.2.1 Accounting tag resolution, measured

EBITDA and enterprise value are not XBRL concepts. They are assembled from
tags that different filers use differently, and the assembly rules below
were derived by downloading companyfacts for 40 S&P 500 issuers sampled
across the alphabet and counting, not from reading the taxonomy.

Per-issuer derivability of each coordinate:

| Yield | Derivable | Blocked by |
|---|---|---|
| E/P | 40/40 | — |
| FCF/P | 39/40 | APA reports no capex tag |
| EBITDA/EV | 29/40 | 6 issuers have no operating-income subtotal (C, COP, DHI, EMR, FOX, STT), 5 no reachable long-term-debt tag (AKAM, BRK.B, DHI, GM, TTD), 1 no cash tag |

Three rules follow, and each exists because its absence produces a wrong
number rather than an error:

1. **Availability is per COORDINATE, not per row.** Six of the eleven
   EBITDA/EV misses are banks and similar, whose income statements do not
   have an operating-income subtotal at all - a structural fact, not a data
   gap. An all-or-nothing rule would discard their E/P and FCF/P too, for
   28% of the sample.
2. **A partial component sum is refused.** Where no depreciation-and-
   amortisation aggregate is reported, the two components are added
   together; if only one is present the concept is absent. Using
   `us-gaap:Depreciation` alone - which an earlier version of the chain did,
   for 3 of 12 issuers in the first real run - omits amortisation and
   understates EBITDA silently.
3. **Absence means zero only for genuinely optional concepts.** No
   `ShortTermInvestments` tag means the issuer holds none; no `cash` tag is
   a gap. Every substituted zero is counted, split between "this filer
   reports none" and "not published by this date yet".

Per-ticker-DAY coverage is lower than per-issuer coverage, because a
concept can resolve for an issuer and still not be published as of an early
date. Measured on a real run, among ticker-days that have a market
capitalisation on the full 98-issuer run: E/P 94.6%, FCF/P 77%,
EBITDA/EV 53%, plus 4431 days excluded for a non-positive enterprise
value.

Each field takes the most recent figure for its period **or any earlier
period** that was public by the row's own `available_date`. This introduces
no look-ahead - the availability cutoff is unchanged and only the period
relaxes, backwards - and it is what an analyst reads off the latest filing
to hand. It raised FCF/P from 64% to 94% of ticker-days and EBITDA/EV from
39% to 57%, by fixing an artifact rather than a shortage: net income is
re-reported as a comparative in nearly every later filing and so has many
more vintages than capex does, and those extra anchors previously produced
rows carrying net income and nothing else.

**Measured collinearity of the two default axes.** E/P and FCF/P share a
denominator, so between filings they are exactly proportional. Over 200730
windows on the full 86-ticker production run the median absolute
correlation between them is **0.73**, the 90th percentile is **0.988**, and
**9.5%** of windows exceed 0.99. The 9123
windows (4.5%) that Mahalanobis and FastMCD both refuse to fit ARE that
collinearity - Mahalanobis names it, reporting a near-singular covariance
with points degenerate or collinear in some dimension. KDE, which inverts
nothing, scores all of them. So View D on its default axes is close to a
ONE-dimensional view, and a genuinely independent second axis means
EBITDA/EV - whose denominator is enterprise value rather than market cap -
at 53% coverage instead of 77%.

**View D therefore defaults to fitting in two dimensions**
(`earnings_yield`, `fcf_yield`). A boundary is fitted in one space, so
every point must carry every configured axis; adding EBITDA/EV does not
enrich the fit so much as shrink the cross-section it is fitted to. The
count of ticker-days that costs is published either way.

---

### 8.3 Surface naming and what each surface means

The two boundary views of §6.4 produce two different SHAPES, and pairing
either with the other's points would be a category error - so they are
named apart on disk and the viewer picks by what is currently drawn.

| File | Fitted to | Drawn when |
|---|---|---|
| `{date}_A.gmmesh` | every ticker present on `date` | the viewer is showing one date's whole market |
| `{date}_B_{ticker}.gmmesh` | that ticker's own trailing `view_b_lookback_days`, **excluding `date` itself** | the viewer is following that ticker through time |

**What shape View B comes out as depends on the lookback, and at the §6.4
default it is not a tube.** The measure is the mesh vertices' principal
extents, longest:middle - the ratio that separates a cigar from a
flattened disc. Longest:shortest does NOT separate them, because a
pancake scores just as high on it; an earlier version of this section
used that ratio and drew the wrong conclusion from it.

At the 756-day default, one AAPL surface measured 1.85 longest:middle
against View A's 2.06 on the same date - i.e. **less** elongated than the
market envelope it is being contrasted with.

At a 21-day lookback, across 69 dates spanning 2010-2026 (every 60th
exported surface):

| Ticker | median | p25 | p75 | max | fraction >= 2.0 |
|---|---|---|---|---|---|
| AAPL | 2.39 | 1.85 | 3.32 | 31.4 | 68% |
| NVDA | 2.42 | 1.95 | 3.22 | 12.4 | 70% |
| XOM  | 2.23 | 1.68 | 2.96 | 11.6 | 65% |

So roughly **two dates in three** produce a visibly elongated surface at a
one-month lookback, and one in three does not.

The reason is a fact about the data rather than about the code: a name
does not travel along a curve, it **wanders and revisits**. Over a month
in which it trended, the trailing cloud is nearly one-dimensional and its
envelope is a tube. Over a month in which it chopped sideways, the cloud
fills a region and so does the envelope. Over three years it always fills
a region. **The elongation is therefore itself a readout** - a tube means
the name has been moving directionally, a blob means it has been
oscillating - which is information the scores do not separately report.

Two further shapes show up and are not defects:

- **Disconnected lobes.** A KDE level set has no obligation to be one
  connected piece. Around the COVID crash AAPL's 21-day surface breaks
  into several, because its last month genuinely occupied several
  separate regions - pre-crash, in transit, post-crash. A single ellipsoid
  cannot represent that at all, which is the argument for the KDE
  estimator existing alongside the Mahalanobis one (ADR-007).
- **A current point on or outside the boundary.** The window excludes its
  own date, so this is the `inside` column being false, drawn.

Choosing `view_b_lookback_days` is choosing between two different
questions - "unlike its own last month" vs "unlike its own last cycle" -
not two resolutions of one.

Three properties follow from the definitions and are easy to misread as
faults:

1. **A View B tube's own date is not in its training set.** The current
   point can therefore sit *outside* its own tube, and when something
   interesting is happening it does. That is the finding, not a rendering
   error - it is the visual form of the `inside` column being false.
2. **View B surfaces are opt-in per ticker**
   (`boundaries.view_b_mesh_tickers`) and exported on a stride
   (`view_b_mesh_stride`). 81 names x 4129 dates is roughly a third of a
   million files, which is not a default. A View B mesh is also about 30x
   the work of a View A one at the same resolution, because it is fitted
   to ~756 training points rather than ~81.
3. **The viewer snaps backwards, never forwards.** Asked for a tube on a
   date that has none, it draws the newest one at or before that date and
   names the date it used. Snapping forward would put a surface fitted to
   not-yet-available data on screen - the look-ahead ADR-011 forbids in
   the scores, and no more acceptable in a picture.

At `embedding_dims > 3` a surface is necessarily the first-three-dimension
shadow of a k-dimensional fit, and is therefore **not** the boundary the
scores refer to; the manifest records `mesh_dims` alongside
`embedding_dims_scored` and carries a `mesh_projection_note` saying so.

---

## 9. The viewer (`gm-view`)

Four tabs in increasing abstraction, plus a persistent learn panel:

- **2D Pairs** — pick two names: return scatter, rolling correlation, spread with bands, excursion history. The legible baseline every exotic claim gets checked against.
- **3D Sectors** — the cloud colored by sector with cluster hulls. Answers "did the geometry rediscover sectors?" — the cheapest possible detector of a broken pipeline.
- **Manifold** — the centerpiece: point cloud inside the wireframe/solid normality surface; inside points dim, outside points lit and labeled with depth; toggles for MST edges, ellipsoid vs kernel surface, color-by (sector/depth/momentum/short interest), and trailing per-point paths.
- **Evolution** — time made explicit: a play/scrub control across the full history over ImPlot strips of the structural change metric, persistence, tear flag, and a per-ticker inside/outside ribbon. (VIX is listed in the original design and is not drawn: FRED is not ingested.)
- **Learn panel** (click any point, any tab): what the company does, SIC/sector, position and depth in all four views, current peer basket with weights, economic links, spread chart, excursion history with reversion outcomes. This is the "learn about the different equities" requirement — and the judgment-building tool for knowing when to distrust the signal.

Performance contract: < 1 ms frame decode from the mapped run directory; 60 fps scrub across ~3,800 frames × 100 names.

---

## 10. Validation protocol

1. **Geometry sanity** — clusters correspond to real sectors; the object visibly clenches in March 2020. If not, stop and debug.
2. **Alignment quality** — stable animation; structural change metric spikes at known events (Aug 2015, Feb 2018, Mar 2020, Jan 2021, Sep 2022).
3. **Reversion study — the gate (ADR-013)** — out-of-sample `P(revert within H | depth ≥ d)`, split by earnings/8-K, **against a matched control**. The question the gate answers is whether the geometry's flag carries information a researcher should act on — not whether to trade. Three outcomes, all acceptable and all to be stated plainly: the flag beats the control (the geometry adds information); it matches the control (the instrument is a legible view of ordinary mean reversion, which is still useful and must be described that way); it does worse (the boundary definition is wrong). *As of 2026-09-06 the base rate is measured and the control is not; see ADR-013's amendment for what that leaves open.*
4. **Walk-forward backtest** — expanding fits, out-of-sample trades only, realistic costs (spread, commission, borrow, impact at traded size).
5. **Deflated Sharpe** with machine-counted trials (ADR-014).
6. **Robustness** — results must survive W, k, and estimator perturbations. A result that only works at W=60, k=8 is an artifact. *Added 2026-09-06:* a result must also survive a change in the definition of "reverted" — a measurement that reads the same under every conditioning variable (as the horizonless reversion rate did, 99.8% everywhere) is a definition, not a finding.
7. **Engineering acceptance (C++-specific)** — full test suite green on MSVC and GCC; ASan/UBSan clean; golden pipeline byte-stable; benchmarks within budget; a run reproduces bit-identically from a clean clone + cached raw data.

---

## 11. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| The flag carries no information beyond ordinary reversion | **Highest** | ADR-013, now with a horizon and a survival curve; the matched control is the open half. Until it exists, regression to the mean is an unexcluded explanation of every reversion figure in this document |
| A measurement that cannot fail | High | Found once already: the gate reported 99.8% in every bucket for months because `reverted` had no horizon. Every headline statistic must be shown to *vary* under something before it is believed (§10 item 6) |
| C++ dev velocity: data layer + viewer are real effort | High | Staged milestones (§13); math library is the easy part and lands early |
| Correlation noise at q≈1.67 | High | ADR-009 mandatory shrinkage + RMT |
| Embedding instability fakes "movement" | High | ADR-010 Procrustes; residual becomes a feature |
| Hand-rolled numerics harbor silent bugs | High | ADR-020 reference vectors + goldens + properties + dual-platform CI |
| Survivorship bias inflates everything, not only backtests | High | ADR-016: membership is now point-in-time (413 departed names recovered from a free source; the geometry itself was previously drawn from survivors — 47% of the 2010 index was missing). Prices for departed names remain ~one-third retrievable; that residual is measured and reported |
| Ticker used as identity | Medium, rising with each universe | ADR-023: `BK`→`BNY` has already been misread as a departure; permanent opaque keys before the second universe, not after |
| Overfitting the parameter space | High | ADR-014 walk-forward + DSR + automatic trial counting |
| Bad tick fabricates a dislocation | Medium | ADR-015 two-source validation + screens + timestamped cache |
| Source breakage (esp. anything unofficial) | Medium-High | Yahoo chart endpoint is primary and unofficial (§7.2, revised M1) — the ADR-015 validation screens are the real defense here, not source diversity, since Stooq (the intended primary) is currently blocked outright and Tiingo isn't wired in yet |
| FastMCD implementation difficulty | Medium | Phase-1 stand-in (shrunk covariance + MAD); MCD is its own milestone with published reference tests |
| Crowding — residual reversion is well-trodden | Medium | Thin-margin expectation; costs modeled from day one. PRIOR-ART.md §2: the RMT+PCA+OU stack is industry-standard and August 2007 shows crowding is a correlated-drawdown risk, not only a decay |
| Viewer scope creep | Medium | Performance contract + four fixed tabs; anything else is phase 4+ |

**The largest risk is still conceptual, not technical.** A rotating manifold with a red point outside it is persuasive independent of whether the trade makes money — and a native 60 fps viewer makes it *more* persuasive. ADR-013 exists so that persuasiveness never substitutes for evidence.

---

## 12. Open questions

1. Universe reconstitution frequency — annual assumed; quarterly tracks liquidity better but adds geometric turnover noise.
2. Scoring dimension — display is 3; whether scoring uses 3/5/10 is a phase-3 sweep. **Partially informed:** the pipeline now genuinely scores in *k* dimensions rather than silently in 3, and a k=10 run over the full panel completes in the same order of time as k=3 (geometry 6.8s; boundaries scoring materially slower but tractable). One measured cost: at k=10, FastMCD declines to fit one frame in the whole 2010-2026 panel (2014-04-16, all 81 tickers), where at k=3 it declines none — the h-subset covariance is 10x10 and no subset of that frame yields a non-singular one. The other two estimators score it normally.
3. Within-sector vs cross-sector fits — likely different reversion characteristics; test both.
4. Short-side borrow feasibility — footnote in phase 1; becomes a constraint if the book is short-biased.
5. Market-mode removal for View C — help or hurt? Both `C*` and `C_res` retained until settled.
6. MSVC↔GCC bit-reproducibility — same platform reproduces bit-identically (guaranteed); cross-platform is tolerance-based; goldens are per-platform if needed.
7. Quarterly shelving in View D — **measured, and it matters more than "shelving" suggested.** The shelves are not merely steps: between filings *every* numerator is constant while the shared denominator (market cap) moves, so E/P and FCF/P are exactly proportional within a quarter and each shelf is a RAY through the origin rather than a plateau. A 756-day window is a fan of about twelve such rays, and it collapses toward a line whenever the cash-flow-to-earnings ratio is stable across them. Over 200730 windows on the full production run the median absolute correlation between the two axes is 0.73, the 90th percentile 0.988, and 9.5% exceed 0.99; 4.5% are singular enough that Mahalanobis and FastMCD both decline to fit while KDE, which inverts nothing, does not. So the answer is not a longer window — a longer window adds more nearly-parallel rays. It is a second axis with a DIFFERENT denominator, which means EBITDA/EV, at 53% ticker-day coverage against 77%. The run publishes the correlation so the choice is made on numbers.
8. Cross-sectional valuation geometry — a valuation View A needs a sector normalization that ADR-022 deliberately does not choose. Revisit once View D has been measured on its own.
9. **The matched control (ADR-013 amendment).** What characteristics to match on — the survey suggests date, sector, size, volatility and prior-move magnitude — and whether to use a calendar-time portfolio instead of clustered errors. Undecided; the highest-value open item in the project.
10. **Does the embedding earn its keep (ADR-010 amendment)?** The Mahalanobis-on-residuals baseline has not been run.
11. **RIE against shrink-then-clip (ADR-009 amendment).** Implemented as a flag or not yet at all; the comparison has not been made.
12. **One geometry or one per universe (ADR-023).** Deliberately open until a second universe exists to test against.
13. **Deeper excursions revert slower.** Measured, unexplained, and still unexplained after the gate was run: q1 0.606 by day 5 against q4 0.354, monotonic. Whether that is depth measuring news (news-driven excursions are both deeper and slower), the boundary being wrong in the tails, or a real property of dislocation size, is not known. Logged as H2 in [HYPOTHESES.md](HYPOTHESES.md), which names the one experiment that would settle it: re-run the depth split *inside* the news-free bucket.
14. ~~**The hypothesis log.**~~ **Decided 2026-09-24: [HYPOTHESES.md](HYPOTHESES.md).** Append-only, one entry per claim, each stating its prediction *before* the run and recording the result whichever way it fell. Entries are superseded, never deleted. Nine entries at the time of writing, of which the two that matter are H1 (the gate, not supported) and H2 (deeper excursions revert slower, unexplained). The immediate value was not bookkeeping: writing H6 forced a pre-commitment to a calendar-split holdout *before* any entry-rule sweep is run, which is exactly the commitment nobody makes after seeing a null result.

---

## 13. Milestones (each closes only with tests green on both platforms, sanitizers clean)

- **M0 — Skeleton (foundation).** Repo, CMake presets, vcpkg manifest, gm-core (strong types, errors, config, manifest), NYSE calendar + tests, CI scripts local+remote, empty stage binaries wired end-to-end passing a trivial artifact. *Exit: `gm-run` executes the whole chain on a stub fixture on both machines.*
- **M1 — Data layer.** gm-io (Parquet, HTTP+cache, CSV), gm-universe (point-in-time), gm-ingest with the ADR-015 validation screens and quality report; the 10-ticker golden fixture frozen. *Exit: 15-year, 100-name validated price panel builds locally; coverage stats reported.*
- **M2 — Geometry.** Shrinkage, RMT, distance, MDS, Procrustes, MST; reference tests for each; gm-report v1 (eigenvalue spectra, alignment residual). *Exit: geometry artifacts for full history in < 60 s locally; structural change metric spikes at known events.*
- **M3 — Boundaries + Viewer alpha.** Phase-1 Mahalanobis + KDE level set + marching cubes; scores for views A and B; gm-view with Manifold + Evolution tabs against real artifacts. *Exit: the object visibly clenches in March 2020, on screen, scrubbed live.*
- **M4 — Signals + the gate.** Peer baskets (OSQP), OU fitting, excursion tracking, earnings/8-K tagging; the ADR-013 reversion study in gm-report. *Exit: a defensible out-of-sample answer to "do excursions revert?" — the go/no-go.*
- **M5 — Backtest + sweeps.** Walk-forward engine, cost model, DSR, gm-sweep sharding on the remote box. *Exit: deflated, cost-netted walk-forward results with machine-counted trials.*
- **M6 — Depth (contingent on M4 passing).** FastMCD, Ripser lens + tear-veto, remaining viewer tabs (2D Pairs, 3D Sectors), learn panel with SEC profiles, ETF co-membership layer. *Exit: each lens either improves the reversion statistics or is documented as not doing so.*
- **M7 — Hardening (contingent on M5 promise).** 10-K customer-graph parsing, paid point-in-time data decision (ADR-016), full-S&P-500 scale test, benchmark budget review.

**Status against this plan, 2026-09-24.** M0–M9 are built and green (422 tests, three configurations, CI); M10 is partial. **The gate is closed and negative** — see the ADR-013 amendment. The paragraph below is the 2026-09-06 status and is kept because its central warning turned out to be correct.

**Status against this plan, 2026-09-06.** M0–M7 are built and green (379 tests, three configurations, CI). The contingencies were **not honoured as written**: M6 and M7 were built before M4's gate was known to be passed, and it is now known that M4's exit criterion was not actually met at the time — the reversion study had no horizon and could not have answered "do excursions revert?" in any discriminating way. That is recorded here rather than re-ordered away. The gate stands **open**: the base rate is measured (ADR-013 amendment), the control is not. Nothing built in M5–M7 is invalidated by that — the backtest, valuation view and viewer are all instruments for the same research question — but no claim of predictive value is made anywhere in this repository, and none should be until the control exists.

- **M8 — The gate, properly. DONE 2026-09-24, and the answer is negative.** Matched control (`libs/gm-signals/matching.hpp`), two-way cluster-robust inference with effective N (`cluster.hpp`), outcome measured in realised return net of costs, competing-risk accounting (`competing_risks.hpp`). *Exit met: ADR-013 is answered against a control, and the answer — not passed, zero of five horizons — is stated.*
- **M9 — Estimator questions the survey raised. DONE 2026-09-24.** RIE implemented behind `geometry.correlation_estimator` and compared on a full run: it changes the distance matrix and not the answer (ADR-009 amendment). The no-manifold baseline turned out to be the *existing* pipeline — k-NN runs on the distance matrix, not the embedding — so there was no second thing to build and the comparison ADR-010 asked for does not currently exist to be made (ADR-010 amendment). *Exit met: both documented as not changing the M8 answer, one of them because it was already what was running.*
- **M10 — Second universe. PARTIALLY DONE 2026-09-24.** ADR-023 identity is implemented and measured (amendment above): `instrument_id` in `universe.parquet`, 894 instruments, the 394-name blind spot counted rather than assumed, and a rename-candidate tool for the names the key cannot reach. **The non-equity adapter is not built.** Given the M8 result, adding a second universe before the first one has a supported hypothesis would be building more instrument around a question that has just been answered negatively; H5 and H6 come first. *Exit not met: no universe that rolls or never closes has been run.*

---

## 14. References

The survey in [PRIOR-ART.md](PRIOR-ART.md) carries the fuller list, including the negative results. These are the ones the original design rested on.

- Mantegna (1999), *Hierarchical structure in financial markets* — correlation distance, MST.
- Ledoit & Wolf (2004), *A well-conditioned estimator for large-dimensional covariance matrices*.
- Laloux, Cizeau, Bouchaud & Potters (1999), *Noise dressing of financial correlation matrices* — the RMT case for ADR-009.
- Avellaneda & Lee (2010), *Statistical arbitrage in the US equities market* — residual reversion, OU, s-scores; direct ancestor of View C.
- Rousseeuw & Van Driessen (1999), *A fast algorithm for the minimum covariance determinant estimator* — the ADR-011 phase-2 deliverable.
- Cohen & Frazzini (2008), *Economic links and predictable returns* — supply-chain layer justification.
- Gidea & Katz (2018), *Topological data analysis of financial time series: landscapes of crashes* — ADR-012.
- Bailey & López de Prado (2014), *The deflated Sharpe ratio* — ADR-014.
- Bauer (2021), *Ripser: efficient computation of Vietoris–Rips persistence barcodes* — the vendored TDA engine.
