# geomarket

QuantHaxs selected option contracts can be ingested as optional native
Parquet run artifacts; see [the options integration guide](docs/options-native.md).

Geometric market manifold — equity relationship geometry for statistical
arbitrage. See [ADR.md](ADR.md) for the full design (data sources, math,
architecture, milestones) and [PRIOR-ART.md](PRIOR-ART.md) for what has
already been tried in this space, what the evidence supports, and what it
does not. [HYPOTHESES.md](HYPOTHESES.md) logs every claim this instrument
has been pointed at and where each one stands; [BLOCKED.md](BLOCKED.md)
records every limit that cannot be closed from inside this repository,
with the measurement behind it. This file is the quickstart.

The instrument's purpose, stated once so it is not inferred from whichever
number happens to be in front of you: this is a **research instrument for
finding candidate dislocations geometrically**, not a trading strategy.
The measurement that decides whether it works is ADR-013's gate — and the
gate is a *difference against matched controls*, not a base rate and not a
backtest Sharpe. That distinction was learned the hard way here: the
reversion base rate conditioned on depth and on news is large, sharp and
monotonic, and turns out to be regression to the mean, which comparable
unflagged names exhibit just as much. A base rate cannot tell the two
apart. The Sharpe ratio is reported only as a supporting check, from a
crude execution model over a small number of positions, with its sample
size attached.

> **The ADR-013 gate has been run against a matched control and is not passed.**
> Flagged excursions do not revert more than comparable unflagged names on the same day:
> zero of five horizons show a significant positive difference, at any of four calipers,
> over matched samples of 435 to 5,137 pairs. The reversion base rates are real and are
> not evidence of anything, because matched controls do the same thing. This repository
> claims no predictive value. See the ADR-013 amendment, [HYPOTHESES.md](HYPOTHESES.md)
> for what is open, and [BLOCKED.md](BLOCKED.md) for what cannot be closed here.

## QuantHaxs options bridge (first slice)

`tools/options_bridge.py` imports a manifested QuantHaxs 8-K options run as a
separate `gm-options` artifact. It preserves event identity, strategy outcomes,
capacity rows, and SHA-256 provenance. It does not change the equity geometry
or treat its scores as a validated option signal.

From this checkout inside QuantHaxs, import the current smoke study:

```bash
python tools/options_bridge.py --study-dir ../data/processed/smoke \
  --output-dir runs/quanthaxs-smoke/gm-options
```

To attach equity context from a Lattice run, add
`--scores runs/<lattice-run>/gm-boundaries/scores.parquet`. The bridge joins
View B scores on **exact ticker and the pre-event `t_pre` session**. A score
from the event or entry session cannot fill a missing pre-event score. Reading
Parquet scores requires Python `pyarrow`; a CSV export with Lattice's score
columns also works without extra Python packages. Output paths are immutable:
choose a new directory for a new input or scoring run.

The current QuantHaxs dataset supplies selected contract daily closes and
volume, not synchronized full-chain quotes. This bridge supports an event
study and score-conditional analysis; it does not implement an options
volatility surface or execution model. See
[the integration plan](docs/options-integration-plan.md) for the boundary and
remaining data requirements.

## Prerequisites

| | Windows | Linux |
|---|---|---|
| Compiler | MSVC (Visual Studio 2022, C++ workload) | GCC 13+ |
| CMake | ≥ 3.27 | ≥ 3.27 |
| Generator | Ninja | Unix Makefiles (see note) |
| Git | required | required |

vcpkg itself is **not** a prerequisite — it is bootstrapped into
`tools/vcpkg/` by the steps below and pinned to the exact commit in
`vcpkg.json`'s `builtin-baseline`, so every clone builds the same
dependency versions.

**Linux note:** the `linux-gcc-*` CMake presets use the "Unix Makefiles"
generator, not Ninja, so a from-scratch box needs no extra package
beyond what's in the table above. If `ninja` happens to be installed,
nothing stops you from adding a Ninja preset locally.

**Linux note on build tooling without root:** several ports (Thrift, for
Arrow's Parquet support; glfw3's X11 backend) need build-time tools that
are not always present and are easy to get wrong without root:

