# Biologics FDS dataset (SIC 2836)

> **Known problem (found 2026-10-04).** Five columns carry future information: `px_close_raw`, `fin_shares_adj_m`, `fin_mktcap_m`, `fin_log_mktcap`, `fin_liq_to_mcap`. They come from a price file that is adjusted for splits that happened later, so a past price can reveal a future reverse split. Drop these five and join `fds_realprice.csv` (same `cik` and `date` keys: `px_close_real`, `fin_mktcap_real_m`, `fin_log_mktcap_real`, `fin_liq_to_mcap_real`), built by `scripts/44_offer_noleak.py` from `data/raw/splits.csv`. Return and ratio columns are not affected. Dollar volume is not affected (the source adjusts volume too).

Point in time company snapshot. One row per company per market day. 89,150 rows, 139 companies, 2024-01-02 to 2026-10-02.

## Files (data/fds/)
| File | What it is |
| --- | --- |
| fds_features.csv | The matrix. Numbers only. 156 feature columns plus `cik` and `date` (YYYYMMDD). |
| fds_missing.csv | Same shape. Reason code for every cell (see fds_lookup_codes.csv). |
| fds_labels.csv | Outcomes (next returns, will an 8-K come). Kept separate so labels can never leak into features. |
| fds_dictionary.csv | Every column: block, unit, definition. |
| fds_fin_provenance.csv | Every financial value used: company, tag, period end, filed date, usable-from date, SEC accession number. |
| fds_lookup_*.csv | cik to ticker, code meanings. |
| fds_price_cleaning_log.csv, fds_share_*.csv | Every price or share-count fix that was applied. |

Rebuild: `python scripts/16_build_fds.py` then `python scripts/16b_write_fds.py` (the first step saves a checkpoint, the second writes the files).

## Design choices and why
1. **Row = company x market day, not one row per 8-K.** The team plan needs "what did we know before the first release". A daily snapshot answers that for any day, and 8-K days are just rows. It also keeps quiet days, so we can learn what normal looks like.
2. **Decision clock = market close (21:00 UTC rule).** Matches the team's Benchmark chat so the files join.
3. **One day lag on anything with only a date.** SEC data gives a filing date, not a time. A filing from day D is usable from D+1. This costs up to a day of freshness but removes any chance of using a filing that came out after the decision. Check: smallest filing age in the data is 1 day. News has a real timestamp, so it is usable if published before 21:00 UTC.
4. **Restatements handled as they happened.** For each company and item, the value is whatever the latest filing before that date said. Later corrections do not rewrite the past.
5. **Trailing 12 month flows are rebuilt from filed periods** (latest annual + current year to date - same period last year). Quarterly 10-Q numbers are cumulative, so this is the only safe way.
6. **Numbers only.** Company is `cik`. Dates are integers. Text sources (8-K type, news) enter as counts, days-since, or scores. Blank = NaN and the reason is in fds_missing.csv. The team spec says blanks need reasons ("not reported" is not the same as "not applicable").
7. **Labels in their own file.** Features at day t, outcomes after t.

## Blocks
financials (balance, flows, derived: runway, cash vs market cap, dilution), market (returns, volatility, volume, distance from high, XBI/SPY state), filings (counts and days-since by form type, 8-K item counts), 8-K category history (Massive categories grouped: trial, regulatory, offering, deal, management, listing, earnings, presentation, debt), insider (Form 4 buys and sells), news (volume, sentiment, spike), trials (leak-safe subset), regulatory (FDA action dates already mentioned in earlier 8-Ks, openFDA approvals), calendar.

## What was left out on purpose
- **ClinicalTrials.gov forward dates and status.** The registry is a snapshot from Oct 2026, so "trial ends in 90 days" would use dates that were revised later. Only start dates, completion dates already passed, and results-posted dates are used. Remaining risk: a trial may have been registered after it started, so some counts can run slightly early. Fix: re-pull `studyFirstSubmitDate` from the registry (the sandbox could not reach it).
- **Options coverage.** Not collected yet (needs the Massive key run on a machine that can reach it). Roughly 39% of trial result events had steady options trading in the earlier check. Add a `has_options` column before choosing the tradable universe.
- Purple Book (no ticker link yet).

## Data problems found and fixed
- Price source is already split adjusted to today. Bad prints and sub-2-cent bars dropped (see log).
- Some companies entered share counts x1000 in XBRL (one made a market cap of $7 trillion). Fixed by checking neighbours; 7 fixes logged.
- Reverse splits: older cover-page shares are divided by later reverse splits so market cap matches the adjusted price.

## Checks run
- 300 random balance sheet values re-derived from the raw SEC files using only filings before the date: 300 match.
- 400 random rows re-counted for 8-K counts, days-since, trial-result 8-Ks, insider buys: 0 mismatches.
- TTM equals the annual figure when the period ends on a fiscal year end: 46 of 46.
- No feature has a rank correlation above 0.04 with next-day return (no sign of leakage).
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
