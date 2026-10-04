# Biologics (SIC 2836) hand-off

Owner: Abhay. Written 2026-10-04. Universe: 139 tickers, Biological Products (no diagnostic substances).
Everything here uses public data. All numbers can be rerun with the commands in section 8.

## 0. READ FIRST: what our own check found, and what was fixed (2026-10-04)

A second, independent check of the first version of this document confirmed the arithmetic but found the problems below. The first version is in the git history (commit f3fc5cf1). **Every offering-short and trial-registry number in this document is now the corrected one.**

1. **Future information in five dataset columns (fixed for the strategy, still present in `fds_features.csv`).** `px_close_raw`, `fin_shares_adj_m`, `fin_mktcap_m`, `fin_log_mktcap` and `fin_liq_to_mcap` are built from a price file that is adjusted for splits that happened later. For a company that later did a reverse split, the stored past price is far higher than what traders saw that day. Example: QNCX on 2026-02-12 is 45.1 in the data, the real quote was 0.27. 9,224 rows (10.3%) in 32 tickers are affected, and the stored market cap is off by more than 2 times in 6.4% of rows. The first model used these columns and a `px_close_raw >= 1` filter, so it could partly see which companies would later reverse split.
   - Fix: script 43 pulls the split history (`data/raw/splits.csv`, 91 splits). Script 44 rebuilds the real price and real market cap (`data/fds/fds_realprice.csv`, same keys as the dataset) and retrains the model without the five columns.
   - Check of the fix: the rebuilt real price matches the real Massive quotes of all 186 first-version trades (all within 15% at the open, all within 5% at the close).
   - **Anyone using `fds_features.csv` should drop the five columns and join `fds_realprice.csv` instead.**
2. **The $1 price floor is now applied before the trade**, on the real close of the signal day. The first version applied it afterwards to the entry quote. No trade is removed after the fact any more.
3. **Hold length.** The 5 day hold was chosen in the first version with all results visible. With the corrected model every hold tested is positive before costs in both windows (Sharpe in sample / out of sample: 1 day 0.66 / 2.69, 3 days 1.48 / 1.85, 5 days 1.22 / 3.11, 10 days 0.98 / 2.45). 5 days is kept as the standard.
4. **2026 is still not a perfectly clean out-of-sample test.** The rule (top 2% per day, 5 day hold, $1 and $1M volume floors) was set while 2026 results of the first version were visible. Nothing was tuned on the corrected results.
5. **Training gap** raised from 7 to 12 days, so no training label reaches the test quarter.
6. **How much the fix changed.** Before costs the first version showed Sharpe 2.25 in sample and 1.83 out of sample. Corrected: 1.20 and 3.11. Only 71 of the 198 trades are the same as before. The strategy trades 1 to 2 names a day, so a small change in the model swaps most of the names. This is a sign of fragility.
7. **Trial registry (still rejected).** Three fixes in script 42: the "no 8-K" filter now looks back only (event day and 2 days before), market cap and price use the real values, and the per trade result is plain buy and hold (the old formula was wrong when a short lost more than 100% in a day). Windows are now assigned by the usable date. Result: Sharpe 0.11 in sample, -0.30 out of sample.
8. **Where things ran.** The HiPerGator jobs in section 6 ran the first version and the team engine. The corrected offering-short numbers (scripts 44, 45, 42) were run on a laptop after the fix. The team engine runs do not use our price file and are not affected by the leak. The "our signal priced by the team engine" run used the first version's signal days and was not rerun.

## 1. Bottom line

