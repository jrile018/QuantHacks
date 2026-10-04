# Blocked, unfixable, and deliberately deferred

Every known limit of this repository that cannot be closed by writing
more code here, with the measurement that establishes it and what it
would take to close it. A gap that is merely *unbuilt* belongs in
ADR.md §13 (the milestone list); a question that is merely *unanswered*
belongs in HYPOTHESES.md. A gap in this file is one of:

- **Blocked on the user** — needs a credential, a purchase, or a
  decision that is not the pipeline's to make.
- **Blocked on a third party** — the data does not exist in any free
  source, or the source that had it withdrew it.
- **Not fixable** — a property of the world or of the historical record.
  The honest response is to measure the size of it and say so, which is
  what each entry below does.

Every figure is from `runs/pit-survivorship` (panel 2010-01-04 to
2026-08-28) unless stated otherwise. Where an entry says "measured", a
tool or a stage manifest reproduces the number.

---

## 1. Price history for companies that left the index

**Not fixable from free sources. Measured.**

`gm-universe` knows all 919 tickers that were ever S&P 500 members
across 211 monthly observations, including the 413 that have since
departed (ADR-016 as amended). Knowing the membership turned out to be
free. Getting the *prices* for a company acquired in 2014 is not: the
free provider serves a chart endpoint keyed on a live ticker, and a
ticker that no longer trades returns 404.

Measured over the full departed set:

| | |
|---|---|
| Tickers requested | 897 |
| Tickers with a usable series | 634 (71%) |
| Rejected | 263 (29%) |
| — HTTP 404 / non-2xx (`io_failure`) | 132 |
| — Response carried no timestamp block (`parse_failure`) | 82 |
| — Failed the ADR-015 >±50% daily-return screen | 49 |

The 71% flatters it, because it counts a series of any length.
`tools/delisted_price_coverage.py` asks the stricter question — is there
history covering the period the name was actually a member — and gets
roughly one in three.

**Consequence.** The geometry is drawn from a cross-section complete in
*membership* and incomplete in *prices*. The residual bias runs the same
direction as classical survivorship bias but is far smaller than the gap
before the membership fix, when January 2010 saw 266 of the 499
companies actually in the index.

**What would close it.** A paid point-in-time equity panel (CRSP,
Norgate, Sharadar, Polygon flat files). ADR-016 records that as the
user's decision; nothing in this repository will execute a purchase.

---

## 2. Second price source

**Blocked on the user: needs an API key.**

ADR-015 asks for a second independent price source so a bar can be
cross-checked rather than trusted. The retroactive-change screen
(`ingest.compare_against_run`) catches a provider *rewriting its own*
history across two runs; it cannot catch a provider that was wrong the
same way both times.

Tiingo is the intended second source and requires a key tied to an
account. **The key must not be written into a config file in this
repository** — it would land in git history on a public remote. Read it
from the environment.

Until then: one source, and the manifest says so.

---

## 3. Valuation data before mid-2011

**Not fixable. A property of the historical record.**

Valuation coordinates (E/P, EBITDA/EV, FCF/P — ADR-022, View D) are
built from SEC XBRL company facts, gated on `available_date` so nothing
is read before it was published. XBRL was phased in by filer size
between 2009 and 2011, largest filers first, everyone else by fiscal
periods ending after 15 June 2011.

The valuation panel therefore thins going backwards, and it thins
*non-randomly*: the largest companies appear first. A cross-sectional
valuation boundary in 2010 is a boundary fitted mostly on mega-caps and
should be read that way.

Measured coverage, per ticker-day that has a market capitalisation:

| Coordinate | Coverage |
|---|---|
| Earnings yield (E/P) | 100% |
| Free-cash-flow yield (FCF/P) | 94% |
| EBITDA/EV | 57% |

EBITDA/EV is why `boundaries.view_d_axes` defaults to two axes: a
boundary is fitted in one space, so every point must carry every
configured axis, and the third shrinks the cross-section rather than
enriching the fit.

**What would close it.** Nothing free. Pre-2009 fundamentals in
machine-readable point-in-time form is a vendor product (Compustat
point-in-time, S&P Capital IQ). Same decision as entry 1.

---

## 4. Market capitalisation is absent from the default run

**Not blocked — a switch, with a cost. Recorded so the absence is not
mistaken for an oversight.**

`ingest.fetch_fundamentals` is `false` by default, so the default run
has no `fundamentals.parquet`, therefore no `shares_outstanding`,
therefore no market capitalisation and no View D. The default is off
because it is one SEC request per issuer and each `companyfacts`
document is 10–40 MB.

