# Prior art

A survey of what has already been tried in geometric statistical arbitrage,
how comparable systems are built, and what an equities-only pipeline has to
change before a second asset class can plug into it. Compiled 2026-09-06.

This file is **reference material, not a decision record**. Where the findings
below change or contradict a decision, that change is recorded as an amendment
in [ADR.md](ADR.md) and cross-referenced here. Read this to know what the
evidence says; read the ADR to know what this project does about it.

Sources are named inline. Where the public record is thin, that is stated
rather than filled in with inference dressed as fact.

---

## 1. Which lineage this belongs to

Two families of research could claim this system as a descendant. They have
very different evidential standing, and being explicit about which one applies
prevents borrowing credibility that was never earned.

### The residual mean-reversion lineage — real, audited, decayed

Avellaneda & Lee, *Statistical Arbitrage in the US Equities Market*
(*Quantitative Finance* 10(7): 761–782, 2010) is the direct ancestor. Their
method: PCA on a standardised return correlation matrix, residuals against the
top ~15 principal components over a 60-day rolling window, an Ornstein–Uhlenbeck
fit on the cumulative residual, a mean-reversion-speed filter discarding names
whose fitted half-life is long relative to the window, and an `s-score`
threshold band for entry and exit.

Every one of those steps has a counterpart here. This project's boundary on a
robust distance is a **multivariate generalisation of the s-score** — an
ellipsoid in place of a scalar z, and a nonparametric density level set in
place of a fixed threshold.

Reported performance, and its decay:

| Period | Sharpe (PCA variant, after estimated costs) |
|---|---|
| 1997–2007 | ~1.44 |
| 2003–2007 | ~0.90 |

The decay is visible *inside their own sample*, before 2008 and before anything
published since. Corroborating evidence from the adjacent pairs-trading
literature — Do & Faff, *Does Simple Pairs Trading Still Work?*
(*Financial Analysts Journal* 66(4), 2010) — is a monotonic multi-decade
decline in the classic distance method:

| Period | Mean monthly excess return, top-20 pairs |
|---|---|
| 1962–1988 | 0.86% |
| 1989–2002 | 0.37% |
| 2003–2009 | 0.24% |

**No credible audited post-2010 track record for the classic PCA/OU/s-score
construction exists in the public literature.** Claims otherwise generally are
not citing anything.

### The manifold / topological "early warning" lineage — descriptive, not predictive

Persistent homology and diffusion maps applied to markets are a thin and mostly
unreplicated literature. The most-cited work is Gidea & Katz, *Topological Data
Analysis of Financial Time Series: Landscapes of Crashes* (*Physica A* 491,
2018; arXiv:1703.04385), which reports a rise in the persistence-landscape norm
roughly 250 trading days before Lehman. It is two retrospective crisis case
studies, with no false-positive rate reported over calm periods and no trading
rule.

More damaging is the adversarial test of the premise that whole family rests on
— that a crash is a critical transition and therefore has detectable
precursors. Guttal et al., *Lack of Critical Slowing Down Suggests that
Financial Meltdowns Are Not Critical Transitions* (*PLOS ONE* 10(12): e0144198,
2015) tested five markets across a century of crashes and found **no consistent
critical slowing down**, weakly present only before 1987. Rising *variance* — a
far simpler statistic — does show up.

**Consequence for this project.** Never describe the instrument as "detecting
dislocations before they happen" on the strength of that literature. It does
not support the claim. Anything of that kind has to be earned here, against a
control, with a stated false-positive rate.

---

## 2. Standing of each method this design touches

| Method | Standing | What it is actually good for |
|---|---|---|
| RMT correlation cleaning | **Solid** | Laloux, Cizeau, Bouchaud & Potters (*Phys. Rev. Lett.* 83, 1467, 1999) and Plerou et al. (*Phys. Rev. Lett.* 83, 1471, 1999) independently showed the bulk of the empirical correlation spectrum is indistinguishable from Marchenko–Pastur, i.e. pure sampling noise. Load-bearing and correct. |
| Correlation networks / MST | **Descriptive** | Mantegna (*Eur. Phys. J. B*, 1999) recovers sector structure from prices alone; Onnela et al. (2002–2003) show tree length contracting in crises. Both replicate. Neither has produced a replicated *predictive* edge — MST-based portfolio strategies characteristically fit in-sample and fail out. |
| Manifold learning / TDA | **Unsupported** | See §1. Retrospective, in-sample, few labelled crisis dates. |
| Residual mean-reversion | **Real, decayed** | See §1. Edge concentrates in turbulent periods rather than steady state. |

