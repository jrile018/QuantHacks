# Biologics (SIC 2836) hand-off

Owner: Abhay. Written 2026-10-04. Universe: 139 tickers, Biological Products (no diagnostic substances).
Everything here uses public data. All numbers can be rerun with the commands in section 8.

## 0. READ FIRST: problems found in our own check (2026-10-04, fix in progress)

A second, independent check of this document confirmed the arithmetic but found the problems below.
**The offering-short numbers in sections 1, 3, 4 and 5 were produced before the fix. Treat them as too optimistic until this section is removed.**
The rejected strategies stay rejected, and the HiPerGator runs in section 6 are as described.

1. **Future information in five dataset columns.** `px_close_raw`, `fin_shares_adj_m`, `fin_mktcap_m`, `fin_log_mktcap` and `fin_liq_to_mcap` are built from a price file that is adjusted for splits that happened later. For a company that later did a reverse split, the stored past price is far higher than what traders saw that day. Example: QNCX on 2026-02-12 is 45.1 in the data, the real quote was 0.27. The offering model used these columns and the `px_close_raw >= 1` filter, so it could partly see which companies would later reverse split. 53 of the 186 trades are in stocks where the stored price differs from the real price by more than 1.5 times.
   Fix under way: split history is now in `data/raw/splits.csv` (script 43). Real prices and market cap are being rebuilt and the model retrained without the leak.
2. **The in-sample result depends on the $1 price floor**, which was applied to the real entry quote after the fact. It removes one short that lost 385% (VOR, 2025-06-24). On all 186 trades the in-sample Sharpe before costs is 0.30, not 2.25.
3. **The result depends on the 5 day hold.** With a 1 day hold the in-sample Sharpe is about -0.98.
4. **2026 is not a clean out-of-sample test for the offering short.** The hold length and the price floor were chosen with the 2026 results visible.
5. **Training gap.** The 7 day gap between the training data and each test quarter is slightly too short for a 5 market day label. It is being raised to 12 days.
6. **Trial registry (verdict unchanged, still rejected).** The "no 8-K within 2 days" filter also looked 2 days forward, which is future information. The per trade return used daily compounding, which is wrong when a short loses more than 100% in one day (the "SRRK lost 447%" figure comes from that formula). With a plain buy-and-hold formula the per trade Sharpe is 0.13 in sample and -0.27 out of sample. 15 of the 66 out-of-sample trades are cut short by the end of the data.
7. **Wording in section 5 that is wrong or too strong:** the traded-slice hit rate is 14.1% overall (16.4% in 2025, 10.7% in Jan to Aug 2026), not 12.7%. Trading cost was not fixed: it rose from 2.13% per trade in sample to 2.92% out of sample. The concentration shares (OTLK 37%, top 5 trades) mix two different bases and are being recomputed. "Both sides lost" and "same direction as our own backtest" are stronger than the data supports.
8. **Where things ran.** HiPerGator ran the jobs listed in section 6. The standard tables in section 3 (script 42) were built on a laptop from those outputs.

## 1. Bottom line

