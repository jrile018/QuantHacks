# Biologics (SIC 2836) hand-off, version 3

Owner: Abhay. Written 2026-10-04 (version 3, after the team lead's audit of commits 2d07581 and 583e472). Universe: 139 tickers, Biological Products (no diagnostic substances).
Everything uses public data. Every number can be rerun with the commands in section 8, except that script 16 needs the AACT snapshot archive (not in the repo, 112 MB) and script 22 needs a Massive API key. The previous versions of this document are in the git history (f3fc5cf1, 2d075817, 583e472b).

## 0. What changed since the audit, finding by finding

The lead's audit found nine problems (A1 to A9). Status of each:

| Finding | What it was | What was done | Where |
|---|---|---|---|
| A1 high: trial features used today's registry records | `tr_*` columns were built from a ClinicalTrials.gov pull made in Oct 2026 and placed on past days, so later edits reached the past | Rebuilt from the 35 monthly AACT snapshots (Nov 2023 to Sep 2026): day t uses the latest snapshot dated strictly before t; only trials already posted by that snapshot; a trial counts as completed only when that snapshot marks its completion ACTUAL (planned completion dates are never used; start dates are used whatever their type); start dates moved to month end; results postings count from the next day. New column `tr_snapshot_age_days` (1 to 35). Remaining limit: the trial-to-company map is the Oct 2026 sponsor list, so a trial that changed hands is attributed to today's owner. No fixture yet for "an edit posted in 2026 leaves 2025 rows unchanged"; the mechanism guarantees it (a 2025 row can only read a 2025 snapshot), but it is not unit tested | `scripts/16_build_fds.py` v2, trials block |
| A1 extra, found by our own independent review | News block used 21:00 UTC as the close, which is 5pm New York in summer, so 4 to 5pm press releases counted as same day | Close is now 16:00 America/New_York. SEC comment letters (`fil_seccorr_n180`) dropped (released weeks after their date). Spike filter no longer looks at the next day's bar. (A first v2 build accidentally also dropped `fil_q10_dsl` through a comment that swallowed a code line; caught by our second independent review and restored, dataset rebuilt) | same |
| Split look-ahead (first audit) | five columns from a split-adjusted price file | Removed from the dataset itself: `px_close_real`, `fin_shares_now_m`, `fin_mktcap_m` (now real) replace them | same |
| A2 high: portfolio windows leaked past their dates | daily curve took a trade's whole path into its signal window | Replaced by one continuous cash ledger (script 49); windows are clipped by calendar; a position open across the boundary puts its days in each window; idle days included; reconciliation to the cent is asserted. The old per-window cohort curves are still drawn (`std_*.png`, `standard_portfolio.csv`) but relabeled "signal cohort path, descriptive"; the charts carry no Sharpe, and the Sharpe column still written to `standard_portfolio.csv` is not a calendar-account figure | `scripts/49_ledger.py` |
| A3 medium: mixed price clocks in costs | gross from daily bars, costs from quotes | Per trade gross and net now both from the quotes (mid to mid, and sell at bid / cover at ask / XBI at ask and bid). The bar version is printed next to it for comparison. Script 45 now stops on a date mismatch instead of warning | `scripts/45_offer_trades_v2.py` |
| A4 medium: fixed daily weights implied free rebalancing | | Ledger holds fixed share counts from entry, converts shares across splits, charges borrow daily on short market value, no rebalancing, no interest on cash. Nine fixtures with known answers run before every real run: the audit's own 2-share example, exact cash P&L with wide spreads, a 1-for-10 reverse split inside the hold, borrow accrual over 5 sessions and on market value after a doubling, a trade across a window boundary checked against the known price path and through `window_stats`, a short losing 250% of its stake, an entry rejected under $1, and a third trade rejected for lack of a slot. Not covered: the production split lookup on a real trade (no v3 trade spans a split), missing marks | `scripts/49_ledger.py --selftest` |
| A5 medium: intervals assumed independent trades | | Per trade tables now show two intervals: trades resampled one by one, and whole signal weeks resampled. Ledger shows block bootstraps at 5, 10, 20 and 40 days. Wording changed (section 4) | `scripts/42_standard_results.py`, 49 |
| A6 medium: shelf side study used the leaky market cap | | Rerun on dataset v2 (real market cap). Pooled AUC with the shelf block 0.6834 vs 0.6861 without; difference -0.0027, 90% interval -0.0055 to +0.0003. No gain | `scripts/24_shelf_features.py`, `25_lift_check.py` |
| A7: FINRA short interest coverage unverified | | Evidence script: 68 settlement dates 2023-11-15 to 2026-09-15, all 139 tickers present, 16 tickers on fewer than 80% of dates (new listings), exchange-listed names present, no zero rows. Values are as published at pull time (2026-10-04); FINRA corrections replace earlier values and cannot be undone | `scripts/52_finra_evidence.py` |
| A8 medium: unsafe columns still in the dataset, stale docs, no source registration | | Dataset v2 no longer holds them; the dataset README lists the removed columns. Old `docs/README.md` marked superseded. Source registration bundle prepared for `configs/sources/biologics-fds-daily` (section 11) | `data/fds/README_FDS.md`, `source_registration/` |
| A9 medium: the MATCH checker could pass unequal files | | Rewritten: same row sets required, every numeric column compared under tolerance, NaN pattern must match, ledger curve compared day by day, input and output hashes written to `reports/run_manifest.json`, exit 1 on DIFFERENT, exit 2 when a required reference file is missing or a compared file has duplicate keys; the launcher uses `set -e` so a checker failure fails the job. The two false-pass fixtures are kept as regression tests (`--fixtures`). Not covered by the gate: numbers that scripts 47 and 48 only print (section 5 audit numbers, matched controls), the dataset build and the quote pull | `scripts/46_compare_run.py`, `hpg_bundle/run_noleak.sbatch` |
| Matched controls (repair item 7) | | For each traded signal, up to 3 non-flagged names on the same day in the same market cap, runway and dollar-volume bucket; paired difference reported. Controls are priced from daily bars with no costs, so the comparison is before costs only. See section 5 | `scripts/48_offer_v3.py` |
| Borrow availability | | Still an assumption (30%/yr). No free source has 2025 history; iborrowdesk keeps one year; SEC filings hold no borrow data. Listed as the main open item | section 10 |

**Not done, said plainly:** historical borrow rates and availability (no public source), a frozen never-touched holdout period (the hold length, the slice and the window split were all chosen with results visible; section 4), and the ten-trade team engine cross-check was not rerun on the new signal.

## 1. Bottom line

1. **Dataset (version 2):** one row per company per market day, 2024-01-02 to 2026-10-02, 89,151 rows, 156 numeric features plus keys, labels in a separate file. Built point in time as far as the sources allow; the known limits are in section 7. It is not called "leak-free" in this document or in the dataset README.
2. **The offering model has predictive power for the filing itself.** AUC 0.68 out of sample, quarterly walk forward. Of the company-days it flags, 12.4% (54 of 437) are followed by an offering 8-K within 5 days, against 2.0% for all eligible company-days. For the 83 traded signals that have a matched control: 14.5% for the picks vs 3.2% for their controls. Among all trades taken the rate is 12% in sample and 18% out of sample (different denominators).
3. **Before costs the flagged stocks fell more than matched peers, in both windows.** Per trade Sharpe 1.18 in sample and 1.23 out of sample (quote mid to mid, 5 day hold, XBI hedge). Paired against same-day controls of the same size, runway and liquidity (83 of 193 signals have a match): pick minus control +6.6% per trade in sample (34 pairs, 95% interval 0.00 to 4.36 in Sharpe terms) and +4.5% out of sample (45 pairs), before costs, bar prices. Random eligible names made +2.2% and +0.6%. This is a comparison, not a causal claim, and it is before costs.
4. **After real bid/ask fills and a 30% yearly borrow fee there is nothing left.** Per trade Sharpe 0.38 and -0.07. In the cash ledger (fixed shares, 20% of NAV per trade, assumed borrow, no fill-size evidence): return +3.6% and +3.3% over the two windows, Sharpe 0.33 and 0.30, every interval includes zero, drawdowns of -26% and -35%. **No tradable edge is claimed.**
5. **Two other strategies were tested and rejected**: the trial registry strategy (Sharpe -0.13 and -0.43) and buying after an offering 8-K through the team engine (1.86 on 12 events, 0.11 on 21).
6. **Where it ran.** The dataset build ran in a cloud container (pandas 2.3.3, the laptop could not run it in time), the model, quotes and tables on a laptop, and the whole chain again as a frozen job on HiPerGator from this branch (job 44688161, section 6, VERDICT: MATCH), which compares its outputs file by file with the committed laptop outputs.

## 2. The standard used for every result

The lead asked for in-sample and out-of-sample windows of about equal size. The offering model needs 2024 to train, so it has trades from January 2025 to August 2026 (20 months), cut in half:

| Window | Dates | Months |
|---|---|---|
| In sample | 2025-01-01 to 2025-10-31 | 10 |
| Out of sample | 2025-11-01 to 2026-08-31 | 10 |

- **Per trade tables (section 3):** a trade belongs to the window of its signal date. Sharpe = mean / standard deviation of the per trade result, times sqrt(252 / 5). Two 95% intervals: trades resampled one by one (assumes independent trades, optimistic) and whole signal weeks resampled (allows for overlap and shared market shocks). Win rate = share of trades above zero. These are event statistics, not account returns.
- **Cash ledger (section 3):** one continuous account, every market day from the first trade to the last, idle days included. A window's result is the account's daily P&L on the days inside the window, so a position open across the boundary contributes its days to each side and nothing is counted twice. Intervals by stationary block bootstrap at 5, 10, 20 and 40 day blocks (5,000 draws; the checker allows 0.25 of slack on these columns because they are random-sample estimates). This is the account-level number (assumed borrow fee, no fill-size evidence).
- The window split was chosen after the first results were seen (the earlier document used 2024-2025 vs Jan-Aug 2026). Every script takes the dates as arguments.

## 3. Standard results

### Per trade

| Strategy | Engine | Costs | Window | Trades | Avg per trade | Median | Win rate | Sharpe | 95% (trades independent) | 95% (signal weeks resampled) |
|---|---|---|---|---|---|---|---|---|---|---|
| Offering short | ours | none (quote mid to mid) | in sample | 88 | +3.15% | +1.16% | 58% | 1.18 | -0.26 to 2.56 | -0.60 to 2.84 |
| Offering short | ours | none (quote mid to mid) | out of sample | 99 | +2.19% | +1.40% | 56% | 1.23 | -0.19 to 2.72 | -0.38 to 2.91 |
| Offering short | ours | none (daily bars, for comparison) | in sample | 88 | +3.23% | +1.45% | 55% | 1.23 | -0.21 to 2.54 | -0.45 to 2.82 |
| Offering short | ours | none (daily bars, for comparison) | out of sample | 99 | +2.43% | +1.59% | 58% | 1.37 | -0.04 to 2.88 | -0.23 to 3.07 |
| Offering short | ours | real bid/ask fills + 30%/yr borrow | in sample | 88 | +1.03% | -0.98% | 44% | 0.38 | -1.20 to 1.78 | -1.44 to 2.07 |
| Offering short | ours | real bid/ask fills + 30%/yr borrow | out of sample | 99 | -0.12% | -0.17% | 49% | -0.07 | -1.48 to 1.38 | -1.65 to 1.52 |
| Offering short, entry spread under 2% | ours | real bid/ask fills + 30%/yr borrow | in sample | 58 | +2.14% | -0.54% | 48% | 0.66 | -1.28 to 2.38 | -1.51 to 2.62 |
| Offering short, entry spread under 2% | ours | real bid/ask fills + 30%/yr borrow | out of sample | 63 | +0.99% | +1.59% | 56% | 0.56 | -1.15 to 2.52 | -1.19 to 2.68 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | in sample | 83 | -2.74% | -2.80% | 47% | -0.13 | -0.59 to 0.31 | -0.59 to 0.33 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | out of sample | 81 | -7.39% | -7.22% | 40% | -0.43 | -0.92 to 0.00 | -0.87 to 0.00 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | in sample | 12 | +13.42% | +5.06% | 58% | 1.86 | -0.72 to 3.95 | -0.95 to 4.43 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | out of sample | 21 | +0.49% | -5.55% | 29% | 0.11 | -4.06 to 1.85 | -3.69 to 1.58 |
| Offering short, first-version signal priced by the team engine | team engine | none | in sample | 7 | too few | | | | | |
| Offering short, first-version signal priced by the team engine | team engine | none | out of sample | 13 | +0.67% | -0.94% | 46% | 0.38 | -4.22 to 4.17 | -4.00 to 4.20 |

The per trade tables include the 6 trades whose entry bid was under $1 (the ledger rejects them; on the 187 taken the after-cost per trade Sharpe is 0.46 and -0.03). Per trade results for the offering short are quote based: gross = mid quote to mid quote, net = sell at the bid, cover at the ask, XBI bought at the ask and sold at the bid, then minus the borrow fee (30%/yr for 5 days = 0.60%). The team engine rows and the trial registry rows use daily bars and have no quote data.

### Cash ledger (offering short, after costs, 20% of NAV per trade, at most 5 positions)

| Window | Days in window | First and last mark | Return | Annualized | Sharpe | 95% (block 5d) | 95% (block 20d) | 95% (block 40d) | Max drawdown | Idle days |
|---|---|---|---|---|---|---|---|---|---|---|
| In sample, 2025-01-01 to 2025-10-31 | 208 | 2025-01-03 to 2025-10-31 | +3.6% | +4.4% | 0.33 | -1.52 to 2.31 | -1.12 to 1.82 | -0.99 to 1.64 | -26.1% | 22 |
| Out of sample, 2025-11-01 to 2026-08-31 | 207 | 2025-11-03 to 2026-08-31 | +3.3% | +4.0% | 0.30 | -1.74 to 2.46 | -1.52 to 2.30 | -1.29 to 2.16 | -35.0% | 12 |

Whole account 2025-01-03 to 2026-10-01: 187 trades taken (6 rejected because the entry bid was under $1), NAV +21.0%, Sharpe 0.47, max drawdown -35.6%, borrow fees paid 22.5% of initial NAV. Sum of trade P&L equals the NAV change to the cent (asserted). **Read the whole-account number with care:** by signal cohort the P&L is +$152k from in-sample signals, -$68k from out-of-sample signals and +$127k from the 6 September 2026 signals that sit in neither window; and the out-of-sample window's +3.3% comes from its first two sessions (+9.0%, positions signalled in late October), after which it is -5.3% to the end of August.

### Charts (in `reports/`)

- `ledger_offering_short.png`: the cash ledger, one line, both windows shaded
- `std_offering_short.png`: per trade cohort curves by window (descriptive only; a trade's whole path is drawn in its signal window)
- `std_trial_registry.png`, `std_engine_buy_after_offering.png`, `std_engine_offering_short.png`: the rejected strategies
- `equity_*.png`, `summary_table.csv`, `team_backtest_*.csv`: first version outputs, kept for the record only

## 4. Does in sample match out of sample?

| Strategy | In sample | Out of sample | Reading |
|---|---|---|---|
| Offering short, before costs (per trade) | 1.18 | 1.23 | Agree. Both positive, intervals overlap, both intervals include zero |
| Offering short, after costs (per trade) | 0.38 | -0.07 | Agree on "about zero" |
| Offering short, cash ledger after costs | 0.33 | 0.30 | Agree on "about zero". This is the account-level figure; it rests on an assumed borrow fee and on quoted prices without size |
| Trial registry stage | -0.13 | -0.43 | No edge in either. Rejected |
| Buy after an offering 8-K | 1.86 | 0.11 | 12 and 21 events. Rejected |

On wording, following the audit: different point estimates with overlapping intervals do not show different distributions, and an interval that includes zero does not prove a zero effect. The justified statement is: the before-cost effect has the same sign and similar size in the two windows and against matched controls, with intervals that include zero; the after-cost result is indistinguishable from zero in both. This is a retrospective walk-forward evaluation with a reused evaluation window, not a clean holdout: the 5 day hold, the top 2% slice, the $1 and $1M floors and the window split were all settled with some results visible. The complete recipe (section 5) is frozen now for any future period.

## 5. Audit: why each number is what it is

### Offering short

- **Recipe (frozen).** Gradient boosted classifier (`HistGradientBoostingClassifier`, depth 3, 200 rounds, learning rate 0.05, min leaf 200, L2 5), retrained at each quarter start on all rows dated at least 12 days before the quarter, target = offering 8-K within 5 market days. Eligible company-day: real close at least $1 and 20-day average dollar volume at least $1M on the signal day. Trade the top 2% of eligible company-days by predicted probability each day, one open position per company. Short at the first quote after 09:30:30 on the next session (at the bid), buy XBI for the same dollars (at the ask); close both at the last quote before 15:59:50 five sessions after the signal (cover at the ask, sell XBI at the bid). Borrow 30%/yr on the short market value. Ledger: 20% of NAV per trade, at most 5 positions, no rebalancing, no interest on cash.
- **Model quality.** AUC by quarter 0.63 to 0.74, overall 0.68. Flagged company-days 437, hit rate 12.4% (54/437; 10.8% in 2025, 14.4% in 2026); among trades taken 12% in sample and 18% out of sample (different denominators).
- **Matched controls.** 167 control company-days for 83 of the 193 traded signals (52 companies): same day, same market cap, runway and dollar-volume bucket, not flagged, up to 3 per signal; signals with no match in their bucket have no control. Controls: -2.6% per trade in sample and -2.9% out of sample before costs (Sharpe -0.87 and -1.55); the matched picks +6.0% and +1.7%; paired difference pick minus same-day control average +6.6% (n 34) and +4.5% (n 45). Offering rate within 5 days: controls 3.2%, matched picks 14.5%. Random eligible names: +2.2% and +0.6%. Controls are priced from daily bars with no costs, so this is a before-cost comparison only, and not a causal claim.
- **Costs are measured for the bid/ask part.** All 193 trades have all four quotes. Mean cost (half spreads, approximation) 1.53% in sample and 1.70% out of sample; the exact quote-clock gross minus net is close to that. Plus borrow 0.60% (5 sessions). Quote clock vs the old bar-plus-half-spread method: median difference 0.9 points per trade, 88 trades differ by more than 1 point. Quote timestamps and sizes were not saved by script 22 (known gap); a quoted price does not prove the size could be filled.
- **Concentration.** After costs, in sample: 5 best trades sum to +262 points against +90 for all 88; without them the per trade Sharpe is -1.01. Out of sample: -12 points in total, 5 best +127, without them -0.89. In sample the trades WITH an offering made +10.9% and the others -0.4%; out of sample +4.2% and -1.1%. After costs, trades with no offering lose on average (though 33 of 77 in sample and 39 of 81 out of sample were individually profitable); the trades where the offering came carry all of the profit.
- **Cost sensitivity (per trade Sharpe, in / out).** No borrow 0.60 / 0.26. 30% 0.38 / -0.07. 100% -0.13 / -0.83. 200% -0.87 / -1.92. Double spreads at 30% -0.19 / -1.00.
- **Tail risk.** Worst trades after costs: CVM 2025-07-22 -43%, SLXN 2025-03-03 -38%, PALI 2025-10-01 -34%, DBVT 2025-12-02 -34%. Ledger drawdown out of sample -35%.
- **By half year, after costs, per trade average:** 2025 H1 +0.5% (51 trades), 2025 H2 -0.4% (56), 2026 H1 +1.0% (60), Jul to Sep 2026 +2.6% (26, includes the 6 September trades outside both windows).
- **Choices made with results visible:** the 5 day hold (holds of 1, 3, 5, 10 before costs, bar prices, in / out: 1.74/0.99, 0.77/1.16, 1.23/1.37, 0.94/1.67), the window split, and the first-version floor and gap changes. The top 2% slice and the $1 and $1M floors were in the first script. The ledger adds one rule not in the first script: a trade is skipped when its entry bid is under $1 (6 trades).
- **How the three rounds of fixes moved the numbers (per trade, in / out).** Before costs: first version 2.25 / 1.83 (split leak, after-the-fact floor, 2024-25 vs 2026 windows); split fix 1.26 / 2.51 (10-month windows); dataset v2 1.18 / 1.23 (quote clock). After costs: 1.43 / 0.28, then 0.46 / 1.15, now 0.38 / -0.07. The windows changed between the first and second rounds, so the rounds are not directly comparable; the direction is that each round removed information that should not have been there.

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
| 44688161 | c0709a-s3 | **Version 3 frozen run** (commit b3a90f3b): scripts 48, 45, 42, 47, 49 (self test then real run), strict checker 46 with fixtures; input and output hashes in the log and in `reports/run_manifest.json` | `v3_44688161.log` |

The version 3 job copies the committed laptop outputs as its reference before running, prints their hashes, reruns everything from the committed inputs (model fit, quote join, tables, audit, ledger self test and ledger), and fails unless every row and value of the compared files agrees within 1e-6 (bootstrap interval columns within 0.25). Job 44688161 ran 08:39 to 08:40 EDT on 2026-10-04 and reported MATCH; its log holds the input and output SHA-256 hashes. The quotes (`stock_trades_real_v3.csv`, Massive API) and split history were downloaded on a laptop and are committed inputs; the team engine outputs are reused from jobs 44674111 and 44675692.

## 7. The dataset (version 2)

Join key: `cik` and `date` (integer YYYYMMDD). Files in `biological_products/data/fds/`.

| File | What it holds |
|---|---|
| `fds_features.csv` | 89,151 rows, 156 features: prices (real close, returns, volume), market, financials (filing date clock), filings, 8-K categories, insiders, news (16:00 New York clock), trials (monthly registry snapshots), PDUFA and FDA |
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
| Baby shelf limit features | No gain in out-of-sample AUC (rerun on v2: -0.0027, interval -0.0055 to +0.0003) |
| FINRA short volume and short interest | No gain in AUC (-0.0011, interval includes zero) |
| Quiet expected-date delays on the registry | No stock move at 5, 20 or 60 days |
| Australian trial registry | 5 events for our small companies in three years. Too few |

## 10. Limits and open items

- **Borrow.** 30%/yr is an assumption. Many of these names cannot be borrowed at all, or cost far more. No public source has 2025 history (iborrowdesk: one year, blocks scripts; SEC: none; FINRA: positions only). Paid options: Ortex, QuantRocket; academic: WRDS Markit Securities Finance if UF subscribes. Until then no trade here is "executable", only "priced".
- **Fill size.** Quotes were saved without timestamps or sizes. A quote proves a price, not that 20% of a portfolio could trade at it.
- **Holdout.** Reused evaluation window; see section 4. The recipe is frozen now; the next clean test is any period after September 2026.
- **Survivorship**, monthly trial snapshots, the Oct 2026 sponsor map for trials, sentiment model provenance: section 7.
- **Team engine cross-check** was not rerun on the version 3 signal.
- The standard windows cut 2024 (no model trades) and September 2026 (6 trades) out of both tables.

## 11. Housekeeping and integration

- Branch `biological-products-audit`, built on `main` at fa30fcb (PR #4). Shared code (`src/`, `run_all.py`) is untouched.
- Not in the repo because of size: `data/raw/aact/` (70 GB), `data/raw/aact_extract/`, `data/raw/aact_snapshots.csv`, `data/raw/companyfacts/`, `data/raw/research_cache/`. Scripts 00 and 34 rebuild them. No file holds an API key. The Massive key used during the work was exposed in a chat and should be rotated.
- **Source registration.** A bundle for `configs/sources/biologics-fds-daily/` (source.json, manifest.jsonl, README.md), a minimal adapter and tests, prepared per `docs/team-data/source-contract.md`, passes `scripts/validate_team_sources.py` in a test copy, stage `discovery`. It is in `biological_products/source_registration/` and NOT yet placed at the repo root, because the contract requires its own `codex/source-biologics-fds-daily-abhay` branch and a source-only PR. `source_registration/TODO.md` lists the fields a human must fill (URLs, hashes).
- `docs/README.md` and `docs/DATA_DICTIONARY.md` describe the first (per filing) pipeline and are superseded by `data/fds/README_FDS.md`.
- Old launchers `run_backtest.sbatch`, `run_lead_*.sbatch` are first-version; `run_noleak.sbatch` is the current one.
