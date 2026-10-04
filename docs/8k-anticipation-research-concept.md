# Anticipating 8-K disclosures and option repricing: research concept

Status: idea-generation note, 2026-10-03. This records a hypothesis and a proposed research structure. No predictive or trading claim has been tested.

## OCR purpose and the two required answers

User clarification, 2026-10-03: the document system must read each company's **Form 8-K and relevant exhibits** and answer two questions:

1. **How is the document worded?** Measure financial sentiment, uncertainty, qualified or forward-looking statements, and changes from prior disclosures, with the actual sentences as evidence. Distinguish rhetorical tone from the economic meaning of the event.
2. **How might this affect option prices?** Estimate positive, negative, or negligible repricing for specified calls and puts over a stated horizon, conditional on industry, event type, market expectations, implied volatility, maturity, strike, and liquidity. Return uncertainty and permit an inconclusive result.

OCR supplies faithful text, tables, and provenance to that system. Wording measurements and option forecasts have different labels: corrected transcripts and human semantic annotations for the first task; independently observed future option quotes and returns for the second. LoRA adaptation of OCR does not by itself teach the relationship between words and option returns.

The original anticipation objective remains: before a future disclosure, use only earlier public information; after release, the actual document can update the forecast. A model reading an already released 8-K cannot claim to have predicted or traded the earlier price jump. See [the evidence review and recommended architecture](8k-ocr-sentiment-options-research.md) for the sources, model choices, timing boundaries, and proposed future evaluation.

The [proposed first-build design](superpowers/specs/2026-10-03-8k-document-analysis-design.md) narrows the first event family, defines evidence/novelty and readiness records, and proposes one call/put target. It is a scope-review artifact; its target definitions have not changed the current study configuration or been tested.

## What we are trying to learn

For companies with usable historical options data, assemble public information that existed **before** a potential 8-K: prior filings and exhibits, financial statements, issuer announcements, industry conditions, and the option market's own expectations. Ask whether those observations help anticipate (1) the arrival and type of a disclosure, (2) its material content or tone relative to what was already expected, and (3) the size and direction of the subsequent stock and option repricing. The possible use is to choose or hedge an options position before a disclosure, then reassess it when the filing becomes public.

This is three distinct questions, not one prediction. A model that identifies a coming 8-K may have no information about its direction; a model of the filing's words may add nothing beyond the option price; and a prediction can be accurate but untradeable after spreads, slippage, and hedging costs. “Hedge” also needs an explicit objective: protect an existing exposure, make a directional trade, or trade the size of an event move. Those objectives have different payoffs.

## Chosen modeling outcomes (design review pending)

The requested first outcomes are **the later filing's tone/content** and **the later option-price reaction**. These require separate labels and a strict distinction between two uses of FinBERT:

1. **Score historical filings:** extract each published 8-K by accession, preserve item and exhibit boundaries, and score sentences with a frozen FinBERT model. Manually review a labeled sample of 8-K sentences and documents before treating those scores as reliable tone labels; the public checkpoints were tuned on Financial PhraseBank financial-news sentences (ProsusAI) or analyst-report sentences (Yang/Huang), rather than complete 8-Ks. Compare with Loughran–McDonald counts. An SEC URL or OCR transcript alone is not a training label.
2. **Forecast before release:** on a fixed calendar of eligible company-days, build features only from earlier public material, including prior OCR output where needed. Learn the probability and tone/content of a future filing from later verified labels. The actual future 8-K text, item, and FinBERT score are excluded from this row.
3. **Predict the option outcome:** define one option contract and entry/exit rule using quotes available at the decision time; label the subsequent option repricing and after-cost hedge outcome. Inputs may include an out-of-sample *forecast* of filing tone, but never the actual later text or its FinBERT score. Compare with market-only, issuer/industry-frequency, and no-trade baselines. A separate post-release model may use the 8-K text once its public timestamp has passed.

The 1,630-CIK SEC URL catalog can provide source coverage for step 1. It does not imply 1,630 issuers have usable historical option quotes. Model training remains pending until labeling, option quote coverage, and evaluation windows are specified and reviewed.

The existing repository is an 8-K event study. `src/data.py` constructs disclosure events and option observations, `src/implementation.py` computes per-event strategy P&L, `src/capital_liquidity.py` estimates one-event capacity, and `run_all.py` writes study tables. It does not yet make a pre-filing forecast from a dated feature matrix or simulate a portfolio with shared capital. `docs/financial-profile-research.md`, `docs/company-sector-breakdown.md`, `docs/company-source-map.md`, and `docs/reit-source-map.md` already cover parts of the document, issuer, and industry source work. Keep this note separate from those source catalogs.

## Information boundary