A useful critique of the network literature, worth internalising: most of what
an MST diagram shows — sector clustering, correlation rising in crises, market
mode dominance — is already captured by the top eigenvalue and eigenvector of
the correlation matrix. The network view is a lossy re-encoding of information
PCA extracts more efficiently. Marti, Nielsen, Bińkowski & Donnat,
*A review of two decades of correlations, hierarchies, networks and clustering
in financial markets* (arXiv:1703.00485) is the standard survey and is explicit
that the field is largely taxonomic rather than predictive.

### Crowding is a tail-risk story, not only a decay story

Khandani & Lo, *What Happened to the Quants in August 2007?*
(*J. Financial Economics*, 2011; NBER WP 14465) is the definitive forensic
account of the quant quake: equity market-neutral funds took synchronised,
severe losses over 6–9 August 2007 consistent with coordinated forced
deleveraging of similarly-constructed portfolios. The RMT + PCA + OU stack is
now industry-standard. Assume others hold something structurally similar, and
that correlated drawdown is a risk this design shares by construction rather
than one its own backtest would reveal.

The counterweight, and it is a real one: Do & Faff find the strategy still
performs relatively well specifically *during* turbulence, including 2008. That
is the part of the phenomenon that has decayed least — and it is the part an
excursion-flagging instrument is pointed at, as opposed to a strategy
harvesting a constant daily drift.

---

## 3. Two findings that change what this project does

Both are recorded as ADR amendments; the detail is here.

### 3.1 Ledoit–Wolf shrinkage and MP clipping are two solutions to one problem

ADR-009 applies both, in series. They are not complementary steps — they are
competing estimators of the same corrected eigenvalue spectrum, and neither
derivation assumes the other ran first. Linear shrinkage moves every eigenvalue
by a common factor; the true bias is eigenvalue-dependent, which is what
clipping crudely approximates and what nonlinear shrinkage solves properly.

Current best practice is a single **rotationally-invariant estimator** — Bun,
Bouchaud & Potters, *Cleaning Large Correlation Matrices: Tools from Random
Matrix Theory* (*Physics Reports* 666, 2017; arXiv:1610.08104), or equivalently
Ledoit & Wolf's analytic nonlinear shrinkage (*J. Financial Econometrics*,
2017). The honest ranking from the comparative literature:

    raw sample  <  linear Ledoit–Wolf  ≈  MP clipping  <  nonlinear shrinkage / RIE

The gap widens as N/T grows, which for a 500–900 name universe on a rolling
window is exactly the regime this project sits in.

A second-order point that matters specifically here: **RIE deliberately
corrects only the eigenvalues and keeps the empirical eigenvectors**, because
eigenvector instability under sampling noise is a separate and independently
damaging error. Classical MDS builds its coordinates out of precisely those
eigenvectors. See ADR-009's amendment.

### 3.2 The embedding may be a visualisation rather than a signal

Classical MDS on a correlation-distance matrix is mathematically close to PCA
on the same matrix — both are eigendecompositions of a related Gram matrix.
There is **no published evidence that embedding into geometric coordinates adds
predictive information beyond what the cleaned eigenstructure already
contains.**

That is not an argument against the viewer. A diagnostic instrument a human can
read is a real thing to build, and the geometry is what makes the structure
legible. It is an argument for knowing what the geometry costs, which means
running the null hypothesis it has to beat:

> **Mahalanobis distance on RMT-cleaned factor residuals — no MDS, no
> Procrustes.** Same universe, same window, same boundary logic, same horizon
> measurement.

If the embedding does not beat that out of sample, it is earning its keep as a
picture and not as signal, and should be described that way internally. See
ADR-010's amendment.

---

## 4. Comparable systems, by architecture

Read for structure, not features.