Direct consequence for the matched control (ADR-013 / M8): size is a
covariate a control ought to be matched on, and with fundamentals off it
is unavailable. `gm-report` matches on the covariates it actually has
and **names the missing ones in `reversion_study.json` under
`matched_control.primary.covariates_unavailable`** rather than quietly
matching on fewer things and reporting a same-looking number. Turn
`fetch_fundamentals` on and the covariate appears; the study always
states which set it used.

Currently reported there: `log_market_cap`.

---

## 5. A ticker rename is invisible to the permanent key

**Partly fixed. The residue is not fixable from these sources. Measured.**

ADR-023 is implemented: `universe.parquet` carries an `instrument_id`,
taken from the SEC CIK where one exists — a permanent per-issuer
identifier that survives every ticker change.

What it found, on the real panel:

| | |
|---|---|
| Instruments | 894 |
| Provisional (ticker stand-in, no CIK) | 394 |
| Aliases (one instrument, several tickers) | 3 |
| Reused tickers (one ticker, several instruments) | 0 |

All three aliases are **dual share classes** — GOOG/GOOGL, FOX/FOXA,
NWS/NWSA — not renames. A CIK is per-issuer, not per-security, and this
project holds one line per company, so that is a distinction the key
cannot express. It is the reason the key is a tagged string rather than
a bare integer: a share-class namespace can be added later without
invalidating anything already written.

**Zero renames found, and that is the finding.** The old ticker of a
rename is exactly the one with no CIK — gone from the current
constituents table, so no metadata row, so a `TICKER:` stand-in, so the
link is invisible. The blind spot is 394 names wide and it is precisely
the population where renames live.

Three real renames confirmed by hand that the permanent key cannot see:

| From | To | Last seen | First seen |
|---|---|---|---|
| `BK` | `BNY` | 2026-04-19 | 2026-05-23 |
| `ANTM` | `ELV` | 2022-05-20 | 2022-06-29 |
| `FB` | `META` | 2022-05-20 | 2022-06-29 |

**What partly reaches them.** `tools/detect_ticker_renames.py` looks for
the shape instead of the metadata: one ticker's last observation
immediately followed by another's first. 1,469 such handoffs, 46 of them
one-for-one. Roughly a fifth of the one-for-one list is real (WMI→WM,
AA→ARNC, DLPH→APTV, CTL→LUMN, MYL→VTRS, COG→CTRA, WLTW→WTW) and the
rest are coincidence — `AIV`→`TSLA` and `ALXN`→`MRNA` are the reminder.

**Why it stops there.** A genuine departure at observation *N* and an
unrelated addition at *N+1* have the identical shape. Membership dates
alone cannot separate them, so the tool reports candidates with their
handoff crowding and refuses to resolve. Confirming one needs a
corporate-actions feed this repository does not have — same vendor
decision as entry 1.

Both remaining effects are conservative: an unresolved rename inflates
the departure count and splits one history into two shorter ones, which
understates coverage rather than overstating it.

---

## 6. No VIX or macro regime series

**Blocked on a decision, not on data.**

ADR §8.2's artifact contract once listed a `vix` column in
`regime.parquet`. FRED was never ingested, so the column was never
written, and the contract has since been corrected to match the code
rather than the other way round.

Cheap to close — FRED's CSV endpoint needs no key — and not done because
nothing downstream reads it. Listed so the absence reads as a recorded
choice: the tear-flag regime detector (ADR-012) keys off the panel's own
correlation structure and nothing external.

---

## 7. The local bare mirror must be updated by hand

**Blocked on the user. One command, which only a human should run.**

Two remotes exist:

| Remote | Where | State |
|---|---|---|
| `github` | `github.com/jrile018/Lattice.git` | current |
| `origin` | `/home/john-riley/git/geomarket.git` | pre-rewrite |

The single-author history rewrite means `origin` cannot fast-forward, so
bringing it up to date needs a forced update of `main`. A safety hook
blocks that, deliberately, and it should stay that way — an agent
overwriting a backup mirror unattended is exactly what the hook exists
to prevent.

To do it: on the remote box, in `~/projects/geomarket`, run `git push`
to `origin main` with the force flag.

`github` is the real destination and is in sync. Nothing in the pipeline
depends on the mirror; it is a backup.

---

## 8. The free endpoints are undocumented and can vanish

**Not fixable. A standing operational risk, mitigated rather than
solved.**