1. **Dataset:** one row per company per market day, 2024-01-02 to 2026-10-02, numbers only. Five price and market cap columns carry future information and must be replaced by `fds_realprice.csv` (section 0, item 1).
2. **Offering short, before costs:** our model flags stocks likely to announce a stock offering. Shorting them (hedged with XBI, 5 days) has a Sharpe of 1.20 in sample (-0.11 to 2.43) and 3.11 out of sample (1.62 to 4.71). The in-sample interval includes zero.
3. **After real trading costs and a 30% borrow fee:** Sharpe 0.38 in sample (-1.02 to 1.61) and 1.59 out of sample (0.07 to 3.21). As a daily portfolio: 0.66 and 1.43, both intervals include zero. **In sample does not match out of sample, and in sample is not different from zero, so we do not claim a tradable edge.** The honest label is "promising in 2026, not confirmed in 2025".
4. **Two other strategies were tested and rejected** by the same rule (in sample must match out of sample): the trial registry strategy and buying after an offering filing.
5. **Where it ran:** the first version and the team engine (`run_all.py` code at PR #4, unchanged) ran on HiPerGator (section 6). The corrected numbers were rerun locally after our check found the leak (section 0).

## 2. The standard used for every result

So that "in sample" and "out of sample" mean the same thing everywhere, every strategy uses the team's own windows from `src/config.py`:

| Window | Dates |
|---|---|
| In sample | 2024-01-01 to 2025-12-31 |
| Out of sample | 2026-01-01 to 2026-08-31 |

- A trade belongs to the window of its **signal date** (the day the information became usable). Its profit never counts in the other window.
- **Sharpe (standard):** mean / standard deviation of the per trade result, times sqrt(252 / holding days).
- **95% interval:** bootstrap over trades, 5,000 draws.
- **Win rate:** share of trades with a positive result.
- **Portfolio version** (our own backtests only): daily profit and loss, fixed share of capital per trade, 95% interval by block bootstrap (20 day blocks).

## 3. Standard results

### Per trade (same formula for every strategy)

| Strategy | Engine | Costs | Window | Trades | Avg per trade | Median | Win rate | Sharpe | 95% interval |
|---|---|---|---|---|---|---|---|---|---|
| Offering short | ours | none | in sample | 109 | +3.06% | +0.65% | 52% | 1.20 | -0.11 to 2.43 |
| Offering short | ours | none | out of sample | 78 | +4.64% | +3.47% | 65% | 3.11 | 1.62 to 4.71 |
| Offering short | ours | real bid/ask + 30%/yr borrow | in sample | 109 | +0.98% | -1.23% | 47% | 0.38 | -1.02 to 1.61 |
| Offering short | ours | real bid/ask + 30%/yr borrow | out of sample | 78 | +2.39% | +1.33% | 55% | 1.59 | 0.07 to 3.21 |
| Offering short, entry spread under 2% | ours | real bid/ask + 30%/yr borrow | in sample | 73 | +3.27% | +2.81% | 55% | 1.14 | -0.48 to 2.64 |
| Offering short, entry spread under 2% | ours | real bid/ask + 30%/yr borrow | out of sample | 52 | +3.70% | +2.20% | 58% | 2.73 | 0.85 to 4.72 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | in sample | 184 | +2.63% | +4.11% | 55% | 0.11 | -0.20 to 0.40 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | out of sample | 68 | -5.42% | -4.94% | 44% | -0.30 | -0.78 to 0.18 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | in sample | 35 | +5.94% | +0.18% | 51% | 1.17 | -0.48 to 2.31 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | out of sample | 15 | -2.69% | -5.89% | 20% | -0.58 | -6.90 to 1.45 |
| Offering short, first-version signal priced by the team engine | team engine | none | in sample | 10 | +6.39% | -1.95% | 40% | 2.04 | -5.62 to 4.81 |
| Offering short, first-version signal priced by the team engine | team engine | none | out of sample | 10 | +0.90% | -0.01% | 50% | 0.46 | -4.47 to 4.98 |

The offering model needs 2024 to train, so its in-sample trades are all in 2025.

### Portfolio version (our own backtests, after costs)

| Strategy | Window | Trades | Total return | Sharpe | 95% interval | Max drawdown |
|---|---|---|---|---|---|---|
| Offering short | in sample | 109 | +20.1% | 0.66 | -1.16 to 2.54 | -23.8% |
| Offering short | out of sample | 78 | +33.2% | 1.43 | -0.68 to 4.00 | -21.5% |
| Offering short, entry spread under 2% | in sample | 73 | +67.7% | 1.68 | -0.54 to 3.80 | -20.0% |
| Offering short, entry spread under 2% | out of sample | 52 | +41.3% | 2.30 | 0.19 to 4.46 | -10.2% |
| Trial registry stage | in sample | 184 | +12.3% | 0.36 | -1.15 to 2.16 | -26.5% |
| Trial registry stage | out of sample | 68 | -9.5% | -0.40 | -2.38 to 0.86 | -17.3% |

Offering short uses 20% of capital per trade (about 2 trades open at a time). Trial registry uses 5% per trade.

### Equity curves (in `reports/`)

- `std_offering_short.png`: offering short, both windows, before and after costs
- `std_trial_registry.png`: trial registry stage, both windows
- `std_engine_buy_after_offering.png`: team engine, buy after an offering 8-K
- `std_engine_offering_short.png`: team engine priced on the first version's signal days (only 10 trades per window)
- `equity_*.png`, `summary_table.csv` and `team_backtest_*.csv` are from the first version (before the leak fix) and are kept only for the record

## 4. Does in sample match out of sample?

| Strategy | In sample | Out of sample | Verdict |
|---|---|---|---|
| Offering short, before costs | 1.20 | 3.11 | Positive in both, but far apart, and the in-sample interval includes zero. Does not match. |
| Offering short, after real costs | 0.38 | 1.59 | Does not match. In sample is not different from zero. No edge claimed. |
| Offering short, daily portfolio after costs | 0.66 | 1.43 | Same reading. Both intervals include zero. |
| Trial registry stage | 0.11 | -0.30 | No edge in either window. Rejected. |
| Buy after an offering 8-K | 1.17 | -0.58 | Does not match. Rejected. |
| Offering short, first-version signal priced by the team engine | 2.04 | 0.46 | Only 10 trades per window. Too few to judge. |

## 5. Audit: why each number is what it is

### Offering short (corrected version)

- **What it is.** A gradient boosted model, retrained each quarter on past data only (12 day gap), predicts "an offering 8-K within 5 market days". Each day the top 2% of company-days are shorted at the next open, XBI is bought for the same dollars, both are closed 5 market days after the signal. One position per company at a time. Only stocks with a real close of at least $1 and at least $1M average daily volume on the signal day.
- **Model quality (out of sample, 2025Q1 to 2026Q3):** AUC 0.69. In the traded slice 11.7% of flagged days were followed by an offering versus a 2.0% base rate (11.2% in 2025, 12.3% in 2026). The leak did not create this: the AUC is the same with and without it.
- **Timing is honest.** Every trade enters at least 1 day after the signal.
- **Costs are measured, not assumed, for the bid/ask part.** 197 of the 198 trades are priced from Massive quotes (1 had no quote and is dropped): sell the short at the bid, buy back at the ask, and the same for the XBI hedge. Mean cost 1.54% per trade, median 1.05% (2025: 1.48%, 2026: 1.61%). The 30% yearly borrow fee is an assumption and adds 0.60% per trade.
- **Unusual: in 2025 the model was no better than random.** Shorting random liquid company-days from the same universe with the same hedge gave Sharpe 1.22 before costs in sample (average +1.87% per trade), the same as the model (1.22, +3.08%). In 2026 the random version gave 0.43 and the model 3.11. Small biotechs fell against XBI in 2025 whatever you picked.
- **Unusual: 3.11 out of sample is high, and should not be read as a real Sharpe of 3.** It is a per trade number: +4.6% average with a 10.6% standard deviation, scaled by sqrt(252/5). It is before costs and from 78 trades in 8 months. The daily portfolio after costs is 1.43 with an interval that includes zero.
- **Unusual: the profit is concentrated.** After costs, in sample: the 5 best trades made +250% in summed returns against +107% for all 109, so without them the Sharpe is -0.67. Out of sample: without the best 5 it is 0.66, without the best 10 it is -0.34. Before costs the out-of-sample result is broader (46 companies, Sharpe 1.66 without the best 10).
- **Unusual: the in-sample curve is flat, then jumps.** Two trades in August 2025 made about +70% each (CLDI signal 2025-08-13, OTLK signal 2025-08-26). The first half of 2025 lost (49 trades, -0.8% each after costs). The second half made +2.4% each, the first half of 2026 +2.3%, July and August 2026 +2.7%.
- **Unusual: most of the profit did not come from offerings.** An offering was announced within 5 days in 15% of in-sample trades and 12% of out-of-sample trades. Trades with no offering made 92% of the after-cost profit in sample and 72% out of sample. The model mostly finds weak, cash-short companies that keep falling. The "offering" story is only part of the reason.
- **Cost sensitivity (per trade Sharpe, in sample / out of sample).** No borrow fee 0.61 / 1.99. 30% borrow 0.38 / 1.59. 100% borrow -0.16 / 0.67. 200% borrow -0.93 / -0.66. Double bid/ask cost at 30% borrow -0.19 / 0.48.
- **Tail risk.** Worst trades after costs: -35% (SLXN, 2025-03-03), -30% (DBVT, 2025-12-02), -29% (PALI, 2025-10-01), -28% (SCLX, 2026-07-06).
- **Choices made with results visible:** the 5 day hold (section 0, item 3). The top 2% slice and the $1 and $1M floors were written into the first script before any trade result. Ten trades after August 2026 are in neither window.

### Trial registry stage (rejected)

- **Idea.** Sponsors update ClinicalTrials.gov records quietly. Short a company under $2B when a record shows it is still building a trial (starts recruiting, adds 20%+ sites, raises its enrollment target), buy when enrollment is over. Hold 60 days, hedge with XBI, only when no 8-K was filed within 2 days.
- **Data.** 35 monthly snapshots of the registry from AACT (Dec 2023 to Oct 2026). A change counts only when a new record version was posted, and it is dated by that posting date.
- **What happened.** The rules were designed on events up to June 2025, where the portfolio Sharpe after costs was 1.19. On the events after that it was -1.62 (95% interval -3.0 to -0.5). Those two numbers are from scripts 38 and 39, before the fixes in section 0, item 7. On the team windows, with the fixes, it is 0.11 and -0.30 per trade.
- **Why the design half looked good.** Five trades made most of the profit, seven companies made half the gains, and 71% of the profit came in the first half of 2024.
- **Unusual: one short lost 219% of its stake.** Scholar Rock (SRRK): shorted on 2024-07-30 after it added sites, the stock rose from about 7 to 34 on 2024-10-07 when its trial succeeded. This is the tail risk of shorting a biotech before data. (An earlier version said 447%. That came from a compounding formula that is wrong for losses above 100%.)
- **Unusual: the out-of-sample curve sinks.** Only 44% of trades won after costs. It is not one bad trade.
- **Conclusion.** The pattern was not real. The held-out test caught it before we presented it.

### Buy after an offering 8-K, team engine (rejected)

- **What ran.** `src.implementation.run_study` from the team repo at commit fa30fcb, unchanged, with tag `public_offering` and our 139 tickers as the universe.
- **Coverage.** 166 filings in sample and 58 out of sample. The engine could price 63 and 23 of them. The rest have no option chain or no option trade near the filing date.
- **Unusual: the in-sample average rests on one event.** IVVD rose 121% in 10 days after its August 2025 offering. Without it the average is +2.6%, without the top two +1.1%.
- **Unusual: the out-of-sample average is held up by one event.** Without OTLK (+75%) it is -8.3%.
- **Noticed after the run (not a claim):** selling a 5% out-of-the-money put and holding 5 days made about +1.2% per event in both windows (win rate 59% and 69%). Both intervals include zero, the engine has no trading costs, and our own test found bid/ask spreads on these options near 70% of the option price.
- **Buying options loses** in most cells, which matches our own earlier test (long straddles around 8-Ks lost about 43% after costs).
- Some cells show extreme Sharpe values (for example -11.6). They come from 8 events and mean nothing.

### Offering short priced by the team engine (cross-check only)

- **What ran.** The 155 days the first version of the model flagged (before the leak fix, not rerun) were given to the team engine as events (`price_events` and `evaluate`, unchanged). The engine enters at the close of the session after the signal. Our trade is a short, so the result is minus the engine's "stock" number. No costs.
- **Coverage.** The engine could price 34 of the 155 events (22 tickers). 91 had no option chain at all. In the standard cell (nearest expiry, 5 days) that leaves 10 trades in each window.
- **Reading.** With 10 trades per window the intervals run from about -5 to +5, so this neither confirms nor contradicts anything.
- **Why our own backtest is the better measurement for this strategy.** It prices the trades from real stock quotes with real costs. The team engine needs traded options, which most of these companies do not have.

## 6. HiPerGator runs

| Job | Node | What ran | Log |
|---|---|---|---|
| 44673323 | c0706a-s7 | Our backtests: offering short, trial registry (both halves) | `hpg_bundle/hpg_results/backtest_44673323.log` |
| 44673985 | c0706a-s3 | Team engine smoke test, 8 events | `lead_backtest_44673985.log` |
| 44674111 | c0702a-s7 | Team engine, `public_offering`, both windows | `lead_backtest_44674111.log` |
| 44675692 | c0704a-s1 | Team engine priced on our model's 155 signal days | `lead_signal_44675692.log` |

The HiPerGator numbers for our own backtests matched the local run of the first version exactly. These jobs ran before the leak fix. The corrected offering-short numbers in sections 1 to 5 come from scripts 44, 45 and 42 run locally afterwards (section 0, item 8).
All logs and engine output folders are in `hpg_bundle/hpg_results/`.

## 7. The dataset

Join key for every file: `cik` and `date` (integer YYYYMMDD). Files are in `biological_products/data/fds/`.

| File | What it holds |
|---|---|
| `fds_features.csv` | 89,150 rows, 156 feature columns: prices, market, financials, filings, 8-K categories, insiders, news, trials, FDA |
| `fds_missing.csv` | Same shape. One reason code per cell: 0 present, 1 not public yet, 2 never reported, 3 stale, 4 insufficient history, 5 not collected, 6 inapplicable, 7 derived |
| `fds_labels.csv` | Outcomes only. Never use as features |
| `fds_realprice.csv` | Real (not split adjusted) close and real market cap per row. Use these instead of `px_close_raw`, `fin_shares_adj_m`, `fin_mktcap_m`, `fin_log_mktcap`, `fin_liq_to_mcap` |
| `fds_options.csv` | Option spreads and straddle prices seen at earlier 8-K events |
| `fds_shelf.csv` | Baby shelf limit features |
| `fds_short.csv` | FINRA short volume and short interest |
| `fds_trialchg.csv` | Trial registry change block (run script 37 to build it) |
| `fds_dictionary.csv`, `README_FDS.md` | Column meanings, design choices, data fixes |

Rules used throughout: decision clock is the market close; anything with only a date is usable from the next day; restatements are used as they were filed; every script recounts random rows from raw data and stops if a row uses information dated after it. That check did not catch the split adjustment in the price file (section 0, item 1).

## 8. How to rerun

From `biological_products/scripts`:

```
python 16_build_fds.py ; python 16b_write_fds.py     # dataset
python 43_pull_splits.py                              # split history (needs MASSIVE_API_KEY)
python 44_offer_noleak.py                             # real prices, corrected offering model, signal slice, old version next to it
python 22_stock_real_costs.py --slice offer_signal_slice_v2.csv --out stock_trades_real_v2.csv   # real bid/ask (needs MASSIVE_API_KEY)
python 45_offer_trades_v2.py                          # joins the trade list with the quotes
# first version, kept for the record (has the leak): 21_stock_offer_test.py, 22_stock_real_costs.py, 40_offer_strategy_pnl.py
python 34_aact_extract.py ; python 35_aact_events.py ; python 36_aact_event_study.py   # trial registry events (needs the AACT zips in data/raw/aact)
python 39_strategy_audit.py                           # trial registry: design half
python 39_strategy_audit.py --set holdout --confirm_holdout
python 42_standard_results.py                         # the standard tables and charts in this document
```

On HiPerGator: copy `hpg_bundle/` to `~/qh_bio`, then `sbatch run_backtest.sbatch` (our backtests), `sbatch run_lead_backtest.sbatch` (team engine, needs `MASSIVE_API_KEY` exported in the shell first), `sbatch run_lead_signal.sbatch` (our signal through the team engine).

## 9. Other ideas tested and dropped

| Idea | Result |
|---|---|
| Long option straddles around 8-Ks | Lose about 43% after bid/ask costs. Spreads are about 70% of the option price |
| Baby shelf limit features | No gain in out-of-sample AUC (-0.0009, interval includes zero) |
| FINRA short volume and short interest | No gain in AUC (-0.0011, interval includes zero) |
| Quiet expected-date delays on the registry | No stock move at 5, 20 or 60 days |
| Australian trial registry | Only 5 events for our small companies in three years. Too few to test |

## 10. Limits

- The universe is today's SIC 2836 list, so there is survivorship bias.
- The out-of-sample window is 8 months. Intervals are wide and most include zero.
- Many small biotechs cannot be borrowed for shorting, or cost far more than 30% a year. This is the main unknown for the offering short.
- The team engine prices from last option trades with no trading costs, and only for companies with traded options (about 4 in 10 of ours).
- The trial registry data is monthly snapshots. A change is dated by its posting date, which is exact when one update happened in the month.
- Several looks were taken at the data before the rules were fixed. Every such choice is named in sections 0 and 5.
- The offering short trades 1 to 2 names a day. A small change in the model changes most of the trades (71 of 198 stayed the same after the leak fix), so the result is fragile.

## 11. Housekeeping

- This folder is on the branch `biological-products-audit`, built on `main` at fa30fcb (PR #4).
- Not in the repo because of size (see `biological_products/.gitignore`): `data/raw/aact/` (70 GB of AACT zips), `data/raw/aact_extract/`, `data/raw/aact_snapshots.csv`, `data/raw/companyfacts/`, `data/raw/research_cache/`. Scripts 00 and 34 rebuild them. No file holds an API key.
- The Massive API key was shared in chat earlier and should be rotated.
- `hpg_bundle/_to_delete/` and the `_stage.pkl`, `_tld*.pkl` files in `data/fds/` can be deleted.
- Still to do in the dataset itself: remove the five leaky columns from `fds_features.csv` and `fds_missing.csv` and merge in `fds_realprice.csv` (rebuild with script 16).
