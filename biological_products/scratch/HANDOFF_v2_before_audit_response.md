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
8. **Where things ran.** All backtests ran on HiPerGator (section 6). Jobs 44673323 to 44675692 ran the first version and the team engine. Job 44679395 reran the corrected version (scripts 44, 45, 42) from this branch at commit 88a52022, and script 46 confirmed it matches the laptop run exactly: the same 198 trades and the same Sharpe in every row. Only the downloads (split history and real quotes, scripts 43 and 22) were done on a laptop. The team engine runs do not use our price file and are not affected by the leak. The "our signal priced by the team engine" run used the first version's signal days and was not rerun.

## 1. Bottom line

1. **Dataset:** one row per company per market day, 2024-01-02 to 2026-10-02, numbers only. Five price and market cap columns carry future information and must be replaced by `fds_realprice.csv` (section 0, item 1).
2. **Offering short, before costs:** our model flags stocks likely to announce a stock offering. Shorting them (hedged with XBI, 5 days) has a Sharpe of 1.26 in sample (-0.17 to 2.56) and 2.51 out of sample (1.10 to 4.00). The in-sample interval includes zero.
3. **After real trading costs and a 30% borrow fee:** Sharpe 0.46 in sample (-1.11 to 1.81) and 1.15 out of sample (-0.31 to 2.66). As a daily portfolio: 0.79 and 1.10, both intervals include zero. **Positive in both windows, but neither is different from zero, so we do not claim a tradable edge.** The honest label is "promising, not proven". Shorting these stocks in practice (borrow availability) is the main unknown.
4. **Two other strategies were tested and rejected** by the same rule (in sample must match out of sample): the trial registry strategy and buying after an offering filing.
5. **Where it ran:** HiPerGator (section 6). First the first version and the team engine (`run_all.py` code at PR #4, unchanged), then the corrected version in job 44679395. Every number in sections 1 to 5 for our own backtests is from that job.

## 2. The standard used for every result

The team lead asked for in-sample and out-of-sample windows of about equal size. Our offering model needs 2024 to train, so it has trades only from January 2025 to August 2026 (20 months). Those 20 months are cut in half:

| Window | Dates | Months |
|---|---|---|
| In sample | 2025-01-01 to 2025-10-31 | 10 |
| Out of sample | 2025-11-01 to 2026-08-31 | 10 |

The earlier version of this document used the windows from `src/config.py` (2024-01-01 to 2025-12-31 and 2026-01-01 to 2026-08-31). Those gave the offering short Sharpe 0.38 and 1.59 per trade after costs (portfolio 0.66 and 1.43). The split was changed on the lead's request, after those results were seen. Every script takes the window dates as arguments, so either set can be rerun (`--is_start --is_end --os_start --os_end`).

- A trade belongs to the window of its **signal date** (the day the information became usable). Its profit never counts in the other window. Ten trades after August 2026 are in neither window.
- **Sharpe (standard):** mean / standard deviation of the per trade result, times sqrt(252 / holding days).
- **95% interval:** bootstrap over trades, 5,000 draws.
- **Win rate:** share of trades with a positive result.
- **Portfolio version** (our own backtests only): daily profit and loss, fixed share of capital per trade, 95% interval by block bootstrap (20 day blocks). This is the realistic number: it counts overlapping trades and days with nothing open, and its interval allows for trades moving together.

## 3. Standard results

### Per trade (same formula for every strategy)

| Strategy | Engine | Costs | Window | Trades | Avg per trade | Median | Win rate | Sharpe | 95% interval |
|---|---|---|---|---|---|---|---|---|---|
| Offering short | ours | none | in sample | 90 | +3.30% | +0.87% | 53% | 1.26 | -0.17 to 2.56 |
| Offering short | ours | none | out of sample | 97 | +4.10% | +3.10% | 62% | 2.51 | 1.10 to 4.00 |
| Offering short | ours | real bid/ask + 30%/yr borrow | in sample | 90 | +1.22% | -1.15% | 47% | 0.46 | -1.11 to 1.81 |
| Offering short | ours | real bid/ask + 30%/yr borrow | out of sample | 97 | +1.89% | +1.19% | 54% | 1.15 | -0.31 to 2.66 |
| Offering short, entry spread under 2% | ours | real bid/ask + 30%/yr borrow | in sample | 60 | +4.09% | +2.88% | 57% | 1.36 | -0.43 to 3.05 |
| Offering short, entry spread under 2% | ours | real bid/ask + 30%/yr borrow | out of sample | 65 | +2.86% | +1.93% | 55% | 1.82 | 0.10 to 3.76 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | in sample | 83 | -2.74% | -2.80% | 47% | -0.13 | -0.60 to 0.30 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | out of sample | 81 | -7.39% | -7.22% | 40% | -0.43 | -0.90 to 0.02 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | in sample | 12 | +13.42% | +5.06% | 58% | 1.86 | -0.67 to 3.87 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | out of sample | 21 | +0.49% | -5.55% | 29% | 0.11 | -4.05 to 1.82 |
| Offering short, first-version signal priced by the team engine | team engine | none | in sample | 7 | too few | | | | |
| Offering short, first-version signal priced by the team engine | team engine | none | out of sample | 13 | +0.67% | -0.94% | 46% | 0.38 | -4.25 to 4.12 |

The offering model needs 2024 to train, so it has no trades before January 2025. The trial registry strategy has events from January 2024 on; its 2024 events fall outside both windows (its result on the earlier windows was Sharpe 0.11 and -0.30, also rejected).

### Portfolio version (our own backtests, after costs)

| Strategy | Window | Trades | Total return | Sharpe | 95% interval | Max drawdown |
|---|---|---|---|---|---|---|
| Offering short | in sample | 90 | +22.4% | 0.79 | -1.10 to 2.73 | -23.8% |
| Offering short | out of sample | 97 | +30.7% | 1.10 | -0.68 to 3.27 | -22.5% |
| Offering short, entry spread under 2% | in sample | 60 | +69.9% | 1.94 | -0.31 to 4.25 | -20.0% |
| Offering short, entry spread under 2% | out of sample | 65 | +39.5% | 1.78 | -0.03 to 3.92 | -12.9% |
| Trial registry stage | in sample | 83 | -3.6% | -0.13 | -1.69 to 1.54 | -18.2% |
| Trial registry stage | out of sample | 81 | -17.6% | -0.89 | -2.69 to 0.33 | -18.7% |

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
| Offering short, before costs | 1.26 | 2.51 | Positive in both. In-sample interval includes zero. Weakly consistent. |
| Offering short, after real costs | 0.46 | 1.15 | Positive in both, both intervals include zero. No edge claimed. |
| Offering short, daily portfolio after costs | 0.79 | 1.10 | Same reading. This is the number to quote. |
| Trial registry stage | -0.13 | -0.43 | No edge in either window. Rejected. |
| Buy after an offering 8-K | 1.86 | 0.11 | 12 and 21 events. Does not match. Rejected. |
| Offering short, first-version signal priced by the team engine | too few (7) | 0.38 | Too few trades to judge. |

## 5. Audit: why each number is what it is

### Offering short (corrected version)

All numbers below are from `scripts/47_offer_audit.py` on the 197 priced trades.

- **What it is.** A gradient boosted model, retrained each quarter on past data only (12 day gap), predicts "an offering 8-K within 5 market days". Each day the top 2% of company-days are shorted at the next open, XBI is bought for the same dollars, both are closed 5 market days after the signal. One position per company at a time. Only stocks with a real close of at least $1 and at least $1M average daily volume on the signal day.
- **Model quality (out of sample, 2025Q1 to 2026Q3):** AUC 0.69. In the traded slice 11.7% of flagged days were followed by an offering versus a 2.0% base rate (11.2% in 2025, 12.3% in 2026). The leak did not create this: the AUC is the same with and without it.
- **Timing is honest.** Every trade enters at least 1 day after the signal.
- **Costs are measured, not assumed, for the bid/ask part.** 197 of the 198 trades are priced from Massive quotes (1 had no quote and is dropped): sell the short at the bid, buy back at the ask, and the same for the XBI hedge. Mean cost 1.49% per trade in sample and 1.62% out of sample (medians 1.18% and 0.98%). The 30% yearly borrow fee is an assumption and adds 0.60% per trade.
- **Unusual: in 2025 the model was no better than random.** Shorting random liquid company-days from the same universe with the same hedge gave Sharpe 1.45 before costs in the in-sample window, against 1.27 for the model. Out of sample the random version gave 0.42 and the model 2.51. Small biotechs fell against XBI in 2025 whatever you picked; only the later window shows the model adding anything.
- **Unusual: the per trade out-of-sample Sharpe looks high and should not be read as a real Sharpe of 2.5.** It is +4.1% average on a 10% standard deviation, scaled by sqrt(252/5), before costs, from 97 trades in 10 months. The daily portfolio after costs is 1.10 with an interval of -0.68 to 3.27.
- **Unusual: the profit is concentrated.** After costs, in sample: the 5 best trades sum to +250% against +110% for all 90, so without them the Sharpe is -0.81. Out of sample: without the best 5 it is 0.43, without the best 10 it is -0.29. Before costs the out-of-sample result is broader (54 companies, Sharpe 1.31 without the best 10).
- **Unusual: the in-sample curve is flat, then jumps.** Two trades in August 2025 made about +70% each (CLDI signal 2025-08-13, OTLK signal 2025-08-26). By half year after costs: 2025 first half -0.8% per trade (49 trades), 2025 second half +2.4% (60), 2026 first half +2.3% (58), July and August 2026 +3.6% (30).
- **Unusual: most of the profit did not come from offerings.** An offering was announced within 5 days in 11% of in-sample trades and 15% of out-of-sample trades. In sample the trades WITH an offering lost on average (-3.1% after costs) and all the profit came from trades without one. Out of sample the offering trades made +6.0% and the others +1.1%. The model mostly finds weak, cash-short companies that keep falling. The "offering" story is only part of the reason.
- **Cost sensitivity (per trade Sharpe, in sample / out of sample).** No borrow fee 0.68 / 1.52. 30% borrow 0.46 / 1.15. 100% borrow -0.06 / 0.31. 200% borrow -0.81 / -0.91. Double bid/ask cost at 30% borrow -0.10 / 0.16.
- **Tail risk.** Worst trades after costs: -35% (SLXN, 2025-03-03), -30% (DBVT, 2025-12-02), -29% (PALI, 2025-10-01), -29% (DBVT, 2025-03-31), -28% (SCLX, 2026-07-06).
- **Choices made with results visible:** the 5 day hold (section 0, item 3) and the window split (section 2). The top 2% slice and the $1 and $1M floors were written into the first script before any trade result.

### Trial registry stage (rejected)

- **Idea.** Sponsors update ClinicalTrials.gov records quietly. Short a company under $2B when a record shows it is still building a trial (starts recruiting, adds 20%+ sites, raises its enrollment target), buy when enrollment is over. Hold 60 days, hedge with XBI, only when no 8-K was filed within 2 days.
- **Data.** 35 monthly snapshots of the registry from AACT (Dec 2023 to Oct 2026). A change counts only when a new record version was posted, and it is dated by that posting date.
- **What happened.** The rules were designed on events up to June 2025, where the portfolio Sharpe after costs was 1.19. On the events after that it was -1.62 (95% interval -3.0 to -0.5). Those two numbers are from scripts 38 and 39, before the fixes in section 0, item 7. With the fixes: Sharpe -0.13 in sample and -0.43 out of sample per trade on the current windows, 0.11 and -0.30 on the earlier team windows.
- **Why the design half looked good.** Five trades made most of the profit, seven companies made half the gains, and 71% of the profit came in the first half of 2024.
- **Unusual: one short lost 219% of its stake.** Scholar Rock (SRRK): shorted on 2024-07-30 after it added sites, the stock rose from about 7 to 34 on 2024-10-07 when its trial succeeded. This is the tail risk of shorting a biotech before data. (An earlier version said 447%. That came from a compounding formula that is wrong for losses above 100%.)
- **Unusual: the out-of-sample curve sinks.** Only 44% of trades won after costs. It is not one bad trade.
- **Conclusion.** The pattern was not real. The held-out test caught it before we presented it.

### Buy after an offering 8-K, team engine (rejected)

- **What ran.** `src.implementation.run_study` from the team repo at commit fa30fcb, unchanged, with tag `public_offering` and our 139 tickers as the universe.
- **Coverage.** On the current windows the engine priced 12 events in sample and 21 out of sample (on the earlier team windows: 166 and 58 filings, 63 and 23 priced). The rest have no option chain or no option trade near the filing date.
- **Unusual: the in-sample average rests on one event.** IVVD rose 121% in 10 days after its August 2025 offering. It is one of only 12 in-sample events; without it the average is far lower.
- **Unusual: the out-of-sample average is held up by one event.** OTLK rose 75% after its offering; without it the average is negative.
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
| 44675692 | c0704a-s1 | Team engine priced on our model's 155 signal days (first version) | `lead_signal_44675692.log` |
| 44679395 | c0710a-s3 | **Corrected run:** real prices, offering model without the leak, standard tables (scripts 44, 45, 42), then a comparison with the laptop run (script 46: MATCH) | `noleak_44679395.log` |

The first four jobs ran before the leak fix. Job 44679395 ran the corrected version straight from this branch (commit 88a52022, Python 3.10.8, scikit-learn 1.7.2, pandas 2.0.3, numpy 1.26.2) and reproduces the laptop numbers exactly: the same 198 trades, largest Sharpe difference 0.0000. The numbers in sections 1 to 5 for our own backtests are from that job.
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
python 42_standard_results.py                         # the standard tables and charts in this document (window dates are arguments)
python 47_offer_audit.py                              # the audit numbers in section 5
```

Corrected run on HiPerGator: check out this branch, `cd biological_products/hpg_bundle`, `sbatch run_noleak.sbatch` (about 2 minutes, no API key needed).

First version on HiPerGator: copy `hpg_bundle/` to `~/qh_bio`, then `sbatch run_backtest.sbatch` (our backtests), `sbatch run_lead_backtest.sbatch` (team engine, needs `MASSIVE_API_KEY` exported in the shell first), `sbatch run_lead_signal.sbatch` (our signal through the team engine).

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