- `flex` + `bison` — if missing, `apt-get download flex bison libfl-dev
  libfl2 m4` and extract each with `dpkg -x <deb> <prefix>` (no root
  needed for download-only + local extraction). Put `<prefix>/usr/bin`
  on `PATH` **and** export `BISON_PKGDATADIR=<prefix>/usr/share/bison` —
  bison hardcodes `/usr/share/bison` at compile time and does not locate
  its data files relative to its own binary, so without the env var it
  fails with `m4sugar.m4: cannot open` partway through Thrift's build.
- `autoconf` + `automake` + `libtool` (+ `autoconf-archive`) — same
  `apt-get download` + `dpkg -x` approach for packages `autoconf
  automake libtool libtool-bin autoconf-archive autotools-dev`. Export
  `ACLOCAL_PATH=<prefix>/usr/share/aclocal:<prefix>/usr/share/aclocal-1.16`
  so `aclocal`/`autoreconf` find autoconf-archive's macros (e.g.
  `AX_CHECK_COMPILE_FLAG`, used by glfw3's `pthread-stubs` dependency) —
  without it, `autoreconf` fails with "possibly undefined macro" or
  `vcpkg_run_autoreconf` fails outright asking you to `apt install`
  packages that don't need installing, only extracting.

(This is exactly how the project's remote build box — no sudo — is set
up; see the M0 session notes in git history for the literal commands.)

## Building

```bash
git clone <this repo>
cd equities
git clone https://github.com/microsoft/vcpkg.git tools/vcpkg
cd tools/vcpkg && git checkout $(grep '"builtin-baseline"' ../../vcpkg.json | sed -E 's/.*"([0-9a-f]{40})".*/\1/') && cd ../..
./tools/vcpkg/bootstrap-vcpkg.sh -disableMetrics   # or bootstrap-vcpkg.bat on Windows

cmake --preset windows-msvc-release   # or: linux-gcc-release
cmake --build --preset windows-msvc-release
ctest --preset windows-msvc-release
```

The first configure builds every pinned dependency from source (Arrow is
the long pole — expect 30-90 minutes on the first run, cached
thereafter). Subsequent configures are fast.

**The `tools/vcpkg` checkout must be at the baseline commit**, which is
what the `git checkout` line above does. Pointing it at a newer vcpkg —
or at an existing system-wide one — fails during dependency resolution
with *"osqp does not exist"*, because the pinned baseline names versions
that a newer ports tree no longer carries. Measured cost of getting this
wrong: the error arrives 27 minutes in, after everything else has built.

**Windows** additionally needs a Developer Command Prompt (or
`vcvars64.bat`) so `cl.exe` is on `PATH`, and Ninja on `PATH` — if CMake
reports *"unable to find a build program corresponding to Ninja"*, pass
`-DCMAKE_MAKE_PROGRAM=<path to ninja.exe>`.

Both platforms are verified green at **422 tests**: `linux-gcc-release`,
`linux-gcc-asan`, and `windows-msvc-release`, and CI runs all three on
every push (`.github/workflows/ci.yml`) with a benchmark regression gate.

## Repository layout

See ADR.md §8.1 for the full annotated layout. Short version:

- `libs/gm-core/` — strong types, error handling, config, manifest, the
  NYSE trading calendar. No financial math lives here yet (that starts
  in `libs/gm-geometry/` etc. from M1 onward).
- `apps/gm-*/` — one CLI executable per pipeline stage (ADR-006). Each
  reads a TOML config plus upstream artifacts and writes its own
  artifacts and manifest under `runs/<run_id>/<stage>/`.
- `apps/gm-run/` — orchestrates the full chain end to end.
- `runs/` — immutable, run_id-keyed output (gitignored; regenerate
  rather than diff).
- `tests/golden/` — end-to-end pipeline tests that actually invoke the
  built binaries and check their artifacts.

## Data discipline: point-in-time, or it does not ship

Every backtest in this repo must only ever see information that was
actually available on the day it is simulating. That sounds obvious and
is the single easiest thing in quantitative research to get wrong,
because the failure is silent: the equity curve looks better, not
broken.

The rule is enforced at the data layer rather than left to the
discipline of each stage.