The price endpoint is an undocumented chart API with no stability
guarantee, and the membership reconstruction reads an encyclopedia's
revision history. Both are free, both work today, neither is a contract.
The revision-history route exists *because* the "changes" table
previously used was withdrawn from that article — the failure mode is
not hypothetical, it has already happened once to this project.

What makes this a risk rather than a blocker:

- Every fetch is cached on disk (ADR-015), so a run reproduces from
  cache with no network at all.
- The retroactive-change screen compares ~1.9M bars against a prior run
  and fails loudly if history was rewritten underneath.
- The >±50% daily-return screen rejects a series rather than admitting a
  bad bar — the 49 `validation_failure` rejections in entry 1 are that
  screen doing its job.
- Reconstruction is a tool (`tools/sp500_membership_history.py`) whose
  output is a checked-in CSV, so the panel survives the source going
  away.

---

## 9. Delisting is inferred, not observed

**Not fixable from the current sources. Handled explicitly, and measured
to be immaterial in this panel.**

When an excursion is still open at the end of a ticker's price series
there are two very different reasons, and this repository cannot always
tell them apart:

- The panel ended (administrative censoring). The episode would have
  gone on; calling it "did not revert" invents a failure never seen.
- The company stopped existing — acquired, taken private, delisted. The
  episode can never revert. Calling it censored is wrong in the opposite
  direction: Kaplan-Meier assumes censoring is independent of outcome,
  and a takeover is emphatically not.

`gm-report` separates the two with an Aalen-Johansen cumulative-
incidence estimator (`libs/gm-signals/competing_risks.hpp`), classifying
an episode as a competing event when the ticker's price series ends more
than `report.delisting_gap_days` (default 10) trading days before the
panel does.

**Measured: zero competing events**, against 13 censored out of 7,110
episodes. Aalen-Johansen and Kaplan-Meier agree exactly here. The active
universe is the liquid top hundred and those names do not get acquired
mid-panel.

The estimator stays wired in, because that is a property of *this*
universe rather than of the method — on a small-cap or a wider universe
the same code would have something to find, and `km_overstatement` in
the artifact would stop reading zero.

The inference remains a heuristic: with no corporate-actions feed, a
name that stopped being *covered* looks identical to one that stopped
*existing*. Same vendor decision as entry 1.

---

## 10. Cluster-robust intervals use a normal critical value

**A known small-sample approximation, stated rather than hidden.**

`libs/gm-signals/cluster.hpp` reports two-way cluster-robust standard
errors (ticker and calendar month) and forms intervals with a normal
critical value of 1.96, not a *t* quantile on a cluster count. With the
79 tickers and 197 months of the full panel the two agree closely. On a
narrow slice — one sector, one year — they do not, and the interval
reads too tight.

Every estimate therefore carries `clusters_ticker`, `clusters_month` and
`min_clusters`. **Any bucket where `min_clusters` is below about 30
should be read as indicative only.** A proper small-sample *t* or a wild
cluster bootstrap would close this; not done because the buckets that
matter are far above that threshold.

The two-way variance can also come out non-positive (a known property of
the Cameron-Gelbach-Miller subtraction). When it does, the code falls
back to the larger one-way variance and sets
`two_way_variance_adjusted`, rather than emitting a standard error the
arithmetic did not produce.

Related and *not* a defect: `effective_n` sometimes exceeds the
observation count. A matched pair shares a date, so the market-wide
component is common to both and cancels in the contrast — the clustering
correctly finds the same-day design more efficient than independent
sampling, not less.

---

## 11. Open questions live in HYPOTHESES.md, not here

"Unexplained" and "blocked" get confused, so the boundary is worth
stating: this file is for things that cannot be closed from inside the
repository. Live research questions — including the two that matter most
— are logged in `HYPOTHESES.md` with their status and what would settle
them:

- **H1**, the gate: flagged excursions do **not** revert more than
  matched controls, at any horizon or caliper tested.
- **H2**: deeper excursions revert more *slowly*, monotonically, and
  nobody knows why.
- **H3**: whether the MDS embedding adds anything is currently
  **untestable as stated**, because the embedding is not in the signal
  path — k-NN peer selection runs on the full-precision distance matrix
  and the coordinates feed only the viewer and the tear-flag detector.

---

## Keeping this file honest

Add an entry when something cannot be closed from inside this
repository. Move an entry out when it can be. Every claim of size here
is a measurement with a tool or a manifest behind it, and an entry that
loses its measurement should lose its place in this file.
