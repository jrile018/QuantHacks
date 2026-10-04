# Hypothesis: executive departures are bad news that the market under-reacts to (packaged software)

Written 2026-10-04 (America/New_York morning), BEFORE any event return was computed. Event classes were built from the
raw 8-K Item 5.02 text by `data/packaged_software/classify_departure_events.py`; only event types and counts had been
seen when this was written (A officer departure 371, of which 266 senior; B officer retirement 59; C director departure
248; D other 1,093).

## Economic hypothesis
**Who is on the other side?** Holders who price an officer exit as a one-day headline and assume a successor fixes it.
**Why it may persist:** unplanned officer exits (resignation, termination, step-down) correlate with undisclosed
operating or governance problems that surface over the following weeks; arbitrage is limited because the names are small
and costly to short.
**Prediction:** after the first tradable close, companies announcing an unplanned officer departure (class A) earn
negative 4-factor abnormal returns over the next 20 trading days.
**It fails if:** the mean 20-day cumulative abnormal return is not distinguishable from random-date placebos, does not
survive 2x costs, or exists only in the day-of reaction (before we could trade).

## Primary test (one only)
Class A events, all roles, 20-trading-day cumulative abnormal return starting at the first close strictly after the
filing date, 4-factor adjusted (market, size, value, momentum). Secondary tests (reported, but not used to claim an
edge, with a Bonferroni count disclosed): horizons 5 and 60; senior subset (CEO/CFO/COO/President); successor named
vs not; classes B, C, D as placebos (expected about zero); announcement-window reaction (non-tradable diagnostic).

## Protocol (fixed)
- Entry at the close of the first session strictly after the filing date (no intraday acceptance time is available, so
  a same-day move is never claimed). Windows must lie fully inside the factor calendar (ends 2026-08-31) or the event is
  dropped, not truncated.
- Abnormal return = daily return minus rf minus factor loadings estimated on trading days [-250, -30] before entry
  (at least 150 observations, otherwise the event is dropped).
- One event per company per 20 trading days (later overlapping events dropped).
- Eligible: price >= $3 and verified identity at entry. Minimum events for a group to be reported: 30.
- Inference: mean CAR with a month-clustered bootstrap, plus a placebo (200 random dates per event drawn from the same
  company outside +/-10 trading days of any Item 5.02 filing). Not tuned.
- Out-of-sample = events with entry on or after 2025-11-03 (about the last 20% of history), evaluated once, after a
  development pass that only reports events before that date.
- Costs for a tradable short: 10 bp per side (also 20 and 50), no borrow cost, no short-availability constraint
  (both stated as limits).

## Known limits
Survivors-only universe; 8-K item classification is rule-based on text (about 90% precise in a small spot check);
announcement time of day unknown; borrow cost for shorts not modeled; event count is modest, so confidence intervals
are wide; the earlier thesis-composite work looked at the same companies.