For every hypothetical decision, store a `decision_timestamp` with timezone. A usable feature must have its own `public_at` timestamp **strictly before** that decision. Preserve `source_url`, CIK, accession or vendor ID, document hash, first-seen/retrieval time, parser version, and any later correction. Source period end and filing date are not enough to establish availability. Historical macro series require their publication/revision vintage; amended financial statements must not silently replace what was originally public.

The full text, item code, and tertiary category of the *future* 8-K are outcome information for a pre-filing model. They may label a historical outcome, but must never enter that event's pre-filing feature row. After verified public availability, receipt and processing, they can enter a **separate post-release model**; SEC acceptance alone does not prove the system could read or act on the filing then. Check earlier press releases, earnings calls, other filings, and scheduled events: an 8-K can formalize information the market already knew. Form 8-K is generally due within four business days after a triggering event, with item-specific rules and exceptions; its filing date is therefore not necessarily the first public-information date. [SEC Form 8-K](https://www.sec.gov/files/form8-k.pdf)

## Candidate research units and feature matrix

Conceptual primary key: `(CIK, decision_timestamp, candidate_event_family, feature_version)`. Ticker mapping and industry membership need effective dates. Candidate decision times should be generated for the entire eligible risk set, including company-days **without** a later 8-K, rather than only retrospectively selected filing dates.

| Feature family available at decision time | Examples | Provenance and caution |
| --- | --- | --- |
| Issuer history | Prior 8-K item frequencies, time since comparable event, filing cadence, amendments | Prior accessions only; changes in filing behavior may reflect disclosure practice rather than economic risk |
| Financial condition | As-filed cash, leverage, coverage, margins, accruals, guidance changes, segment trends | Exact period, unit, consolidation scope, and original publication time; use SEC XBRL before OCR |
| Prior language | Financial-domain negative, positive, uncertainty, litigious, and constraining counts; change from the issuer's own earlier documents; section-level counts | Separate actual sentiment from boilerplate, length, and OCR artifacts; preserve dictionary and parser versions |
| Industry context | Peers' already published results and filings, sector-specific metrics, dated macro releases | Industry classification and peer membership must be historically valid; sector effects may dominate issuer signal |
| Market expectation | Known event calendar, stock returns/volume, option bid/ask, open interest, implied move, skew, term structure, liquidity | The market may already price the information; last trades alone are weak evidence for an executable price |
| Data quality | Missing source, extraction confidence, stale quote, document type and parse method | Missingness can be informative but must never be filled using a later observation |

Use CIK as the issuer key. Organize analysis by an industry *mapping* and feature definitions, not thousands of hand-maintained company folders. Financial businesses, REITs, software companies, and drug developers need different accounting and event features; common normalized fields still permit cross-industry comparisons. SEC SIC is a useful initial grouping, but a current SIC snapshot is not historical membership, and diversified firms may not fit one label. See `docs/company-sector-breakdown.md` and `docs/reit-source-map.md`.

## Labels and reference comparisons

Possible labels, each fixed to a stated horizon and information time:

1. Whether a specified 8-K item/event family becomes public within the next *N* sessions, including no-event observations.
2. What the 8-K reveals **beyond prior public information**: signed financial change, management/action category, and document-language surprise. Human-reviewed labels may be required; tone alone is not the event's economic effect.
3. Stock move and option repricing after the **first public disclosure**, and realized P&L of a precisely specified hedge or strategy after costs.

Compare every richer model with simple references: issuer/industry filing frequency and calendar, prior issuer financial trend, the option-implied move and skew, a no-trade/no-change hedge, and same-issuer ordinary days. Measure incremental information and net option outcome, not just classification accuracy. A high rate of true predictions can still have negative value if rare misses are costly or options are expensive.

