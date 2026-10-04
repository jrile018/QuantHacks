# Biologics FDS dataset (SIC 2836)

> **Version 2 (2026-10-04).** Rebuilt after the team lead's audit. Removed because they carried future information: `px_close_raw`, `fin_shares_adj_m`, the old `fin_mktcap_m`, `fin_log_mktcap`, `fin_liq_to_mcap` (built from a price file adjusted for later splits), `fil_seccorr_n180` (SEC letters are released weeks after their index date), and the `tr_*` columns built from an Oct 2026 registry pull. Added: `px_close_real` (real close, later splits undone using `data/raw/splits.csv`), `fin_shares_now_m` and a real `fin_mktcap_m`, `tr_*` rebuilt from monthly AACT snapshots with `tr_snapshot_age_days`. News now uses a 16:00 America/New_York close (was a fixed 21:00 UTC). The spike filter no longer looks at the next day's bar. Do not call this dataset leak-free: trial snapshots are monthly, the universe is today's list, and the sentiment model's provenance is not recorded.

Point in time company snapshot. One row per company per market day. 89,151 rows, 139 companies, 2024-01-02 to 2026-10-02. Version 2 (2026-10-04).

## Files (data/fds/)
| File | What it is |
| --- | --- |
| fds_features.csv | The matrix. Numbers only. 156 feature columns (v2) plus `cik` and `date` (YYYYMMDD). |
| fds_missing.csv | Same shape. Reason code for every cell (see fds_lookup_codes.csv). |
| fds_labels.csv | Outcomes (next returns, will an 8-K come). Kept separate so labels can never leak into features. |
| fds_dictionary.csv | Every column: block, unit, definition. |
| fds_fin_provenance.csv | Every financial value used: company, tag, period end, filed date, usable-from date, SEC accession number. |
| fds_lookup_*.csv | cik to ticker, code meanings. |
| fds_price_cleaning_log.csv, fds_share_*.csv | Every price or share-count fix that was applied. |

Rebuild: `python scripts/16_build_fds.py` then `python scripts/16b_write_fds.py` (the first step saves a checkpoint, the second writes the files).

## Design choices and why
1. **Row = company x market day, not one row per 8-K.** The team plan needs "what did we know before the first release". A daily snapshot answers that for any day, and 8-K days are just rows. It also keeps quiet days, so we can learn what normal looks like.
2. **Decision clock = market close, 16:00 America/New_York.** (v1 used a fixed 21:00 UTC, which is 5pm New York in summer; fixed in v2.)
3. **One day lag on anything with only a date.** SEC data gives a filing date, not a time. A filing from day D is usable from D+1. This costs up to a day of freshness but removes any chance of using a filing that came out after the decision. Check: smallest filing age in the data is 1 day. News has a real timestamp, so it is usable if published before 21:00 UTC.
4. **Restatements handled as they happened.** For each company and item, the value is whatever the latest filing before that date said. Later corrections do not rewrite the past.
5. **Trailing 12 month flows are rebuilt from filed periods** (latest annual + current year to date - same period last year). Quarterly 10-Q numbers are cumulative, so this is the only safe way.
6. **Numbers only.** Company is `cik`. Dates are integers. Text sources (8-K type, news) enter as counts, days-since, or scores. Blank = NaN and the reason is in fds_missing.csv. The team spec says blanks need reasons ("not reported" is not the same as "not applicable").
7. **Labels in their own file.** Features at day t, outcomes after t.

## Blocks
financials (balance, flows, derived: runway, cash vs market cap, dilution), market (returns, volatility, volume, distance from high, XBI/SPY state), filings (counts and days-since by form type, 8-K item counts), 8-K category history (Massive categories grouped: trial, regulatory, offering, deal, management, listing, earnings, presentation, debt), insider (Form 4 buys and sells), news (volume, sentiment, spike), trials (monthly registry snapshot subset), regulatory (FDA action dates already mentioned in earlier 8-Ks, openFDA approvals), calendar.

## What was left out on purpose
- **ClinicalTrials.gov forward-looking fields.** v2 trial features come from the monthly AACT snapshot available before each day (`tr_snapshot_age_days` = how old that view is). Planned completion dates are not used as features; a trial counts as completed only when the snapshot marks the completion ACTUAL. Trial-to-company mapping uses the Oct 2026 sponsor list (a trial whose sponsor changed is attributed to today's owner).
- **SEC comment letters** (`fil_seccorr_n180`, dropped in v2): the SEC releases them weeks after their index date.
- Purple Book (no ticker link yet).

## Data problems found and fixed
- Price source is split adjusted to today. v2 keeps the delivered series for returns and computes the REAL close from the split history (`px_close_real`); the delivered close is not written. Sub-2-cent bars dropped (see log). The v1 'reverting spike' filter looked at the next day's bar and was removed in v2.
- Some companies entered share counts x1000 in XBRL (one made a market cap of $7 trillion). Fixed by checking neighbours; 7 fixes logged.
- Reverse splits: v2 converts cover-page shares only by the splits between the filing date and the row date (`fin_shares_now_m`), and market cap = real close x those shares. (v1 divided by ALL later splits, which revealed future reverse splits; removed.)

## Checks run
- 300 random balance sheet values re-derived from the raw SEC files using only filings before the date: 300 match.
- 400 random rows re-counted for 8-K counts, days-since, trial-result 8-Ks, insider buys: 0 mismatches.
- TTM equals the annual figure when the period ends on a fiscal year end: 46 of 46.
- No feature has a rank correlation above 0.04 with next-day return. (This check did not catch the v1 split and trial problems; it is a weak test, kept only for the record.)
- Quick baseline, train to mid 2025, test Aug 2025 on, gradient boosting:
  - 8-K in next 5 days: AUC 0.66 calendar only, 0.73 with filing history, 0.73 with everything.
  - Offering/underwriting 8-K in next 5 days (2.5% base rate): 0.51, 0.58, 0.67. Financial and market data help most here.
  - Size of next-day move: rank correlation 0.29 from market features alone, 0.29 with everything. Nothing added.

## Known limits
- Universe is today's SIC 2836 list, so companies that were delisted before now are missing (survivorship).
- Cover-page share counts can be stale by a quarter; mktcap and dilution are approximate. Heavy tails in `fin_shares_chg_1y` and `fin_liq_to_mcap` (SPAC mergers, reverse splits): winsorize before modeling.
- `fin_debt_m` is empty for 64% of rows (companies often do not tag debt). Empty does not mean zero debt.
- About 3.5% of financial cells are older than 200 days (companies that stopped filing, e.g. SCNI, ELOX). Flagged with code 3.
- 8-K category history uses the Massive taxonomy from 2020; the PDUFA dates come from a text pattern and can include non-PDUFA dates.