| System | Take | Leave |
|---|---|---|
| **QuantConnect LEAN** | `Symbol` / `SecurityIdentifier`: a permanent hashed identifier plus dated map-files resolving ticker-at-time back to it. The `Slice` model — the algorithm sees exactly one time instant, so look-ahead is structurally impossible rather than a discipline. `IUniverseSelectionModel`: one asset-class-agnostic interface, different filters underneath. | "Survivorship-bias-free" is a property of the data vendor, not the engine. C# weight. |
| **Microsoft Qlib** | An explicit revision chain for restated data — `date, period, value, next` — so "what was known on date X" is a lookup rather than a reconstruction. Content-hashed feature caching. | Its point-in-time layer covers fundamentals only, not membership, sectors, or corporate actions. Easy to believe you have bitemporal correctness everywhere when you have it in one place. |
| **Zipline Pipeline** | Factor / Filter / Classifier separation, and computing cross-sectional terms ahead of the sequential simulation. This project's stage boundaries already do this. | bcolz storage; a new reader/writer class per asset class; volunteer-maintained fork. |
| **Nautilus Trader** | Ports-and-adapters: strategy written once, only the data/execution adapter changes between backtest and live. Venue-native symbol kept as a field separate from the canonical internal one. | Kernel parity does not imply identical live outcomes. Fast-moving API. |
| **ArcticDB** (Man Group) | Immutable segments plus a version chain; named cross-symbol **snapshots** — an atomic "reproduce this whole run's inputs" pointer. | It is unitemporal (transaction-time) versioning, not bitemporal, despite loose usage of the word. Business Source Licence. |
| **vectorbt** | A deliberately separate fast parameter-sweep mode for exploration, kept apart from the reproducible path. | Its default fills on the same bar that generated the signal, so look-ahead becomes a data-alignment bug rather than an architectural impossibility. |

**Where this project is already ahead:** none of the six records compiler
identity in its provenance. For numerically sensitive C++ that is a real
reproducibility input, not fastidiousness (ADR-017).

**The one organisational idea worth stealing** is López de Prado's "research
factory" (*Advances in Financial Machine Learning*, 2018): separate who
proposes a signal from who validates it, so no one person can iteratively tune
a backtest until it looks good. At this size the committee version is overkill;
the substrate is not. Per-stage manifests already provide the technical means
to enforce such a boundary.

**Worth knowing before importing anything:** `mlfinlab` has documented
discrepancies between its implementations and the algorithms it claims to
implement. Treat its functions as reference implementations to audit, not
black boxes to trust.

---

## 5. Adding universes

The expensive part of a second asset class is not the data. It is that this
pipeline assumes things true only of US equities: one calendar, one currency,
instruments that live forever, and a ticker as an identity.

### What breaks, in order of cost

1. **Ticker as identity.** Already biting: `BK` became `BNY` in May 2026 and the
   membership reconstruction read it as one name leaving and another arriving
   (ADR-016). Futures rolls and option expiries make this structural rather
   than occasional. A permanent opaque identifier is cheap now and a migration
   later. OpenFIGI is the relevant prior art — FIGIs never change and are never
   reused; they persist through renames and are retired rather than recycled
   when an instrument ceases to exist.
2. **Continuous futures construction.** Naive front-month concatenation puts a
   price jump at every roll, which a geometric outlier detector will faithfully
   flag as a dislocation. Use **ratio/proportional adjustment** for anything
   return-based; back-adjustment preserves absolute differences but accumulates
   drift and can produce negative historical prices over long contango
   histories. Keep raw per-contract series separately for settlement and margin
   logic — one series cannot serve both purposes. Roll on volume/open-interest
   crossover rather than a fixed days-before-expiry rule.
3. **Non-synchronous closes.** FX has no close; crypto never closes. Any daily
   bar convention across them is an arbitrary snapshot, and correlations
   computed across it carry a synchronisation artefact. Choose the convention
   explicitly and record it.
4. **Volatility scale.** Crypto runs 3–6× equity volatility with fatter tails.
   Without per-instrument volatility standardisation before embedding, the
   geometry is dominated by whichever universe is loudest.
5. **Crypto survivorship.** Over half of all listed tokens have died; estimates
   of backtest return inflation from ignoring this run to 200–400%. An order of
   magnitude worse than the equity problem this project just fixed.
6. **Currency denomination.** Unhedged foreign-currency P&L folds FX risk into
   the asset correlation structure — a EUR-denominated future starts
   correlating with EURUSD rather than with its own fundamentals.

### One geometry or several

**Do not put all asset classes into one embedding first.** Two reasons. Without
careful per-class normalisation a shared embedding will mostly rediscover
asset-class membership, a cluster already known. And cross-asset dependence
structure reorganises under stress — classes that look segmented in calm
periods mix — which is precisely when a dislocation flag is supposed to be
trustworthy.