The Loughran–McDonald dictionary is a useful, transparent **text baseline**. Notre Dame provides the [master CSV and its seven sentiment categories](https://sraf.nd.edu/loughranmcdonald-master-dictionary/) and a [Generic_Parser.py example](https://sraf.nd.edu/textual-analysis/code/) for sentiment counts. Freeze and record the dictionary version. Compare raw counts, length-normalized counts, and issuer-relative changes by section. Check negation, tables, boilerplate, industry vocabulary, and manual samples. Dictionary counts are reproducible measurements of words, not objective labels for price direction or proof of causal impact. A domain language model such as [FinBERT](https://arxiv.org/abs/1908.10063) can be a later comparison only after the simple baseline is understood.

Author-backed, Apache-2.0 GitHub candidates for that later comparison are [Yang et al.'s FinBERT](https://github.com/yya518/FinBERT), whose pretrained corpus includes 10-K/10-Q reports and whose sentiment model was tuned on analyst sentences, and [ProsusAI's FinBERT](https://github.com/ProsusAI/finBERT), tuned for positive/negative/neutral financial sentiment. The latter repository documents older `pytorch_pretrained_bert` code; its [Hugging Face model](https://huggingface.co/ProsusAI/finbert) offers a newer inference route. Neither repository establishes accuracy for complete 8-Ks or option-price forecasts. Score dated sections or sentences and retain the source span; a whole filing may contain several opposing events.

## Document and compute concept

Build an accession-level source manifest first. SEC [Submissions and Company Facts APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) provide filing history and standardized XBRL facts without public-data API keys. Parse XBRL, HTML, and text-layer PDFs directly. Use OCR on HiPerGator only for genuinely scanned pages or exhibits, with source hash, page reference, extraction confidence, and manual checks for material tables, minus signs, and decimal points. Existing `src/document_ocr.py` and `docs/company-source-map.md` are work in progress; this note does not assume that the corpus or extracted facts exist. Observe SEC [fair-access limits](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits) for collection.

Suggested **future** boundaries, without creating modules now: source/availability catalog; as-filed fact and text extraction; point-in-time feature builder; pre-filing event/content models; post-release surprise/regime model; option execution and shared-capital portfolio simulator; analysis and audit reports. Keep immutable source metadata and derived features separate. Store enough provenance to reproduce any matrix cell from the document version actually available at the decision time.

## Holes most likely to overturn the idea

- **Unforecastable event timing:** Many 8-Ks concern unscheduled contracts, management changes, cyber incidents, or restatements. An event-conditioned result is not a deployable pre-event forecast unless it also accounts for all days when no event arrives.
- **The information may precede the filing:** A press release or other disclosure may move the market before the SEC 8-K. Align outcomes to the first public release, not automatically the 8-K date.
- **Known event versus unknown event:** Scheduled earnings are different from unscheduled 8-K items. Pooling them may create misleading average performance.
- **Market already anticipates the jump:** Option premiums and skew embed expectations and risk premia. The target is incremental, executable value relative to those prices, not merely predicting a large move.
- **Historical leakage:** Static current top-100 membership, today's issuer/industry metadata, revised fundamentals, future 8-K categories, and later OCR/label corrections can each leak information backward.
- **Weak execution evidence:** The current study uses daily last-trade option marks and synthetic stock exposure. It lacks a historical executable quote/spread, leg-level fill rule, shared collateral and overlapping-position ledger. These are material before claiming a tradeable edge.
- **Small, dependent samples and search:** Some 8-K categories are rare; multiple filings from one issuer and industry shocks are correlated. Many feature/strategy/industry searches can manufacture an apparent winner. Keep a trial log and a locked, later time window for eventual evaluation.
- **OCR and language errors:** Most SEC filings are machine-readable, while scanned exhibits can have unreliable tables. Word counts can mistake legal boilerplate for sentiment and miss the economic meaning of a contract or restatement.
- **Regime definitions chosen after outcomes:** A “rule for the day the 8-K drops” must say what is observable at each intraday decision and when it may switch positions. A regime filter chosen by looking at the test window is another fitted parameter.

## Related work and what is different here

- [Schmitz et al., *When Machines Trade on Corporate Disclosures*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3910451) study text-based strategies on 8-K filings and report that optimistic historical pricing and omitted liquidity filters can overstate profitability. Their focus is trading after a disclosure; the proposed pre-filing anticipation question adds a harder information-timing problem.
- [Oesch and Reinhart, *Corporate Voluntary Disclosure and Retail Option Trading*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5067087) find option-trading responses around voluntary 8-K filings. That supports the relevance of the options market but does not establish a pre-filing edge.
- [Leung and Santoli, *Accounting for Earnings Announcements in the Pricing of Equity Options*](https://arxiv.org/abs/1412.8414) model a scheduled event jump and pre-event implied volatility. It is a reference for comparing expected event risk with the option market, while unscheduled 8-Ks need a separate event-arrival model.

Inference from this literature: filing text, option prices, and event timing have each been studied. The proposed combination—strictly pre-filing public-document features, industry-aware event probabilities, an option-implied benchmark, and a post-release update—remains a **hypothesis** here. Novelty and profitability have not been established.

## Decisions to settle before any implementation or test

1. Is the primary outcome protection of an existing portfolio, directional option return, or an event-volatility trade?
2. Which 8-K item family is plausible to anticipate from public information, and how far ahead is the decision made?
3. What is the first public timestamp for each historical event, including press releases and exhibits?
4. Which companies had usable, historically dated option quotes at each decision time? The 1,630-CIK source universe and the existing 100-name options universe are different populations.
5. What fixed baseline, cost assumptions, and failure threshold would persuade us the extra document and OCR work adds value?

This concept note records ideas for discussion and revision. It did not run data collection, modeling, a backtest, or implementation.