**Two dates, never one.** Any record describing a company carries both:

- `period_end` — the date the figures are *about* (e.g. a quarter end).
- `available_date` — the date those figures were actually *published*.

Any stage simulating day `D` may only read records where
`available_date <= D`. Never `period_end <= D`.

The distinction is not pedantic. A company's Q1 results describe the
quarter ending 31 March, but are not published until some weeks into
May. A backtest that joins them on `period_end` is trading on 31 March
using numbers no participant could have seen until May. Across fifteen
years that produces a strategy that appears to work and cannot be
traded.

**Estimated availability is labelled as such.** Many free fundamental data
sources record `period_end` but not `available_date`. Where
`available_date` has to be estimated (a deliberately pessimistic lag
after `period_end` rather than an optimistic one), the run manifest
records `fundamentals_availability = "estimated"`. A run built on real
publication dates records `"reported"`.

**SEC XBRL is the exception, and it is the source this project uses.**
Every fact in `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
carries a `filed` field — the actual EDGAR submission date of the filing
that reported it:

```json
{"start":"2022-09-25","end":"2023-09-30","val":96995000000,
 "accn":"0000320193-23-000106","form":"10-K","filed":"2023-11-03"}
```

So `available_date` here is **measured, not estimated**, and a run built
on it records `"reported"`. `filed` also errs in the safe direction:
companies press-release earnings days to weeks before the 10-Q reaches
EDGAR, so a backtest using `filed` sees the numbers slightly *later* than
the market did — the pessimistic side, which is the side to be on.

Two caveats that keep this honest. XBRL was phased in from 2009 for large
filers, so the earliest years of ADR-002's 2010 start need a per-issuer
coverage check rather than an assumption — that check is a reported
dataset statistic, not something to take on trust. And a company reports
the *same* period many times, in its own filing and again as a
comparative in later ones; the reader keeps every one of those vintages,
because collapsing them to the newest is look-ahead bias wearing the
costume of deduplication.

That flag exists so the distinction survives contact with time. Six
months after a run, nobody remembers which numbers were solid;
without the flag, estimated data silently acquires the authority of
measured data. Consumers that care about the difference check the
manifest rather than trusting the filename.

Swapping in a paid point-in-time source (ADR-016) replaces the
estimated dates with reported ones and flips the flag. No schema
change, no recomputation of anything else — which is why the machinery
is built before the data is bought, not after.

**Survivorship.** The same principle governs the universe itself
(ADR-001, ADR-016): names are included for the period they were
actually index members, not selected by who survived to today.

That was the intent from the start; for a while it was not what the
code did. The universe came from the current-constituent table, which
is correct about arrivals and blind to departures — a name dropped from
the index in 2014 is not in the file at all, so it was missing from
every historical day it belonged to. ADR-016 assigned that gap to a
paid point-in-time vendor. The gap was real; the assignment was wrong.
The index article's *revision history* is free, reaches back past 2010,
and carries the full constituent table at every revision, so membership
reconstructs from it directly (`tools/sp500_membership_history.py`):
211 monthly revisions, 919 tickers ever a member, **413 of them gone
from today's list**.

What that was costing, per date — the universe as it was against the
universe as it should have been:

| Date | Was | Should have been | Missing |
|---|---|---|---|
| 2010-01-04 | 266 | 499 | 233 (47%) |
| 2016-01-04 | 329 | 504 | 175 (35%) |
| 2020-01-02 | 406 | 505 | 99 (20%) |
| 2024-01-02 | 456 | 503 | 47 (9%) |
| 2026-08-28 | 503 | 503 | 0 |

In January 2010 the universe held 266 of the 499 names actually in the
index, and every one of the 233 missing had later left — which is the
population that drags returns down. Over the whole panel it is
1,566,334 ticker-days against 2,106,845.

413 is an upper bound, not a clean count: a ticker **rename** looks
exactly like one name leaving and another arriving. Bank of New York
Mellon became `BNY` in May 2026, so `BK` runs for 207 observations and
then stops — which is also why the price source cannot retrieve it, the
old symbol no longer resolving. A prefix sweep of the departed list
turns up roughly twenty candidate pairs, several coincidental and the
sweep missing `BK`→`BNY` itself, so renames are a few percent of the
total rather than a large share. Both consequences run the conservative
way: the gap is a little smaller than 413, and price coverage of
departed names a little better than a third.

**This is fixed for membership and not for prices.** Knowing PXD
belonged in the 2015 universe does not produce its price series, and
the free source mostly does not have it: of a 60-name sample of
departed tickers, queried over a window when each was genuinely a
member, about a third come back with a usable series
(`tools/delisted_price_coverage.py`). So the denominator is now right
and the residual is a measured coverage figure rather than an unknown —
which is the difference between a bounded gap and a silent one, not
between a gap and no gap.

`gm-universe` writes `membership_source` into its manifest, so no
artifact can look point-in-time when it is not, and rows for departed
names carry `metadata_available = false` rather than a plausible-looking
blank where their sector and CIK would be.

## Status

This section describes what is **built and verified**. It deliberately
says nothing about what the results *mean* — in particular, whether
ADR-013's reversion gate passes is a question about findings, not about
code, and answering it here by implication would be exactly the kind of
quiet overclaim the rest of this repo is written to avoid.

**Test suite: 422 tests, green in `linux-gcc-release`, `linux-gcc-asan`
and `windows-msvc-release`.** Every milestone below closes only on that
set (ADR.md §13).

The Windows leg had never actually been run before, and running it found
nine defects — including one that mattered: **`gm-run` could not launch a
single stage on Windows**, because `cmd.exe` strips the outermost quotes
of a command line that begins with a quote and contains more. The golden
test that exists to catch precisely that had the same bug in its own
invocation, so it could never have reported it.

### Built

| Milestone | What exists |
|---|---|
| M0 — Skeleton | Repo, CMake presets, vcpkg manifest, `gm-core`, NYSE calendar, all nine stages wired end-to-end |
| M1 — Data layer | `gm-io` (Parquet, HTTP+cache, CSV), point-in-time universe, `gm-ingest` with validation screens; 15-year panel builds |
| M2 — Geometry | Shrinkage, RMT clipping, Mantegna distance, classical MDS, Procrustes, MST, with reference tests |
| M3 — Boundaries + viewer | Mahalanobis, KDE level set, marching tetrahedra; views A and B; `gm-view` against real artifacts |
| M4 — Signals | Peer baskets, OU fitting, excursion tracking, earnings/8-K tagging, the reversion study |
| M5 — Backtest | Walk-forward engine, cost model, Deflated Sharpe, `gm-sweep` sharding |
| M6 — Depth | FastMCD, tear veto, remaining viewer tabs, SEC company profiles, ETF co-membership |
| M7 — Valuation | SEC XBRL tag chains measured against real filings, `fundamentals.parquet`, `valuation.parquet`, View D |
| Since M7 (Sept 2026) | Valuation gate wired into the backtest and measured three ways; View C's boundary on `(z, ż)`; beta and idiosyncratic volatility, real; ADR-015's retroactive-change screen; point-in-time membership including departed names (ADR-016); the reversion study measured **within a horizon**, with censoring handled (ADR-013); CI, benchmarks with a machine-independent gate, and byte-identical determinism goldens (ADR-020) |

### The two views, on screen

`gm-boundaries` fits a boundary around two different things, and the
viewer now draws both — which one depends on what is being looked at:

| | The points are | The surface is |
|---|---|---|
| **View A** | every equity on one date | the market's envelope that day |
| **View B** | one equity across many dates | that equity's own envelope, from its trailing history |

What View B's envelope *looks* like depends on how far back it reaches,
and the shape is itself a readout. Over a 21-day window it is a tube when
the name has been trending and a blob when it has been chopping sideways
— measured across 69 dates, about **two in three** are visibly elongated
(median longest:middle 2.4 for AAPL). Over the 756-day default it is
always a region, because across three years a name does not travel along
a curve, it wanders and revisits.

The surface also breaks into **disconnected lobes** when the trailing
window genuinely occupied separate regions — AAPL around the COVID crash
is the clear case. A single ellipsoid cannot represent that, which is why
the KDE estimator exists alongside the Mahalanobis one. See ADR §8.3.

The distinction matters because the interesting question is not "is this
name unusual" but "unusual *compared to what*". View A answers it against
its peers today; View B answers it against its own recent selves.

**A View B tube is fitted to history strictly before its own date.** So
the current point can sit outside its own tube — and that is the finding,
not a rendering fault. It is the same fact as the `inside` column being
false, in a form you can see.

Both surfaces are opt-in (`boundaries.write_meshes`), because the scores
are the deliverable and do not depend on meshes existing. View B is
additionally opt-in *per ticker*: 81 names x 4129 dates is roughly a third
of a million meshes, and each is about 30x the work of a View A one. See
ADR §8.3.

The pipeline also carries **any number of embedding dimensions** end to
end — `geometry.embedding_dims = 10` now produces a genuinely
10-dimensional fit rather than a 3-dimensional one with a 10 in the
manifest. Two consequences are documented where they bite: `x/y/z` are not
comparable across a change to `embedding_dims` (Procrustes aligns in the
full k), and above three dimensions the drawn surface is a shadow of the
scored boundary rather than the boundary itself.

### ADR-022, the valuation geometry (View D)

A second robust ellipsoid per equity, over point-in-time valuation yields
rather than embedding coordinates, so the pipeline can distinguish "this
name diverged because it got cheap" from "this name diverged because the
business is deteriorating". Price geometry alone cannot see that
difference, and it is the difference the reversion gate turns on.

| Piece | State |
|---|---|
| ADR-022 + §6.6 (the design) | Written down, in this repo, not in a conversation |
| `gm::features::valuation` — the as-of rule and the three yields | Built, 21 tests, per-coordinate availability |
| `gm::data::fundamentals` — the SEC XBRL reader | Built, tested |
| Accounting tag chains — the thing that was blocking it | Built, 15 tests, **14 deliberate defects reintroduced and caught** |
| `gm-ingest` → `fundamentals.parquet` | Built, run against real SEC filings |
| `gm-features` → `valuation.parquet` | Built |
| View D fit in `gm-boundaries` | Built — same estimators and same causal window as View B |

**The blocker was real and it is now measured rather than guessed.** EBITDA
and enterprise value are not XBRL concepts: they have to be assembled from
tags that different filers use differently, and some do not report at all.
Downloading companyfacts for 40 S&P issuers and counting gives the honest
answer, per issuer:

| Yield | Derivable for | Why the misses |
|---|---|---|
| **E/P** | 40/40 (100%) | — |
| **FCF/P** | 39/40 (98%) | one issuer reports no capex tag |
| **EBITDA/EV** | 29/40 (72%) | mostly **structural**: banks report no operating-income subtotal, because that is not how a bank's income statement is built |

The full run bears this out across 98 issuers: net income, cash, D&A,
operating cash flow and share count all resolve for 98/98, while operating
income resolves for 86, long-term debt for 94, capex for 93 and short-term
investments for only 73. Two issuers produce no usable rows at all. Every
one of those counts, and which tag won for each issuer, is in the stage
manifest rather than in this README — a README goes stale, a manifest is
generated by the run that produced the data.

That measurement changed the design rather than just documenting it. The
original rule rejected a whole ticker-day if any field was absent, which
would have thrown away E/P and FCF/P — perfectly computable — for 28% of
issuers, over a third coordinate that does not apply to them. Availability
is now **per coordinate**, and each axis's coverage is published separately
so one blended figure cannot hide which axis is the weak one.

Two further rules the chains follow, both learned from a real run:

- **A partial sum is refused.** Three of twelve issuers reported no
  depreciation-and-amortisation aggregate. Falling through to
  `us-gaap:Depreciation` alone silently omitted amortisation and understated
  EBITDA. The chain now prefers a reported aggregate, else adds *both*
  components, else reports the concept absent. Half an add-back is a
  plausible number that is quietly too small, which is worse than none.
- **Absence means zero only where absence means zero.** No
  `ShortTermInvestments` tag almost certainly means the issuer holds none —
  nobody files a zero, they omit the line. No `cash` tag is a gap, and
  reading *that* as zero would fabricate a balance sheet. Every substituted
  zero is counted, and split between "this filer reports none" and "not
  published by this date yet", because those call for different responses.

### Known gaps, stated plainly

- **The gate is not passed, and this README does not claim it is.** The
  reversion study now measures `P(reverted by H days)` per depth quartile
  and per news condition, and the curves separate — deeper excursions
  revert *slower*, and excursions with an 8-K in their span revert at 33%
  by day five against 54% without. That is a base rate. It is not yet a
  comparison against a matched control, which is what would show the
  geometry adds anything beyond ordinary mean reversion; until it exists,
  regression to the mean explains the whole table. ADR-013's amendment
  lists the three things still required. ADR §13 records that later
  milestones were built before this one was genuinely met.
- **`gm-report` does not write the HTML report ADR-007 describes.** There
  is no `gm-plot`; the stage writes `reversion_study.json` and
  `excursions_tagged.parquet`. The viewer became the human-readable record
  instead. ADR-007 is marked open rather than quietly retired.
- **FRED is not ingested**, so the VIX overlay in the design is not drawn.

- **EBITDA/EV is the weak axis and always will be.** Per ticker-day on the
  full 98-issuer run, of 341,358 days that have a market capitalisation:
  E/P is present for **94.6%**, FCF/P for **77%**, EBITDA/EV for **53%**,
  with a further 4,431 days excluded for a non-positive enterprise value.
  View D therefore defaults to fitting in
  `[earnings_yield, fcf_yield]`. Adding the third axis is one config key,
  and it does not enrich the fit so much as shrink the cross-section it is
  fitted to — the run reports how many ticker-days that costs, so the trade
  is visible rather than assumed.
- **A row's coordinates can describe different periods.** Net income is
  re-reported as a comparative in nearly every later filing, so it has far
  more vintages than capex or operating income do. Requiring an exact period
  match meant such a vintage produced a row carrying net income and nothing
  else — costing that day its other coordinates entirely, since the consumer
  keeps one row per ticker-day. Each field now takes the most recent figure
  for its period **or earlier** that was public by the row's own
  `available_date`. No look-ahead is introduced: the availability cutoff is
  unchanged and only the period relaxes, backwards. Measured on a
  twelve-issuer run before and after, it raised FCF/P coverage from 64% to
  94% of ticker-days and EBITDA/EV from 39% to 57%. Rows that used an
  earlier-period figure are counted in the manifest.
- **ADR-020's reference-test requirement is met for every routine it
  names**, each against something derived independently of the code:

  | Routine | Reference |
  |---|---|
  | Ledoit–Wolf shrinkage | hand-derived values on a fixed dataset |
  | Marchenko–Pastur clipping | the published closed-form bulk edges |
  | Classical MDS | exact recovery of planted coordinates |
  | Procrustes | recovery of a known rotation and a known reflection |
  | FastMCD | the published Hawkins–Bradu–Kass example |
  | OU fitting | parameters recovered from simulated paths |
  | Deflated Sharpe | **the paper's own worked numerical example** |
  | NYSE calendar | published Easter dates and exchange holiday lists |
  | Fundamentals reader | Apple's filed figures |

  This entry previously claimed only two of these were covered. That was
  understated, which is the same fault as overstating it in the other
  direction — the README is meant to say what is true.
- **View D has been fitted, but its results have not been studied.** The
  pipeline computes it; whether "cheap and diverging" actually separates
  from "deteriorating and diverging" in the scores is a research question
  this repo has not answered, and nothing here claims it has.
- **XBRL coverage does not reach the start of the price window, and now
  that is measured rather than suspected.** Across 40 issuers, counting the
  earliest EDGAR filing date present in `companyfacts`:

  | Concept | Median first available | Issuers covered at 2010-01-04 |
  |---|---|---|
  | net income (E/P) | 2010-08-02 | 19/40 (48%) |
  | operating cash flow (FCF/P) | 2010-08-02 | 19/40 (48%) |
  | operating income (EBITDA) | 2010-11-24 | 13/40 (32%) |
  | long-term debt (EV) | 2010-08-03 | 15/40 (38%) |

  Those medians line up with the SEC's own phase-in — large filers from
  June 2009, mid-tier June 2010, everyone June 2011 — so this is the
  mandate schedule showing through, not a gap in the reader. The practical
  consequence: **View D is thin before roughly mid-2011** and does not
  become broadly available across the universe until then, while the price
  geometry runs from 2010-01-04. Any study using both has to say which
  window it means. `tools/xbrl_coverage_start.py` reproduces the table.

### Two measured behaviours that look like bugs and are not

**FastMCD declines to fit one frame at ten dimensions, and no frame at
three.** Scoring View A alone over the identical 2010-2026 panel:

| Embedding | FastMCD failures | Where |
|---|---|---|
| `embedding_dims = 3` | 0 | — |
| `embedding_dims = 10` | 81 | all on **2014-04-16**, one per ticker |

Same data, same estimator, same dates; only the dimension differs. At
k=10 the h-subset is 46 points and the covariance is 10x10, and on that
one date no subset of the frame yields a non-singular one — so the
estimator reports "no valid candidate found across all trials" instead of
inverting something it should not. The other two estimators score that
frame normally, which is the disagreement ADR-007 calls a first-class
output. The manifest now records where each estimator first failed, not
just how often, so this took two minutes to localise rather than being
inferred from a count.

**View D's two default axes are barely two axes.** E/P is net income over
market cap and FCF/P is free cash flow over market cap — the same
denominator. Between filings both numerators are constant, so the two
coordinates are exactly proportional and every day in that quarter lies on
one ray through the origin. A trailing window is a fan of about twelve
such rays, and when the cash-flow-to-earnings ratio is stable across them,
the fan collapses toward a line.

Measured over 200,730 windows on the full 86-ticker production run:

| | |
|---|---|
| median \|correlation\| between the two axes | **0.73** |
| 90th percentile | **0.988** |
| windows above 0.99 | **19,102 (9.5%)** |
| windows Mahalanobis and FastMCD both refuse to fit | **9,123 (4.5%)** |

The refusals *are* the collinearity rather than a separate problem —
Mahalanobis names it, reporting a near-singular covariance with points
degenerate or collinear in some dimension. KDE, which inverts nothing,
fits every one of them.

An 11-ticker test run had put the median at 0.87 and the >0.99 share at
17%; the production figures are lower, and overstating a finding is as
much a fault as not measuring it. Either way the reading is the same: a
second coordinate that is largely a copy of the first adds columns, not
information. A genuinely independent second axis means EBITDA/EV — a
different denominator — at 53% ticker-day coverage instead of 77%. Which
side of that trade is right is a research question this repo has not
answered.

### The one property everything else rests on

ADR-020 asks that View B scores be **causal**: recomputing with future data
truncated must change nothing. That is the most load-bearing claim in this
project and the one whose violation is hardest to notice — a look-ahead
leak does not crash, does not fail a unit test, and does not produce
implausible numbers. It produces *better* numbers, and a backtest built on
one looks like a discovery.

It now has three tests, run against the real stage binary:

1. **Truncation.** The same panel scored to date D, and scored again with
   fifty more days appended, must agree *exactly* on every date up to D.
2. **Sensitivity.** Two runs differing only in lookback must *disagree* on
   most shared dates — otherwise the first test is comparing two things
   that would match regardless, and proves nothing.
3. **Exclusion of today.** A ticker jumping five units out of a cloud
   spanning 0.02 must score enormously outside its own boundary.

The third exists because mutation testing showed the first cannot see that
bug: extending the window by one day to include the scored point is not
look-ahead relative to the end of the panel, so both runs agree and the
property passes while the estimator is quietly ruined — the more unusual a
day is, the better it hides. And the third test's *own first version* was
also non-discriminating, which mutation testing caught as well: `depth` is
a signed margin, so a ratio assertion is vacuous whenever the control is
negative. Both are written up in the test file.

### How the tests here are meant to be read

A regression test that has never been watched to fail is a claim, not a
test. Everything above described as "defects reintroduced and caught"
means exactly that: the bug was put back into the source, the project was
rebuilt, and the test was confirmed to fail before the bug was removed
again. This convention exists because an earlier commit in this repo
claimed three tests each pinned a specific bug when two of them detected
nothing at all — a review found 13 of 14 tests passing against the very
bugs they were named after. Where a test does *not* catch something it
might be assumed to, the test file says so.
