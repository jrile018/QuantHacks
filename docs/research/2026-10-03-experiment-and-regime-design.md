# Anticipating 8-K disclosures: experiment and regime design

Research date and source access date: **2026-10-03**. Status: research proposal; no fitting, installation, data acquisition jobs, or trading was performed for this document. Repository evidence: `docs/8k-anticipation-research-concept.md`, `docs/options-model-training.md`, `src/options_learning.py`, and `src/document_language.py`. External claims below link to primary sources; proposed design choices are recommendations, not empirical findings.

## 1. Resolve the decision before choosing the target

The original objective connects earlier public documents, industry conditions, future disclosures, and protecting an exposure. The implemented learner instead predicts four outcomes: call/put midpoint premium changes and call/put after-cost long-option returns. Contracts share an expiry 90–180 days away nearest 120 days; strikes approximate 105% and 95% of decision spot. Entry follows the decision and exit occurs at the next supplied session close after the entry session. Selecting the largest predicted net return against zero implements standalone directional choice. It cannot establish portfolio protection without the portfolio.

This matters concretely: a long put can lose premium while still cushioning a falling stock position; a profitable call can increase the risk of an existing long position. Call delta is positive and put delta negative, with magnitude changing with spot, volatility, and time. Fixed moneyness therefore does not fix hedge exposure. [Options Industry Council, Delta](https://prd-web.optionseducation.org/advancedconcepts/delta).

Three candidate objectives require different evaluation contracts:

| Objective | Necessary inputs | Primary output and evaluation |
|---|---|---|
| Protect an existing portfolio | Dated holdings, quantities, marks, available capital, protection horizon, premium budget, permitted instruments | Distribution of portfolio-plus-hedge loss; reduction in expected shortfall at a frozen confidence level, premium spend, and protection failures versus no hedge and a fixed hedge |
| Trade direction | Contract selection, executable quotes, cash costs, sizing, capital limits | Conditional net option return distribution; forecast error and incremental decision value versus calendar/market baselines |
| Trade event magnitude | Joint call/put quotes, combined position and sizing rules | Joint position payoff or realized move relative to implied pricing; separate experiment and targets |

**Grill question 1:** What exposure should this protect, over what horizon and premium budget, or is the intended objective standalone option returns? **Conditional recommendation:** choose exposure-conditioned portfolio protection if “hedge” means protecting owned assets; supply dated exposure before specifying the primary loss. If exposure is unavailable, retain premium prediction as research and defer hedge claims. No objective is silently selected here.

**Grill question 2:** At what fixed time can the system act, and are we predicting the first public economic disclosure, an SEC filing, or both within which horizon? **Conditional recommendation:** pilot one decision per eligible issuer at 15:30 New York time on each options session, with outcomes through the next session close, if this matches intended operation. Track SEC filing hazard separately from first-disclosure hazard. A longer anticipation horizon requires separately versioned payoff and holding rules.

## 2. Construct the risk set before observing events

Generate the complete eligible issuer/session grid first. Add later event labels only after generation, including ordinary rows with no subsequent disclosure. An event-only dataset conditions on an outcome unavailable at decision and cannot calibrate event probability. Freeze contemporaneous listing, option eligibility, liquidity rules, and security mapping; preserve delisted issuers and historical industry assignments. Record exclusions by industry, calendar period, event status, and liquidity so selective quote coverage is visible. Missing quotes are unavailable outcomes, never zero returns.

An 8-K filing timestamp need not identify the economic news arrival. Form 8-K generally requires reporting within four business days of an event, subject to specific instructions and exceptions. Store triggering occurrence, earliest verified public disclosure, SEC acceptance, local receipt, and completed processing separately. [SEC, Form 8-K instructions](https://www.sec.gov/files/form8-k.pdf).

Group a press release, earnings call, 8-K, exhibits, and amendments describing the same economic event under one `event_group_id`. Item codes are multiple labels where appropriate; do not count every item or duplicate exhibit as an independent surprise. The grouping rule may use later records for label linkage, but retrospective linkage cannot become a predictor. Conflicting earliest-public timestamps require adjudication or exclusion.

Use a discrete-time occurrence model for `P(first disclosure of family k before horizon | information at decision)`, with a separate no-event outcome and documented competing-event handling. Fit simple historical issuer/industry frequencies before richer models. Model later content or tone conditionally on event occurrence. Forecast option outcomes across the full eligible grid because options can move on no-event days. If combining an event probability with event-conditioned returns, include the no-event payoff component; do not multiply an already unconditional return forecast by event probability again.

## 3. Define text measurements without conflating them with outcomes

Araci’s original FinBERT research evaluates financial sentiment classification; it does not validate anticipating unpublished filings or forecasting executable option payoffs. [Araci, 2019, original paper](https://arxiv.org/abs/1908.10063). The ProsusAI model card states financial-domain adaptation, Financial PhraseBank fine-tuning, and positive/negative/neutral softmax outputs. Those are model classifications, not calibrated probabilities of future market direction. [ProsusAI model card](https://huggingface.co/ProsusAI/finbert).

Before using these measurements, annotate an independent sentence/section sample spanning 8-K families and industries. Review factual economic polarity, rhetorical tone, negation, uncertainty, material numeric changes, and conflicting events separately. Record annotator disagreement and source spans. Freeze section aggregation and truncation handling; evaluate reliability on held-out annotated documents. A future filing’s actual text and sentiment can label the content task but cannot enter its anticipation features. Stacked predicted-tone features require chronological out-of-fold predictions within development data and a separately frozen upstream model for final evaluation.

Use transparent counts and issuer-relative textual changes as the first text baseline. Notre Dame’s official dictionary was updated in March 2026, describes seven sentiment categories and category-addition/removal years, and permits free academic use while directing commercial users to obtain a license. Archive exact bytes, version, rights basis, tokenization, and category rules. [Loughran–McDonald official dictionary and terms](https://sraf.nd.edu/loughranmcdonald-master-dictionary/). A bundled custom vocabulary is a custom vocabulary unless official provenance is demonstrated. Current dictionary memberships applied backward are retrospective features; reconstructing an older version requires evidence and correct treatment of later category removals.

Freeze language-model weights and tokenizer hashes and audit pretraining/fine-tuning date coverage. Contemporary checkpoints may contain later information even when the input document is old. The original DatedGPT working paper addresses this risk with temporally partitioned pretraining; it does not certify this project’s FinBERT checkpoint. [Yan et al., 2026](https://arxiv.org/abs/2603.11838). Where corpus boundaries are unknown, label the result retrospective and add a prospective evaluation after the checkpoint freeze. Company-name masking is a sensitivity check, not proof of contamination removal.

## 4. Measure incremental value through ordered comparisons

Prespecify one primary loss per chosen objective and a small ordered ablation family:

1. Historical frequency for occurrence; training mean and no-trade for option outcomes; no hedge and fixed-budget hedge for portfolio protection.
2. Earnings-calendar and market-only information: known schedule, issuer return/volatility history, entry quotes, spread, and available implied-volatility measurements.
3. Add simple earlier-text counts and issuer-relative changes.
4. Add dated industry features with pooled shrinkage rather than sparse independent industry models.
5. Add frozen FinBERT measurements, then a limited train-fitted regime interaction family.

For occurrence report log loss, Brier score, reliability diagrams, precision/recall at a frozen capacity, and alert lead time. For return prediction report per-target MAE/MSE, improvement over the same-row market baseline, and residual diagnostics; average MSE across four targets is not automatically the business objective. For hedge evaluation report cash-normalized loss, expected-shortfall difference, budget use, and losses beyond the agreed protection threshold, including no-event days. Quantile forecasts require coverage and quantile-loss checks. Direction accuracy alone is insufficient.

Use the same eligible observations for paired incremental comparisons and publish the excluded cohort separately. Reserve final-test subgroup reporting in advance; distinguish descriptive subgroup intervals from additional discovery tests. Industry-specific benefits must beat the pooled benchmark with adequate uncertainty estimates before adding separate models.

## 5. Keep option pricing and regime information contemporaneous

Option value reflects underlying price, strike, remaining time, rates, dividends, and volatility. Implied volatility can rise before an event and fall afterward, causing a call to lose value despite a favorable underlying move. [Options Industry Council, Option Price Behavior](https://www.optionseducation.org/referencelibrary/faq/option-price-behavior). Model stock return, implied-volatility changes, and time decay as diagnostic outcome decomposition, while keeping future values out of predictors. The current 120-day contract rule is a frozen research choice, not evidence that it is the right hedge horizon.

Retain synchronized historical bid/ask, underlying timestamps, actual contract deliverables, size, receipt evidence, and quote-quality exclusions. Buying at ask and exiting at bid incorporates the observed spread; add separately documented cash fees and extra execution slippage without charging the spread twice. Quotes are execution assumptions, not guaranteed fills. [Options Industry Council, Trade Entry and Execution](https://www.optionseducation.org/referencelibrary/faq/trade-entry-execution). The repository’s USD 1 fee plus USD 2 additional slippage per side is a research assumption requiring sensitivity analysis before final-test access.

Candidate regimes are continuous decision-time features first: lagged realized volatility, market/industry returns, observed liquidity, term structure, and event-calendar proximity. VIX describes option-implied S&P 500 volatility over approximately 30 days, not an issuer’s 120-day option volatility. [Cboe VIX FAQ](https://www.cboe.com/tradable_products/vix/faqs). Revised macro history must use the available vintage; ALFRED preserves original releases and later revisions. [Federal Reserve Bank of St. Louis, ALFRED API](https://fred.stlouisfed.org/docs/api/fred/alfred.html).

Fit scaling, bin thresholds, clustering, imputation, and regime interactions only on training data. A state model may filter using information through decision, but full-series smoothing or future-selected change points invalidate historical predictors. Report unseen-state handling and missing-data reasons. Choose all thresholds on development data and freeze them before final evaluation.

## 6. Validation, uncertainty, and stopping rules

Preserve the existing chronological train/validation/protected-test design, event grouping, target-availability checks, and overlapping-label purges. Purging and embargo address overlap leakage, as described by the originating researcher, but do not repair incorrect public timestamps or model-corpus contamination. [López de Prado, research methods](https://www.quantresearch.org/Innovations.htm).

Estimate paired loss-difference intervals with economic-event clustering and calendar blocks that retain simultaneous cross-issuer shocks. Select block construction using development data; include issuer-dependence sensitivity checks. The stationary bootstrap’s original scope is weakly dependent stationary observations, so its assumptions need assessment and regime-specific sensitivity reporting here. [Politis and Romano, original publication](https://www.tandfonline.com/doi/abs/10.1080/01621459.1994.10476870).

The existing minimums of 30/10/10 event groups are software gates, not power evidence. Use a development-only pilot to estimate event frequency, usable quote coverage, within-cluster dependence, tail availability, and interval width. Specify the economically relevant improvement and required precision before sizing the final evaluation. If intervals remain too wide, report inconclusive evidence and collect further prospective observations; do not invent sample adequacy.

Record every feature set, target, prompt, hyperparameter, horizon, exclusion threshold, and unsuccessful trial in an append-only research ledger. PBO examines selection over candidate strategies using a dedicated resampling framework; it is not interchangeable with chronological deployment evaluation. [Bailey et al., original PBO paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). DSR adjusts Sharpe assessment for selection and nonnormality and requires trial information; use it only after constructing a valid shared-capital return series. Per-event option returns do not supply that series. [Bailey and López de Prado, original DSR paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

Stop advancement for unresolved objective/horizon, unreliable first-public chronology, unknown instrument mapping, inadequate real bid/ask coverage, unreviewed text labels, or contaminated heldout access. A protected-test ledger guards local reuse, but cannot prove nobody inspected outcomes elsewhere. Document any exposure and establish a new prospective test instead of relabeling the inspected period untouched.

## 7. Parallel work contracts after the two decisions

These are proposed independently owned work packages, not authorization to fit models now. All workers must preserve others’ edits.

| Package and ownership | Dependencies | Contract output |
|---|---|---|
| A: `docs/research/risk-set-and-event-contract.md` | Decision time, horizon, event definition | Complete grid specification; economic grouping; timestamp evidence; no-event and exclusion audit |
| B: `docs/research/text-measurement-contract.md` | A schema; agreed tone/content definitions | Annotation rubric; frozen dictionary/model provenance; calibration report design; upstream out-of-fold interface |
| C: `docs/research/hedge-payoff-contract.md` | Objective and exposure answers | Holdings schema; fixed hedge comparator; executable quote/cost contract; cash normalization and horizon alignment |
| D: `docs/research/validation-and-regime-contract.md` | A–C draft interfaces; primary objective | Frozen split/ledger specification; paired comparisons; train-only regimes; pilot precision procedure and stopping rules |

A–C can develop their contracts concurrently after decisions; D can draft leakage and source checks concurrently, then finalize only after their interfaces agree. Integration requires matching identifiers, currencies, decision times, label horizons, and primary metric across all four outputs. Only then should a bounded development pilot be proposed.
