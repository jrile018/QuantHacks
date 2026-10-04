# Hypothesis log

ADR §12, open question 14. One entry per claim this instrument has been
pointed at. The point of writing them down *before* looking is that a
hypothesis invented after seeing the answer is not a hypothesis, and a
sequence of them invented after seeing the answer is how a research tool
turns into a machine for confirming whatever it just produced.

Rules, few and strict:

1. **State the prediction before the run**, in a form that could come
   out false.
2. **Record the result whether or not it is the one you wanted.** A
   `NOT SUPPORTED` entry is the most valuable kind here — it is the
   only kind that removes something from the search space.
3. **Never delete an entry.** Supersede it, and link the successor.
4. **Name the run.** A result with no run directory behind it is an
   anecdote.

Status values: `OPEN` (stated, not yet tested) · `SUPPORTED` ·
`NOT SUPPORTED` · `INCONCLUSIVE` (tested, the test could not decide) ·
`UNTESTABLE AS STATED` (the experiment does not exist yet, and why).

---

## H1 — Flagged excursions revert more than comparable unflagged names

**Status: NOT SUPPORTED** · stated 2026-09-06 · tested 2026-09-24 ·
runs `pit-survivorship`, `rie-baseline`

This is ADR-013's gate, and the reason the project exists.

**Prediction.** An excursion outside the boundary earns a higher
sign-adjusted, cost-adjusted, basket-relative return over the next H
trading days than a matched control: same day, same GICS sector, similar
absolute 21-day move, similar idiosyncratic volatility and beta, but not
flagged.

**Result.** Zero of five horizons show a significant positive
difference, at any of four calipers, over matched samples from 435 to
5,137 pairs. Largest |t| anywhere is 1.60, and 0.49 under the RIE
estimator. Covariate balance is good throughout (worst standardized
difference 0.021 against a 0.10 bar), so this is not a failure to build
comparable groups.

| caliper | pairs | H5 | H10 | H20 | H40 | H60 |
|---|---|---|---|---|---|---|
| 0.15 | 435 | −0.0038 (−1.9) | −0.0037 (−2.3) | −0.0064 (−2.6) | −0.0000 (−0.0) | +0.0043 (+0.8) |
| 0.25 | 1322 | −0.0011 (−1.6) | +0.0001 (+0.1) | −0.0017 (−1.0) | +0.0000 (+0.0) | +0.0008 (+0.3) |
| 0.50 | 3497 | −0.0004 (−0.7) | +0.0006 (+0.7) | +0.0003 (+0.3) | +0.0018 (+0.9) | +0.0020 (+0.9) |
| 1.00 | 5137 | −0.0005 (−1.1) | +0.0006 (+0.6) | −0.0006 (−0.5) | +0.0007 (+0.4) | −0.0005 (−0.2) |

Where anything reaches significance it points the **wrong way**: at the
tightest caliper the flagged names did worse than their twins out to
twenty days.

**What this does and does not say.** It says the excursion-reversion
hypothesis built on correlation-distance peer baskets is not supported
by this panel. It does **not** say the geometry is uninformative — see
H3, which is a different claim that has not been tested.

**What would overturn it.** A different entry rule (H6), a different
outcome window, a conditioning variable that separates the population
(H5 is the obvious candidate), or a universe where dislocations are less
efficiently arbitraged than in the liquid top hundred.

---

## H2 — Deeper excursions revert faster

**Status: NOT SUPPORTED, and the reverse is unexplained** · stated
2026-09-05 · measured 2026-09-24 · run `pit-survivorship`

**Prediction.** A larger dislocation has more to give back, so deeper
excursions should revert *sooner*.

**Result.** Monotonically the opposite, and by a lot:

| depth quartile | n | reverted by day 5 | by day 20 |
|---|---|---|---|
| q1 shallowest | 1777 | 0.606 | 0.985 |
| q2 | 1777 | 0.482 | 0.964 |
| q3 | 1777 | 0.367 | 0.940 |
| q4 deepest | 1779 | 0.354 | 0.923 |

**Nobody has an explanation.** Three candidates, none currently
distinguished by anything computed:

- Depth partly proxies for news, and a news-driven move is a repricing
  rather than a dislocation. H5 is consistent with this and does not
  establish it, because depth and news are not independent.
- The boundary is misspecified in the tails, so the deepest "excursions"
  are partly a measurement artifact of the rolling z-score's own
  denominator.
- Dislocation size genuinely predicts persistence, which would be a real
  and interesting property of the market rather than of the instrument.

**What would settle it.** Re-run the depth split *within* the
news-conditioned buckets. If the depth gradient survives inside
`without_earnings_or_8k`, explanation one is dead. This is one report
change and has not been done.

---

## H3 — The MDS embedding carries information beyond the correlation distance it is built from

**Status: UNTESTABLE AS STATED** · stated 2026-09-06 (ADR-010 as
amended) · examined 2026-09-24

ADR-010 requires the embedding to beat a Mahalanobis baseline on
RMT-cleaned residuals before any claim rests on the geometry.

**Why it cannot be tested as written.** The embedding is not in the
signal path. Reading `apps/gm-geometry/main.cpp`:

```
returns -> correlation -> clean -> Mantegna distance D
        -> knn_and_mst_edges(D) -> edges.parquet -> peer baskets -> z
```

k-NN is built on the full-precision distance matrix, deliberately and
with a comment saying so, because View C's peer selection needs
precision the embedding compresses when `embedding_dims < n-1`. The MDS
coordinates feed the viewer and the persistence/tear-flag detector, and
nothing else.