There is real positive evidence a cross-asset graph can carry signal: Pu,
Roberts, Dong & Zohren, *Network Momentum across Asset Classes*
(arXiv:2308.11294) report Sharpe 1.51 out-of-sample 2000–2022 over 64
continuous futures spanning commodities, equities, bonds and currencies. Note
what made it work — a single instrument *type*, already continuous-adjusted,
built on returns. The graph added value on top of clean inputs; it did not
substitute for cleaning them.

**Shape to build:** one geometry per universe, each normalised to its own
conventions, plus a separate coarser cross-universe layer on
volatility-standardised, currency-hedged, carry-adjusted returns — treated as
lower-confidence and regime-conditional by construction.

A caution on normalisation worth carrying: the follow-up literature on AQR's
time-series momentum finds the headline result is substantially attributable to
the volatility-scaling transform itself rather than to a distinct momentum
phenomenon. A volatility-scaled cross-asset signal should be validated against
a volatility-scaled *random* signal before being trusted.

---

## 6. Measuring whether any of this is an edge

This section is the methodology the reversion gate is held to. The horizon fix
(ADR-013 amendment) implements the first item; the rest are open.

**Survival analysis is the right frame, and censoring must be explicit.**
Kaplan–Meier for `P(reverted by H)`, Greenwood for the interval. An episode
still outside the band when the data ends is *censored*: counting it as a
failure invents an outcome never observed and biases the estimate down;
dropping it biases up, since an episode is censored precisely because it was
still dislocated (length-biased sampling). Nelson–Aalen cumulative hazard is
the more informative view of *when* reversion risk concentrates.

**Competing risks are not ordinary censoring.** An episode can leave the risk
set by delisting or acquisition rather than by reverting — and a name
dislocated *because* it is a takeover target will never revert. Treating that
as ordinary censoring assumes independence that is false. At minimum, count and
report such exits separately.

**A base rate is not an edge.** The control must hold "just had a large move"
constant, or plain regression to the mean explains everything: selecting on an
extreme value of a noisy statistic produces apparent reversion under a true
null. The design that isolates the geometry's marginal contribution is a
**same-day, characteristic-matched control** — similar size, sector,
volatility, and similar magnitude of prior move, differing only in whether the
boundary flagged it. Self-matched controls miss market-wide reversal regimes;
an unconditional bootstrap reintroduces the regression-to-the-mean confound.

**Effective sample size is far below the episode count.** Excursions for one
ticker overlap and are not independent draws, and episodes cluster heavily in
calendar time because they are driven by common shocks. Kolari & Pynnonen
(*Review of Financial Studies*, 2010) show even modest cross-correlation among
event-window abnormal returns causes severe over-rejection of the null. Cluster
standard errors by name and by calendar block, or use a calendar-time portfolio
so there is one observation per day instead of N pretend-independent episodes.
Report the raw count and a block-bootstrap effective N side by side.

**A z-score crossing back is not a capturable move.** The indicator can revert
because its own denominator moved, or because the boundary itself shifted. Run
the survival analysis twice: once on the indicator, once on realised abnormal
return to horizon H net of a cost assumption. A detector that scores on the
first and not the second is measuring its own definition.

**Count the hypotheses.** Bailey & López de Prado's deflated Sharpe ratio and
Harvey, Liu & Zhu's adjusted hurdle (*RFS*, 2016 — arguing a new factor needs
`t > 3.0`, not 2.0) both need one input above all: how many hypotheses were
tested. Without a log the correction is not informal, it is **uncomputable**.
Chordia, Goyal & Saretto estimate roughly 45% of published anomalies are false
positives under proper correction. For a small team the correction itself will
be modest — dozens to low hundreds of variants a year, not decades of published
literature. The risk is not that the adjustment is large; it is that nobody is
counting, so even a small one cannot be applied. An append-only table — idea,
date, who, in-sample result, kept or rejected — is nearly free, and retrofitting
it after two hundred untracked backtests is not.

**Labels overlap, so ordinary cross-validation leaks.** "Reverted within H days"
spans a forward window that overlaps neighbouring observations'. Purged,
embargoed cross-validation (López de Prado) is the correct scheme for any
tuning done in-sample.

### What to report