1. **Dataset:** one row per company per market day, 2024-01-02 to 2026-10-02, numbers only. Built to hold no future information, but five price and market cap columns do (see section 0).
2. **One signal looks positive before costs (not yet confirmed, see section 0):** our model flags stocks likely to announce a stock offering. Shorting them (hedged with XBI, 5 days) has a Sharpe of 2.25 in sample and 1.83 out of sample before costs, and both 95% intervals are above zero.
3. **After real trading costs it does not hold out of sample:** Sharpe 1.43 in sample, 0.28 out of sample. In sample does not match out of sample, so we do not claim a tradable edge.
4. **Two other strategies were tested and rejected** by the same rule (in sample must match out of sample): the trial registry strategy and buying after an offering filing.
5. **The backtests were run on HiPerGator** (job list in section 6), including the team engine (`run_all.py` code at PR #4, unchanged). The standard tables were then built locally from those outputs.

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
| Offering short | ours | none | in sample | 87 | +5.89% | +3.96% | 63% | 2.25 | 0.89 to 3.63 |
| Offering short | ours | none | out of sample | 62 | +3.45% | +2.01% | 58% | 1.83 | 0.16 to 3.56 |
| Offering short | ours | real bid/ask + 30%/yr borrow | in sample | 87 | +3.76% | +2.02% | 55% | 1.43 | 0.00 to 2.74 |
| Offering short | ours | real bid/ask + 30%/yr borrow | out of sample | 62 | +0.53% | -0.65% | 47% | 0.28 | -1.53 to 2.03 |
| Offering short, entry spread under 2% | ours | real bid/ask + 30%/yr borrow | in sample | 53 | +5.36% | +5.10% | 62% | 1.83 | 0.04 to 3.69 |
| Offering short, entry spread under 2% | ours | real bid/ask + 30%/yr borrow | out of sample | 30 | +1.17% | -0.95% | 43% | 0.71 | -1.83 to 3.46 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | in sample | 184 | -0.10% | -3.99% | 47% | 0.00 | -0.29 to 0.30 |
| Trial registry stage | ours | 2% round trip + 15%/yr borrow | out of sample | 66 | -5.48% | -5.68% | 38% | -0.37 | -0.95 to 0.13 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | in sample | 35 | +5.94% | +0.18% | 51% | 1.17 | -0.50 to 2.34 |
| Buy after an offering 8-K (stock, 10 days) | team engine | none | out of sample | 15 | -2.69% | -5.89% | 20% | -0.58 | -6.81 to 1.47 |
| Offering short, our signal priced by the team engine | team engine | none | in sample | 10 | +6.39% | -1.95% | 40% | 2.04 | -5.04 to 4.84 |
| Offering short, our signal priced by the team engine | team engine | none | out of sample | 10 | +0.90% | -0.01% | 50% | 0.46 | -4.36 to 4.99 |

The offering model needs 2024 to train, so its in-sample trades are all in 2025.

### Portfolio version (our own backtests, after costs)

| Strategy | Window | Trades | Total return | Sharpe | 95% interval | Max drawdown |
|---|---|---|---|---|---|---|
| Offering short | in sample | 87 | +81.3% | 1.67 | -0.39 to 3.72 | -31.7% |
| Offering short | out of sample | 62 | -0.8% | 0.12 | -2.06 to 1.99 | -24.3% |
| Offering short, entry spread under 2% | in sample | 53 | +65.1% | 1.58 | -0.09 to 3.56 | -21.4% |
| Offering short, entry spread under 2% | out of sample | 30 | +4.4% | 0.49 | -2.26 to 2.97 | -15.0% |
| Trial registry stage | in sample | 184 | +12.6% | 0.36 | -1.09 to 2.15 | -27.5% |
| Trial registry stage | out of sample | 66 | -11.9% | -0.88 | -3.03 to 0.68 | -16.5% |

Offering short uses 20% of capital per trade (about 2 trades open at a time). Trial registry uses 5% per trade.

### Equity curves (in `reports/`)

- `std_offering_short.png`: offering short, both windows, before and after costs
- `std_trial_registry.png`: trial registry stage, both windows
- `std_engine_buy_after_offering.png`: team engine, buy after an offering 8-K
- `std_engine_offering_short.png`: team engine priced on our model's signal days (only 10 trades per window)

## 4. Does in sample match out of sample?

| Strategy | In sample | Out of sample | Verdict |
|---|---|---|---|
| Offering short, before costs | 2.25 | 1.83 | Matches. The prediction itself holds on new data. |
| Offering short, after real costs | 1.43 | 0.28 | Does not match. Costs take most of the 2026 result. |
| Trial registry stage | 0.00 | -0.37 | No edge in either window. Rejected. |
| Buy after an offering 8-K | 1.17 | -0.58 | Does not match. Rejected. |
| Offering short, priced by the team engine | 2.04 | 0.46 | Same direction as our own backtest, but only 10 trades per window. Too few to judge. |

## 5. Audit: why each number is what it is

### Offering short

- **What it is.** A gradient boosted model, retrained each quarter on past data only (7 day gap), predicts "an offering 8-K within 5 market days". Each day the top 2% of liquid company-days are shorted at the next open, XBI is bought for the same dollars, both are closed 5 market days after the signal. One position per company at a time. Price at least $1.
- **Model quality (out of sample, 2025Q1 to 2026Q3):** AUC 0.69. In the traded slice 12.7% announced an offering versus a 2.1% base rate (about 6 times).
- **Timing is honest.** Every trade enters at least 1 day after the signal.
- **Costs are measured, not assumed, for the bid/ask part.** Each trade is priced from Massive quotes: sell the short at the bid, buy back at the ask, and the same for the XBI hedge. Average cost 1.9% per trade. The 30% yearly borrow fee is an assumption.
- **Why out of sample is weaker after costs.** The gross result fell from +5.9% to +3.5% per trade, and costs stayed near 2% to 3% per trade, so the net fell from +3.8% to +0.5%. A smaller gross edge leaves little after a fixed cost.
- **Unusual: the profit is concentrated.** Over the whole 2025-01 to 2026-10 period, removing the 5 best trades cuts the portfolio Sharpe from 1.16 to 0.10. Five companies make half the gains and one (OTLK) makes 37%.
- **Unusual: most winning trades had no offering.** 77% of the profit came from flagged stocks that did not announce an offering within 5 days. The model mostly finds weak, cash-short companies that keep falling. The "offering" story is only part of the reason.
- **Unusual: the equity curve is flat, then jumps.** Most of the profit came between August 2025 and February 2026.
- **Cost sensitivity (whole period).** Sharpe 1.45 with no borrow fee, 1.16 at 30%, 0.50 at 100%, negative at 200%. If bid/ask costs were double, Sharpe is 0.27.
- **Choices made after seeing results:** the 5 day hold (1, 3 and 5 were looked at) and the $1 price floor. Without the price floor the whole-period Sharpe is 0.81.

### Trial registry stage (rejected)

- **Idea.** Sponsors update ClinicalTrials.gov records quietly. Short a company under $2B when a record shows it is still building a trial (starts recruiting, adds 20%+ sites, raises its enrollment target), buy when enrollment is over. Hold 60 days, hedge with XBI, only when no 8-K was filed within 2 days.
- **Data.** 35 monthly snapshots of the registry from AACT (Dec 2023 to Oct 2026). A change counts only when a new record version was posted, and it is dated by that posting date.
- **What happened.** The rules were designed on events up to June 2025, where the portfolio Sharpe after costs was 1.19. On the events after that it was -1.62 (95% interval -3.0 to -0.5). On the team windows it is 0.00 and -0.37 per trade.
- **Why the design half looked good.** Five trades made most of the profit, seven companies made half the gains, and 71% of the profit came in the first half of 2024.
- **Unusual: one short lost 447%.** Scholar Rock (SRRK) in October 2024, when its trial succeeded. This is the tail risk of shorting a biotech before data.
- **Unusual: the out-of-sample curve sinks steadily.** Both sides lost and only 38% to 39% of trades won. It is not one bad trade.
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

- **What ran.** The 155 days our model flagged were given to the team engine as events (`price_events` and `evaluate`, unchanged). The engine enters at the close of the session after the signal. Our trade is a short, so the result is minus the engine's "stock" number. No costs.
- **Coverage.** The engine could price 34 of the 155 events (22 tickers). 91 had no option chain at all. In the standard cell (nearest expiry, 5 days) that leaves 10 trades in each window.
- **Reading.** Stronger in sample than out of sample, the same direction as our own backtest. With 10 trades the intervals run from about -5 to +5, so this neither confirms nor contradicts anything.
- **Why our own backtest is the better measurement for this strategy.** It prices all 155 trades from real stock quotes with real costs. The team engine needs traded options, which most of these companies do not have.

## 6. HiPerGator runs

| Job | Node | What ran | Log |
|---|---|---|---|
| 44673323 | c0706a-s7 | Our backtests: offering short, trial registry (both halves) | `hpg_bundle/hpg_results/backtest_44673323.log` |
| 44673985 | c0706a-s3 | Team engine smoke test, 8 events | `lead_backtest_44673985.log` |
| 44674111 | c0702a-s7 | Team engine, `public_offering`, both windows | `lead_backtest_44674111.log` |
| 44675692 | c0704a-s1 | Team engine priced on our model's 155 signal days | `lead_signal_44675692.log` |

The HiPerGator numbers for our own backtests match the local run exactly.
All logs and engine output folders are in `hpg_bundle/hpg_results/`.

## 7. The dataset

Join key for every file: `cik` and `date` (integer YYYYMMDD). Files are in `biological_products/data/fds/`.

| File | What it holds |
|---|---|
| `fds_features.csv` | 89,150 rows, 156 feature columns: prices, market, financials, filings, 8-K categories, insiders, news, trials, FDA |
| `fds_missing.csv` | Same shape. One reason code per cell: 0 present, 1 not public yet, 2 never reported, 3 stale, 4 insufficient history, 5 not collected, 6 inapplicable, 7 derived |
| `fds_labels.csv` | Outcomes only. Never use as features |
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
python 21_stock_offer_test.py                         # offering model and signal slice
python 22_stock_real_costs.py                         # real bid/ask for those trades (needs MASSIVE_API_KEY)
python 40_offer_strategy_pnl.py                       # offering short: Sharpe, interval, audit
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
- Several looks were taken at the data before the rules were fixed. Every such choice is named in section 5.

## 11. Housekeeping

- This folder is on the branch `biological-products-audit`, built on `main` at fa30fcb (PR #4).
- Not in the repo because of size (see `biological_products/.gitignore`): `data/raw/aact/` (70 GB of AACT zips), `data/raw/aact_extract/`, `data/raw/aact_snapshots.csv`, `data/raw/companyfacts/`, `data/raw/research_cache/`. Scripts 00 and 34 rebuild them. No file holds an API key.
- The Massive API key was shared in chat earlier and should be rotated.
- `hpg_bundle/_to_delete/` and the `_stage.pkl`, `_tld*.pkl` files in `data/fds/` can be deleted.