So H1's result is a verdict on **correlation-distance peer baskets**.
The embedding never participated, and there is currently no signal built
on it to compare against anything.

**What would make it testable.** A peer-selection path that genuinely
uses embedding coordinates — k-NN in the 3-D embedding rather than in D
— run through the same gate. Then H3 becomes a real comparison. Until
that exists, ADR-010's requirement is grading a component that is
absent.

---

## H4 — A single RIE beats shrinkage-then-clipping

**Status: INCONCLUSIVE (no material difference)** · stated 2026-09-06 ·
tested 2026-09-24 · run `rie-baseline`

**Prediction.** Composing two competing estimators of the same corrected
spectrum optimises neither, so replacing them with one rotationally-
invariant estimator should produce better peer baskets and a visibly
different gate.

**Result.** It changes the distance matrix — excursions 7,110 → 7,423,
matched pairs 1,322 → 1,571, covariate balance 0.0128 → 0.0024 — and
does not change any conclusion. Kaplan-Meier base rates move under a
point (H5 0.452 → 0.459, H20 0.953 → 0.958). The gate verdict is
identical, with a smaller largest-|t| (1.60 → 0.49).

**What this is worth.** It rules out "the null is an artifact of the
double-cleaning", which was a live objection. It does not establish that
either estimator is better, because the outcome both are measured
against is itself null — there is no signal here for a better estimator
to sharpen. The comparison should be re-run if any entry rule ever
produces a positive H1.

---

## H5 — Excursions without news revert more than excursions with news

**Status: SUPPORTED as a base-rate split, NOT tested against controls** ·
stated 2026-09-05 · measured 2026-09-24 · run `pit-survivorship`

**Prediction.** A dislocation with an 8-K inside its span is a repricing
and should not come back; one without is noise and should.

**Result.** The split is large and in the predicted direction:

| bucket | n | reverted by day 5 | by day 20 |
|---|---|---|---|
| with earnings/8-K | 3057 | 0.335 | 0.920 |
| without | 4053 | 0.541 | 0.977 |

**The caveat that matters.** This is a *base-rate* split, exactly the
kind of number H1 established is not sufficient. A matched control has
not been run inside these buckets, so the difference is equally
consistent with news-free names simply being less volatile. **The
obvious next experiment on this whole list** is H1 restricted to
`without_earnings_or_8k`: it is the one conditioning variable that
separates the population sharply, and the gate has not been run inside
it.

---

## H6 — The entry rule is the problem, not the geometry

**Status: OPEN** · stated 2026-09-24

**Prediction.** `z_entry = 2.0` on a 60-day rolling window selects
dislocations that are already mostly arbitraged away by the time they
are detectable. A different rule — a faster window, a depth-and-velocity
condition on `(z, ż)` rather than a level crossing, a minimum
persistence before entry — would produce a population where H1 is
positive.

**Test.** The parameter sweep machinery exists (`gm-sweep`). This has
not been run, and running it *after* a null result is exactly where a
hypothesis log earns its place: a sweep across entry rules will find one
that looks good on this panel whether or not anything is there.

**Pre-commitment, recorded now, before the sweep:** any rule that comes
out of a sweep must be validated on a holdout the sweep never saw —
split by calendar, not at random, because excursions cluster in time.
A rule that only works on the period it was selected on is not a
finding.

---

## H7 — Survivorship bias was materially distorting the geometry

**Status: SUPPORTED for the geometry, NOT SUPPORTED for the gate** ·
stated 2026-09-05 · tested 2026-09-06 · run `pit-survivorship`

**Result.** The universe went from 1,566,334 to 2,106,845 ticker-days;
January 2010 had been showing 266 of the 499 companies actually in the
index. So the cross-section the boundary was fitted to was badly wrong.

But the *trading* panel barely moved — active universe 81 → 79,
excursions 7,376 → 7,110 — because the liquid top hundred are mostly
survivors. Both facts are worth keeping: the geometry was drawn from a
survivor cross-section, and the gate would have reached roughly the same
place either way.

---

## H8 — Delistings are biasing the reversion estimate upward

**Status: NOT SUPPORTED (immaterial in this panel)** · stated
2026-09-24 · tested 2026-09-24 · run `pit-survivorship`

**Prediction.** An episode open when a name is acquired can never
revert, and Kaplan-Meier treats it as censored — assume it behaves like
the survivors — which should bias reversion upward, hardest in the deep
buckets where takeovers concentrate.

**Result.** Zero episodes classified as competing events; 13 censored
out of 7,110. Aalen-Johansen and Kaplan-Meier agree exactly. The active
universe is the liquid top hundred and those names do not get acquired
mid-panel.

The estimator stays wired in, because this is a property of *this*
universe and not of the method — on a small-cap or a wider universe the
same code would have something to find. The measurement is what makes
that a statement rather than a hope.

---

## H9 — Valuation geometry (View D) separates dislocations that price geometry cannot

**Status: OPEN, blocked on data** · stated 2026-09-03 (ADR-022)

Untested because `ingest.fetch_fundamentals` is off by default and the
default run carries no `fundamentals.parquet`. Also bounded by
BLOCKED.md entry 3: the valuation panel thins non-randomly before
mid-2011, largest filers first, so a 2010 valuation boundary is fitted
mostly on mega-caps.

Worth testing after H5, not before — a conditioning variable that is
available for the whole panel beats one that is not.
