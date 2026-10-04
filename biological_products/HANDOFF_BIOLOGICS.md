# Biologics (SIC 2836) hand-off, version 3

Owner: Abhay. Written 2026-10-04 (version 3, after the team lead's audit of commits 2d07581 and 583e472). Universe: 139 tickers, Biological Products (no diagnostic substances).
Everything uses public data. Every number can be rerun with the commands in section 8. The previous versions of this document are in the git history (f3fc5cf1, 2d075817, 583e472b).

## 0. What changed since the audit, finding by finding

The lead's audit found nine problems (A1 to A9). Status of each:

| Finding | What it was | What was done | Where |
|---|---|---|---|
| A1 high: trial features used today's registry records | `tr_*` columns were built from a ClinicalTrials.gov pull made in Oct 2026 and placed on past days, so later edits reached the past | Rebuilt from the 35 monthly AACT snapshots (Nov 2023 to Sep 2026): day t uses the latest snapshot dated before t, only trials already posted by that snapshot, only ACTUAL completion dates, start dates moved to month end, results postings count from the next day. A new column `tr_snapshot_age_days` (1 to 35) records how old the registry view is | `scripts/16_build_fds.py` v2, trials block |
| A1 extra, found by our own independent review | News block used 21:00 UTC as the close, which is 5pm New York in summer, so 4 to 5pm press releases counted as same day | Close is now 16:00 America/New_York. SEC comment letters (`fil_seccorr_n180`) dropped (released weeks after their date). Spike filter no longer looks at the next day's bar | same |
| Split look-ahead (first audit) | five columns from a split-adjusted price file | Removed from the dataset itself: `px_close_real`, `fin_shares_now_m`, `fin_mktcap_m` (now real) replace them | same |
| A2 high: portfolio windows leaked past their dates | daily curve took a trade's whole path into its signal window | Replaced by one continuous cash ledger (script 49); windows are clipped by calendar; a position open across the boundary puts its days in each window; idle days included; reconciliation to the cent is asserted | `scripts/49_ledger.py` |
| A3 medium: mixed price clocks in costs | gross from daily bars, costs from quotes | Per trade gross and net now both from the quotes (mid to mid, and sell at bid / cover at ask / XBI at ask and bid). The bar version is printed next to it for comparison. Script 45 now stops on a date mismatch instead of warning | `scripts/45_offer_trades_v2.py` |
| A4 medium: fixed daily weights implied free rebalancing | | Ledger holds fixed share counts from entry, converts shares across splits, charges borrow daily on short market value, no rebalancing, no interest on cash. Six fixtures with known answers run before every real run, including the audit's own 2-share example | `scripts/49_ledger.py --selftest` |
| A5 medium: intervals assumed independent trades | | Per trade tables now show two intervals: trades resampled one by one, and whole signal weeks resampled. Ledger shows block bootstraps at 5, 10, 20 and 40 days. Wording changed (section 4) | `scripts/42_standard_results.py`, 49 |
| A6 medium: shelf side study used the leaky market cap | | Rerun on dataset v2 (real market cap). Lift still zero (+0.0000 on every shelf feature) | `scripts/24_shelf_features.py`, `25_lift_check.py` |
| A7: FINRA short interest coverage unverified | | Evidence script: 68 settlement dates 2023-11-15 to 2026-09-15, all 139 tickers present, 16 tickers on fewer than 80% of dates (new listings), exchange-listed names present, no zero rows. Values are as published at pull time (2026-10-04); FINRA corrections replace earlier values and cannot be undone | `scripts/52_finra_evidence.py` |
| A8 medium: unsafe columns still in the dataset, stale docs, no source registration | | Dataset v2 no longer holds them; the dataset README lists the removed columns. Old `docs/README.md` marked superseded. Source registration bundle prepared for `configs/sources/biologics-fds-daily` (section 11) | `data/fds/README_FDS.md`, `source_registration/` |
| A9 medium: the MATCH checker could pass unequal files | | Rewritten: same row sets required, every numeric column compared under tolerance, NaN pattern compared, ledger curve compared day by day, input and output hashes written to `reports/run_manifest.json`, exit 1 on DIFFERENT, exit 2 on a bad reference; the launcher uses `set -e` so a checker failure fails the job. The two false-pass fixtures are kept as regression tests (`--fixtures`) | `scripts/46_compare_run.py`, `hpg_bundle/run_noleak.sbatch` |
| Matched controls (repair item 7) | | For each traded signal, up to 3 non-flagged names on the same day in the same market cap and runway bucket. See section 5 | `scripts/48_offer_v3.py` |
| Borrow availability | | Still an assumption (30%/yr). No free source has 2025 history; iborrowdesk keeps one year; SEC filings hold no borrow data. Listed as the main open item | section 10 |

**Not done, said plainly:** historical borrow rates and availability (no public source), a frozen never-touched holdout period (the hold length, the slice and the window split were all chosen with results visible; section 4), and the ten-trade team engine cross-check was not rerun on the new signal.

## 1. Bottom line

1. **Dataset (version 2):** one row per company per market day, 2024-01-02 to 2026-10-02, 89,151 rows, 155 numeric features plus keys, labels in a separate file. Built point in time as far as the sources allow; the known limits are in section 7. It is not called "leak-free" anywhere.
2. **The offering model works as a predictor.** AUC 0.68 out of sample, quarterly walk forward. Of the company-days it flags, 12.4% are followed by an offering 8-K within 5 days, against 2.0% for all eligible company-days and 3.8% for matched controls (same day, same size and runway bucket).
3. **Before costs the flagged stocks fall against matched peers.** Per trade Sharpe 1.13 in sample and 1.41 out of sample (quote mid to mid, 5 day hold, XBI hedge); matched controls -0.01 and -0.31. The two windows agree with each other.
4. **After real bid/ask fills and a 30% yearly borrow fee there is nothing left.** Per trade Sharpe 0.30 and -0.01. As a real account (cash ledger, fixed shares, 20% of NAV per trade): return +3.2% and +3.9% over the two windows, Sharpe 0.31 and 0.31, every interval includes zero, drawdowns of -24% and -34%. **No tradable edge is claimed.**
5. **Two other strategies were tested and rejected**: the trial registry strategy (Sharpe -0.13 and -0.43) and buying after an offering 8-K through the team engine (1.86 on 12 events, 0.11 on 21).
6. **Where it ran.** Dataset build, model, quotes and all tables ran on a laptop first; the same code was then run as a frozen job on HiPerGator from this branch and compared file by file with the committed outputs (section 6).

## 2. The standard used for every result

The lead asked for in-sample and out-of-sample windows of about equal size. The offering model needs 2024 to train, so it has trades from January 2025 to August 2026 (20 months), cut in half:

| Window | Dates | Months |
|---|---|---|
| In sample | 2025-01-01 to 2025-10-31 | 10 |
| Out of sample | 2025-11-01 to 2026-08-31 | 10 |

- **Per trade tables (section 3):** a trade belongs to the window of its signal date. Sharpe = mean / standard deviation of the per trade result, times sqrt(252 / 5). Two 95% intervals: trades resampled one by one (assumes independent trades, optimistic) and whole signal weeks resampled (allows for overlap and shared market shocks). Win rate = share of trades above zero. These are event statistics, not account returns.
- **Cash ledger (section 3):** one continuous account, every market day from the first trade to the last, idle days included. A window's result is the account's daily P&L on the days inside the window, so a position open across the boundary contributes its days to each side and nothing is counted twice. Intervals by stationary block bootstrap at 5, 10, 20 and 40 day blocks. This is the realistic number.
- The window split was chosen after the first results were seen (the earlier document used 2024-2025 vs Jan-Aug 2026). Every script takes the dates as arguments.

## 3. Standard results

### Per trade

| Strategy | Engine | Costs | Window | Trades | Avg per trade | Median | Win rate | Sharpe | 95% (trades independent) | 95% (signal weeks resampled) |
|---|---|---|---|---|---|---|---|---|---|---|
| Offering short | ours | none (quote mid to mid) | in sample | 94 | +2.91% | +1.22% | 56% | 1.13 | -0.28 to 2.51 | -0.38 to 2.71 |
| Offering short | ours | none (quote mid to mid) | out of sample | 90 | +2.46% | +1.96% | 59% | 1.41 | -0.05 to 3.03 | -0.11 to 2.99 |
| Offering short | ours | none (daily bars, for comparison) | in sample | 94 | +2.97% | +1.48% | 53% | 1.17 | -0.27 to 2.57 | -0.39 to 2.67 |
| Offering short | ours | none (daily bars, for comparison) | out of sample | 90 | +2.54% | +1.50% | 58% | 1.47 | 0.00 to 3.06 | -0.01 to 3.09 |
| Offering short | ours | real bid/ask fills + 30%/yr borrow | in sample | 94 | +0.77% | -0.92% | 45% | 0.30 | -1.19 to 1.67 | -1.36 to 1.83 |
| Offering short | ours | real bid/ask fills + 30%/yr borrow | out of sample | 90 | -0.02% | -0.27% | 48% | -0.01 | -1.46 to 1.51 | -1.45 to 1.51 |
| Offering short, entry spread under 2% | ours | real bid/ask fills + 30%/yr borrow | in sample | 63 | +1.74% | -0.23% | 48% | 0.58 | -1.23 to 2.30 | -1.30 to 2.42 |
| Offering short, entry spread under 2% | ours | real bid/ask fills + 30%/yr borrow | out of sample | 56 | +1.35% | +1.10% | 52% | 0.79 | -0.98 to 2.94 | -1.04 to 3.04 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | in sample | 83 | -2.74% | -2.80% | 47% | -0.13 | -0.59 to 0.32 | -0.60 to 0.34 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | out of sample | 81 | -7.39% | -7.22% | 40% | -0.43 | -0.91 to 0.00 | -0.88 to 0.01 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | in sample | 12 | +13.42% | +5.06% | 58% | 1.86 | -0.71 to 4.00 | -0.79 to 4.24 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | out of sample | 21 | +0.49% | -5.55% | 29% | 0.11 | -3.98 to 1.87 | -3.96 to 1.55 |
| Offering short, first-version signal priced by the team engine | team engine | none | in sample | 7 | too few | | | | | |
| Offering short, first-version signal priced by the team engine | team engine | none | out of sample | 13 | +0.67% | -0.94% | 46% | 0.38 | -4.20 to 4.12 | -3.95 to 4.30 |

Per trade results for the offering short are quote based: gross = mid quote to mid quote, net = sell at the bid, cover at the ask, XBI bought at the ask and sold at the bid, then minus the borrow fee (30%/yr for 5 days = 0.60%). The team engine rows and the trial registry rows use daily bars and have no quote data.

### Cash ledger (offering short, after costs, 20% of NAV per trade, at most 5 positions)

| Window | Days in window | First and last mark | Return | Annualized | Sharpe | 95% (block 5d) | 95% (block 20d) | 95% (block 40d) | Max drawdown | Idle days |
|---|---|---|---|---|---|---|---|---|---|---|
| In sample, 2025-01-01 to 2025-10-31 | 208 | 2025-01-03 to 2025-10-31 | +3.2% | +3.8% | 0.31 | -1.61 to 2.33 | -1.32 to 2.02 | -1.17 to 1.92 | -23.6% | 19 |
| Out of sample, 2025-11-01 to 2026-08-31 | 207 | 2025-11-03 to 2026-08-31 | +3.9% | +4.7% | 0.31 | -1.81 to 2.51 | -1.40 to 2.15 | -1.07 to 1.90 | -33.8% | 20 |

Whole account 2025-01-03 to 2026-10-01: 184 trades taken (6 rejected because the entry bid was under $1), NAV +21.7%, Sharpe 0.49, max drawdown -33.8%, borrow fees paid 18.3% of initial NAV. Sum of trade P&L equals the NAV change to the cent (asserted by the script).

### Charts (in `reports/`)

- `ledger_offering_short.png`: the cash ledger, one line, both windows shaded
- `std_offering_short.png`: per trade cohort curves by window (descriptive only; a trade's whole path is drawn in its signal window)
- `std_trial_registry.png`, `std_engine_buy_after_offering.png`, `std_engine_offering_short.png`: the rejected strategies
- `equity_*.png`, `summary_table.csv`, `team_backtest_*.csv`: first version outputs, kept for the record only

## 4. Does in sample match out of sample?

| Strategy | In sample | Out of sample | Reading |
|---|---|---|---|
| Offering short, before costs (per trade) | 1.13 | 1.41 | Agree. Both positive, intervals overlap, the in-sample interval touches zero |
| Offering short, after costs (per trade) | 0.30 | -0.01 | Agree on "about zero" |
| Offering short, cash ledger after costs | 0.31 | 0.31 | Agree on "about zero". This is the number to quote |
| Trial registry stage | -0.13 | -0.43 | No edge in either. Rejected |
| Buy after an offering 8-K | 1.86 | 0.11 | 12 and 21 events. Rejected |

On wording, following the audit: different point estimates with overlapping intervals do not show different distributions, and an interval that includes zero does not prove a zero effect. The justified statement is: the before-cost effect is consistent across the two windows and against matched controls; the after-cost result is indistinguishable from zero in both. This is a retrospective walk-forward evaluation with a reused evaluation window, not a clean holdout: the 5 day hold, the top 2% slice, the $1 and $1M floors and the window split were all settled with some results visible. The complete recipe (section 5) is frozen now for any future period.

## 5. Audit: why each number is what it is

### Offering short

- **Recipe (frozen).** Gradient boosted classifier (`HistGradientBoostingClassifier`, depth 3, 200 rounds, learning rate 0.05, min leaf 200, L2 5), retrained at each quarter start on all rows dated at least 12 days before the quarter, target = offering 8-K within 5 market days. Eligible company-day: real close at least $1 and 20-day average dollar volume at least $1M on the signal day. Trade the top 2% of eligible company-days by predicted probability each day, one open position per company. Short at the first quote after 09:30:30 on the next session (at the bid), buy XBI for the same dollars (at the ask); close both at the last quote before 15:59:50 five sessions after the signal (cover at the ask, sell XBI at the bid). Borrow 30%/yr on the short market value. Ledger: 20% of NAV per trade, at most 5 positions, no rebalancing, no interest on cash.
- **Model quality.** AUC by quarter 0.64 to 0.74, overall 0.68. Flagged company-days 437, hit rate 12.4% (54/437); among traded signals 12% in sample and 18% out of sample (different denominators: flagged days vs trades taken).
- **Matched controls.** 415 control company-days for 67 of the traded signals (same day, same market cap and runway bucket, not flagged; up to 3 per signal; signals with no match in the bucket have no control). Controls: -0.03% per trade in sample, -0.53% out of sample, Sharpe -0.01 and -0.31, offering rate 3.8%. Model picks: +3.0% and +2.5% before costs, offering rate 15.2% among the matched signals. Random eligible names made +2.2% and +0.6%. So the model picks underperform peers, and the picks are not explained by size or runway alone. This is a comparison, not a causal claim.
- **Costs are measured for the bid/ask part.** 190 of 191 trades have all four quotes (1 trade without quotes dropped). Mean cost 1.55% in sample and 1.84% out of sample (medians 1.34% and 1.00%); plus borrow 0.60%. Quote clock vs the old bar-plus-half-spread method: median difference 0.9 points per trade, 86 trades differ by more than 1 point. Quote timestamps and sizes were not saved by script 22 (known gap); a quoted price does not prove the size could be filled.
- **Concentration.** After costs, in sample: 5 best trades sum to +233 points against +73 for all 94; without them the per trade Sharpe is -0.84. Out of sample: -2 points in total, 5 best +117, without them -0.84. In sample the trades WITH an offering made +11.9% and the others -0.7%; out of sample +3.8% and -0.9%. So after costs the only profitable trades are the ones where the offering actually came.
- **Cost sensitivity (per trade Sharpe, in / out).** No borrow 0.52 / 0.32. 30% 0.30 / -0.01. 100% -0.23 / -0.78. 200% -0.99 / -1.87. Double spreads at 30% -0.30 / -0.99.
- **Tail risk.** Worst trades after costs: CVM 2025-07-22 -43%, SLXN 2025-03-03 -38%, PALI 2025-10-01 -34%, DBVT 2025-12-02 -34%. The ledger drawdown out of sample is -34%.
- **By half year, after costs, per trade average:** 2025 H1 +1.1%, 2025 H2 -0.4%, 2026 H1 +0.8%, Jul to Aug 2026 +2.6%.
- **Choices made with results visible:** the 5 day hold (holds of 1, 3, 5, 10 all positive before costs in both windows on dataset v2: 1.02/1.45, 0.89/1.31, 1.18/1.47, 0.98/1.33 by bars), the window split, and the first-version floor and gap changes. The top 2% slice and the $1 and $1M floors were in the first script.
- **How much the three rounds of fixes moved the numbers (before costs, per trade, in / out):** first version 2.25 / 1.83 (split leak, after-the-fact floor, old windows); after the split fix 1.26 / 2.51 (new windows); after the trial, news and clock fixes 1.13 / 1.41. After costs: 1.43 / 0.28, then 0.46 / 1.15, now 0.30 / -0.01. Each round removed information that should not have been there, and each round brought the two windows closer together.

### Trial registry stage (rejected)

- **Idea.** Sponsors update ClinicalTrials.gov quietly. Short a company under $2B when a record shows it is still building a trial (starts recruiting, adds 20%+ sites, raises its enrollment target), buy when enrollment is over. Hold 60 days, hedge with XBI, only when no 8-K was filed on the event day or the 2 days before.
- **Data.** 35 monthly AACT snapshots. A change counts only when a new record version was posted, dated by that posting date, usable the next day.
- **Result.** Per trade Sharpe -0.13 in sample and -0.43 out of sample after costs; 0.05 and -0.21 before costs. Rules were designed on events up to June 2025 (so the in-sample window is not clean for this strategy either). One short lost 219% of its stake (SRRK, trial success on 2024-10-07; outside both windows). Conclusion unchanged: no edge.

### Buy after an offering 8-K, team engine (rejected)

- `src.implementation.run_study` from the team repo at fa30fcb, unchanged, tag `public_offering`, our 139 tickers. 12 events priced in sample and 21 out of sample on the current windows (166 and 58 filings, 63 and 23 priced, on the earlier windows). The in-sample average rests on one event (IVVD +121%); the out-of-sample average is held up by one (OTLK +75%). Rejected.

### Offering short priced by the team engine (cross-check, first-version signal, not rerun)

- 155 first-version signal days through `price_events` and `evaluate`, unchanged. 34 priced, 7 and 13 in the standard cell. Too few to read. Kept only as a record of the cross-check.

## 6. HiPerGator runs

| Job | Node | What ran | Log |
|---|---|---|---|
| 44673323 | c0706a-s7 | First version: our backtests (scripts 39, 40) | `hpg_bundle/hpg_results/backtest_44673323.log` |
| 44673985 | c0706a-s3 | Team engine smoke test, 8 events | `lead_backtest_44673985.log` |
| 44674111 | c0702a-s7 | Team engine, `public_offering`, our universe | `lead_backtest_44674111.log` |
| 44675692 | c0704a-s1 | Team engine on the first-version signal days | `lead_signal_44675692.log` |
| 44679395 | c0710a-s3 | Second version (split fix only), scripts 44, 45, 42; matched the laptop with the OLD checker (A9) | `noleak_44679395.log` |
| TBD_JOB | TBD_NODE | **Version 3 frozen run**: scripts 48, 45, 42, 47, 49 (self test then real run), strict checker 46 with fixtures; input and output hashes in the log and in `reports/run_manifest.json` | `v3_TBD_JOB.log` |

The version 3 job copies the committed laptop outputs as its reference before running, prints their hashes, reruns everything from the committed inputs, and fails unless every row and value of the compared files agrees within 1e-6. The quotes (`stock_trades_real_v3.csv`, Massive API) and split history were downloaded on a laptop and are committed inputs; the team engine outputs are reused from jobs 44674111 and 44675692.

## 7. The dataset (version 2)

Join key: `cik` and `date` (integer YYYYMMDD). Files in `biological_products/data/fds/`.

| File | What it holds |
|---|---|
| `fds_features.csv` | 89,151 rows, 155 features: prices (real close, returns, volume), market, financials (filing date clock), filings, 8-K categories, insiders, news (16:00 New York clock), trials (monthly registry snapshots), PDUFA and FDA |
| `fds_missing.csv` | Same shape. One reason code per cell: 0 present, 1 not public yet, 2 never reported, 3 stale, 4 insufficient history, 5 not collected, 6 inapplicable, 7 derived |
| `fds_labels.csv` | Outcomes only. Never use as features |
| `fds_options.csv` | Option spreads and straddle prices seen at earlier 8-K events |
| `fds_shelf.csv` | Baby shelf features (rebuilt on v2 market cap) |
| `fds_short.csv` | FINRA short volume (lagged one day) and short interest (settlement + 14 days) |
| `fds_realprice.csv` | Script 44's rebuild of the real price; identical to v2's `px_close_real` (kept for the record) |
| `fds_dictionary.csv`, `README_FDS.md` | Column meanings, design choices, data fixes, the list of removed columns |

Removed in v2 (do not reintroduce): `px_close_raw`, `fin_shares_adj_m`, old `fin_mktcap_m`/`fin_log_mktcap`/`fin_liq_to_mcap`, `fil_seccorr_n180`, the current-snapshot `tr_*` columns.

Known limits that remain: the universe is today's SIC 2836 list (survivorship); trial snapshots are monthly, so registry edits inside a month are seen up to 35 days late (`tr_snapshot_age_days` says how late); the news sentiment model's provenance is not recorded; 8-K categories are the vendor's current classification; PDUFA dates are parsed from 8-K text by regex; `px_adv20_usd_m` relies on the vendor adjusting volume for splits (checked on 31 reverse splits: dollar volume before and after a split is similar, as it should be if volume is adjusted).

## 8. How to rerun

From `biological_products/scripts`:

```
python 16_build_fds.py                                   # dataset v2 (about 6 minutes; needs data/raw incl. aact_snapshots.csv, splits.csv)
python 48_offer_v3.py                                    # offering model on v2, matched controls, trade list
python 22_stock_real_costs.py --slice offer_signal_slice_v3.csv --out stock_trades_real_v3.csv   # real quotes (needs MASSIVE_API_KEY)
python 45_offer_trades_v2.py --version v3                # join trades with quotes, quote clock
python 42_standard_results.py                            # standard per-trade tables and charts
python 47_offer_audit.py --version v3                    # audit numbers in section 5
python 49_ledger.py --selftest ; python 49_ledger.py --trades offer_strategy_trades_v3.csv --quotes stock_trades_real_v3.csv   # cash ledger
python 46_compare_run.py --fixtures ; python 46_compare_run.py --ref <folder with reference outputs>   # strict comparison
python 24_shelf_features.py ; python 25_lift_check.py --extra fds_shelf.csv ; python 52_finra_evidence.py   # side studies and evidence
python 34_aact_extract.py ; python 35_aact_events.py ; python 36_aact_event_study.py   # trial registry events (needs the AACT zips)
```

On HiPerGator: check out this branch, `cd biological_products/hpg_bundle`, `sbatch run_noleak.sbatch`.

## 9. Other ideas tested and dropped

| Idea | Result |
|---|---|
| Long option straddles around 8-Ks | Lose about 43% after bid/ask costs. Spreads near 70% of the option price |
| Baby shelf limit features | No gain in out-of-sample AUC (rerun on v2: +0.0000) |
| FINRA short volume and short interest | No gain in AUC (-0.0011, interval includes zero) |
| Quiet expected-date delays on the registry | No stock move at 5, 20 or 60 days |
| Australian trial registry | 5 events for our small companies in three years. Too few |

## 10. Limits and open items

- **Borrow.** 30%/yr is an assumption. Many of these names cannot be borrowed at all, or cost far more. No public source has 2025 history (iborrowdesk: one year, blocks scripts; SEC: none; FINRA: positions only). Paid options: Ortex, QuantRocket; academic: WRDS Markit Securities Finance if UF subscribes. Until then no trade here is "executable", only "priced".
- **Fill size.** Quotes were saved without timestamps or sizes. A quote proves a price, not that 20% of a portfolio could trade at it.
- **Holdout.** Reused evaluation window; see section 4. The recipe is frozen now; the next clean test is any period after September 2026.
- **Survivorship**, monthly trial snapshots, sentiment model provenance: section 7.
- **Team engine cross-check** was not rerun on the version 3 signal.
- The standard windows cut 2024 (no model trades) and September 2026 (6 trades) out of both tables.

## 11. Housekeeping and integration

- Branch `biological-products-audit`, built on `main` at fa30fcb (PR #4). Shared code (`src/`, `run_all.py`) is untouched.
- Not in the repo because of size: `data/raw/aact/` (70 GB), `data/raw/aact_extract/`, `data/raw/aact_snapshots.csv`, `data/raw/companyfacts/`, `data/raw/research_cache/`. Scripts 00 and 34 rebuild them. No file holds an API key. The Massive key used during the work was exposed in a chat and should be rotated.
- **Source registration.** A bundle for `configs/sources/biologics-fds-daily/` (source.json, manifest.jsonl, README.md), a minimal adapter and tests, prepared per `docs/team-data/source-contract.md`, passes `scripts/validate_team_sources.py` in a test copy, stage `discovery`. It is in `biological_products/source_registration/` and NOT yet placed at the repo root, because the contract requires its own `codex/source-biologics-fds-daily-abhay` branch and a source-only PR. `source_registration/TODO.md` lists the fields a human must fill (URLs, hashes).
- `docs/README.md` and `docs/DATA_DICTIONARY.md` describe the first (per filing) pipeline and are superseded by `data/fds/README_FDS.md`.
- Old launchers `run_backtest.sbatch`, `run_lead_*.sbatch` are first-version; `run_noleak.sbatch` is the current one.