Survival curves by depth decile with Greenwood bands and the matched control
overlaid; a log-rank test across deciles; Cox hazard ratios with the
proportional-hazards assumption checked (Schoenfeld residuals) — and stratified
by depth if it fails; base rate against control at each horizon with an
interval on the *difference*; the cumulative abnormal return event study; a
histogram of episode start dates showing calendar clustering; raw N against
effective N; and the number of configurations tried.

---

## 7. What this project should do about all of it

Ordered by value, not by effort.

1. **Add the matched control.** The horizon fix gives a base rate, not a
   comparison. Until there is a control, regression to the mean is an
   unexcluded explanation of the whole result.
2. **Cluster standard errors by name**, and report effective N beside the
   episode count.
3. **Measure the return, not only the indicator** — same survival analysis on
   realised abnormal return net of costs.
4. **Replace the double correlation cleaning with one RIE step** (ADR-009
   amendment), keeping the current path behind a flag so the two are comparable
   on the same run.
5. **Run the no-manifold baseline** (ADR-010 amendment) to establish what the
   geometry is worth.
6. **Start the hypothesis log before the next experiment**, not after.
7. **Introduce a permanent instrument identifier** (ADR-023) — worth doing now
   only because a second universe is planned, and because ticker-as-identity
   has already produced one wrong answer.

---

## 8. Where the public record is thin

Stated so nobody mistakes inference for evidence:

- No detailed public architecture exists for the internal feature stores of
  Two Sigma, Point72/Cubist, Millennium, Balyasny, Squarepoint or AQR. Man
  Group is an outlier in openness because ArcticDB is open-sourced — and
  ArcticDB is a storage engine, not a feature store.
- No public account of an actual capital- or risk-committee sign-off workflow
  at a named quant fund was found. Descriptions of such governance are inferred
  from how larger funds are described operating.
- No small-fund practitioner account of how the deflated Sharpe ratio or the
  Harvey–Liu–Zhu hurdle is operationalised day to day was found. The
  recommendation to keep a hypothesis log is derived from what those tools
  require as inputs, not from a documented small-fund practice.
- No audited post-2010 track record for the classic Avellaneda–Lee construction
  exists publicly.

---

## Selected references

- Avellaneda, M. & Lee, J.-H. (2010). *Statistical Arbitrage in the US Equities Market*. Quantitative Finance 10(7).
- Bailey, D. & López de Prado, M. (2014). *The Deflated Sharpe Ratio*.
- Bun, J., Bouchaud, J.-P. & Potters, M. (2017). *Cleaning Large Correlation Matrices: Tools from Random Matrix Theory*. Physics Reports 666. arXiv:1610.08104.
- Chordia, T., Goyal, A. & Saretto, A. (2020). *Anomalies and False Rejections*. RFS 33(5).
- Do, B. & Faff, R. (2010). *Does Simple Pairs Trading Still Work?* FAJ 66(4).
- Gidea, M. & Katz, Y. (2018). *Topological Data Analysis of Financial Time Series: Landscapes of Crashes*. Physica A 491.
- Guttal, V. et al. (2015). *Lack of Critical Slowing Down Suggests that Financial Meltdowns Are Not Critical Transitions*. PLOS ONE 10(12).
- Harvey, C., Liu, Y. & Zhu, H. (2016). *…and the Cross-Section of Expected Returns*. RFS 29(1).
- Khandani, A. & Lo, A. (2011). *What Happened to the Quants in August 2007?* JFE.
- Kolari, J. & Pynnonen, S. (2010). *Event Study Testing with Cross-Sectional Correlation of Abnormal Returns*. RFS.
- Laloux, L., Cizeau, P., Bouchaud, J.-P. & Potters, M. (1999). *Noise Dressing of Financial Correlation Matrices*. PRL 83, 1467.
- Ledoit, O. & Wolf, M. (2004; 2017). *Honey, I Shrunk the Sample Covariance Matrix*; *Nonlinear Shrinkage of the Covariance Matrix for Portfolio Selection*.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*.
- MacKinlay, A.C. (1997). *Event Studies in Economics and Finance*. JEL.
- Mantegna, R. (1999). *Hierarchical Structure in Financial Markets*. Eur. Phys. J. B.
- Marti, G., Nielsen, F., Bińkowski, M. & Donnat, P. (2021). *A review of two decades of correlations, hierarchies, networks and clustering in financial markets*. arXiv:1703.00485.
- Pu, X., Roberts, S., Dong, X. & Zohren, S. (2023). *Network Momentum across Asset Classes*. arXiv:2308.11294.
