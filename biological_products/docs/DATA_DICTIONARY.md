# Biological Products (SIC 2836) feature matrix

Final file: data/final/feature_matrix_final.csv (57 columns, 9,808 rows). One row per 8-K filing per Massive category.
Key: accession_number + tertiary_category. Companies: 139 tickers (PRTO dropped, it is an ETF).
Every feature uses only information from BEFORE the filing date. Columns starting with y_ are outcomes. Never use them as features.

## Identity and target label
accession_number, filing_date, ticker, cik: the 8-K and the company.
primary_category, secondary_category, tertiary_category: Massive's AI-tagged 3-level label of what the 8-K is about. tertiary is the thing to predict.

## Financials (source: SEC companyfacts XBRL, script 01_flatten_facts.py)
cash, assets, liabilities, equity: latest value from a filing made before this 8-K.
rd_annual, netinc_annual, opcf_annual: latest 10-K full-year value known at the time.
runway_years: cash / annual cash burn. Blank if the company has positive operating cash flow.
rd_to_assets: R&D / assets.
Weakness: annual flows can be up to a year old. Quarterly values were skipped because 10-Q numbers are year-to-date.

## Clinical trials (source: ClinicalTrials.gov API v2, script 02_pull_trials.py)
n_trials, n_open, n_ph3_open: trials started before the 8-K, how many are open, how many are open Phase 3.
n_pc_next90, n_pc_prev90: trials with a primary completion date in the next or previous 90 days.
Weakness: ClinicalTrials.gov gives today's snapshot (pulled_on in trials.csv). Companies revise dates, so these columns leak a little future information. Matching is by sponsor name, so it can miss subsidiaries.

## News and sentiment (source: Massive news endpoint, scripts 04_pull_news.py, 10_add_news.py)
news_n_7d, news_n_30d: articles tagged to the ticker in the 7 or 30 days before the filing day.
news_sent_7d, news_sent_30d: average sentiment score, from -1 to 1.
Sentiment score is our own model (TF-IDF + logistic regression) trained on Massive's sentiment tags, which only exist from mid-2024. Out-of-fold accuracy 76% vs 51% for always guessing positive. Older articles are scored by extrapolation, so they are noisier.
Weakness: news is sparse. Median event has 0 articles in the prior 7 days. Coverage starts 2021, so events before Feb 2021 are blank.

## Prices (source: Massive daily bars, adjusted for splits, scripts 05, 11, 12, 13)
price_asof, prev_close: last trading day before the filing and its close.
ret_5d, ret_20d, ret_60d: returns up to that day. excess_20d: ret_20d minus XBI.
vol_20d: std of daily returns. adv_20d: average daily dollar volume. off_52w_high: close / 52-week high - 1. vol_spike: 5-day avg volume / 60-day avg volume.
Rows with prices more than 5 days stale are blank. One unadjusted reverse split (AIM) was blanked.

## Outcomes (do not use as features)
d0_date: first trading day on or after the filing date.
y_ret_d0: return from prev_close to the close on d0. y_ret_d1: to the close the day after. y_abs_d1: absolute value of y_ret_d1.
Weakness: no time of day. A filing after the close moves the stock on d1, a filing before the open moves it on d0. Heavy tails (some moves are +300%). Use medians, ranks or winsorizing.

## SEC filing activity (source: EDGAR submissions API, scripts 06, 14)
days_since_shelf: days since last S-3/S-1 style registration. days_since_p424b: days since last 424B prospectus. days_since_k8: days since last 8-K.
n_p424b_90d, n_form4_30d, n_form144_90d, n_act13d_180d, n_late_365d, n_k8_30d: counts of 424B (offerings), Form 4 (insider trades), Form 144 (insider sale notices), 13D (activist stakes), NT (late filing notices) and 8-Ks in the window before the filing.
Weakness: these are counts of filings of any kind. Buy and sell direction is in the insider columns below.

## Insider open-market trades (source: EDGAR Form 4, scripts 07 and 15)
n_insider_buys_30d, n_insider_buys_90d: open-market purchases (transaction code P) in the window before the filing.
n_insider_sells_90d: open-market sales (code S). n_officer_buys_90d: purchases by officers.
insider_buy_usd_90d, insider_sell_usd_90d, insider_net_usd_90d: dollar value (shares times price).
Cleaning: dollar values ignore rows with a price of zero or above $5,000 (data errors), and each transaction is capped at $25M so a few big private placements do not dominate.
Weakness: sales include pre-planned 10b5-1 sales, which carry little information. Buys are rarer and more informative. Only the direct issuer filings are counted.

## PDUFA dates (source: full text of 8-Ks, scripts 08 and 15)
days_to_next_pdufa: days until the nearest FDA decision date that a company had already announced in an earlier 8-K (blank if none known, or more than 365 days away).
days_since_last_pdufa: days since the most recent such date passed (blank if none within 120 days).
Weakness: very sparse. Only 236 events have an upcoming date and only 23 of the 419 regulatory_decision events. Most PDUFA dates are announced in press releases that are not 8-Ks, or not at all.

## Side files, not yet in the matrix
purplebook_actions.csv: FDA biologic approvals (15 companies only).
fda_actions.csv: FDA drug (non-biologic) approvals, 3 companies. Low value.
coverage.csv: which clinical_trial_results events have options data (228 of 583 have 3+ bars).

## Run order
See README.md in this folder. Scripts are numbered 00 to 15 in scripts/.
