o# Financial profiles from SEC filings: source and build research

Researched 2026-10-02. Initial universe: the **1,630 distinct CIKs already in Tiger Cloud**. This is a design and source audit; it does not claim that the financial statements have been downloaded into Tiger.

## The short version

Use SEC filings as the evidence for company financials. The SEC's public **Submissions** and **Company Facts** APIs need **no API key**. Use the SEC's **Financial Statement and Notes Data Sets** for more detailed XBRL facts, custom tags, dimensions, presentation, and calculation relationships. Link every value to its filing and document online. Parse HTML/iXBRL/XML first; use OCR only for scans and image-only exhibits. Keep company-reported numbers separate from our calculated metrics, and record every mismatch instead of forcing a false balance. [SEC APIs][1] · [Financial Statement and Notes Data Sets][2] · [EDGAR document access][3]

The local export made from Tiger contains 1,630 unique CIKs and 2,014 distinct 8-K accessions dated 2024-01-02 through 2026-10-01. Tickers are present for 1,406 CIKs; 224 have no ticker in that export. The 8-K disclosures are event records, mainly CFO appointments. They are **not** a complete statement of those companies' revenue, costs, assets, debt, or cash flows. See the ignored local files `data/processed/tiger_8k_companies.csv` and `data/processed/tiger_8k_filings.csv`; the Tiger copy is in `quant_hacks.source_files` and `quant_hacks.api_responses`. CIK, rather than ticker, should be the issuer key because tickers can change or be absent.

## Which forms matter

All these public filings can be discovered through the Submissions API and opened through the SEC's EDGAR archive without a public-data API key. `/A` amendments are separate filings and must be retained. The extraction column says what to use **after** discovering the accession; an 8-K event tag from Massive is not a substitute for the full filing. The SEC explains the domestic, foreign, offering, ownership, and fund form families in its [EDGAR guide][4].

| Priority | Forms and documents | Financial profile contribution | Preferred extraction | OCR? |
| --- | --- | --- | --- | --- |
| Core | **10-K, 10-K/A** | Audited annual statements, accounting policies, notes, segments, debt, leases, commitments, tax, MD&A, risks | Company Facts plus Financial Statement and Notes data; confirm in primary filing and exhibits | Only image-only pages/exhibits |
| Core | **10-Q, 10-Q/A** | Unaudited interim statements, notes, MD&A, liquidity and risk updates | Same structured data; use exact duration and instant contexts | Only image-only pages/exhibits |
| Core | **8-K, 8-K/A**, especially Items 1.01, 2.01, 2.02, 2.03, 4.02, 5.02, 9.01 | Contracts, acquisitions, earnings releases, debt events, financial-statement non-reliance, officer changes, exhibits | Filing item metadata, HTML/iXBRL, attached EX-99/EX-10 and other exhibits | Only when an attachment is scanned |
| Core for foreign issuers | **20-F, 20-F/A; 40-F, 40-F/A; 6-K, 6-K/A** | Annual foreign issuer accounts and interim/current disclosures | XBRL when present, then filing and attached financials; preserve IFRS/US-GAAP and currency | Only scanned attachments |
| Context | **DEF 14A, DEFA14A** | Executive pay, governance, related-party context, share plans | Filing tables/text; some data may be structured | Only scanned attachments |
| Context | **S-1, S-1/A; F-1; S-3; 424B series** | IPO/prelisting history, offering terms, dilution, capital raised, selected financials | Filing/prospectus and exhibits | Only scanned attachments |
| Event context | **S-4, DEFM14A, 425, tender-offer forms** | Deal terms, pro forma financials, acquisition consideration | Filing/prospectus and exhibits; link to 8-K and later 10-K/Q | Only scanned attachments |
| Separate entity | **11-K** | Employee benefit plan accounts | Filing/XBRL if relevant; do not add plan assets to issuer assets | Only scanned attachments |
| Ownership context | **Forms 3, 4, 5; SC 13D/G; 13F-HR** | Insider/beneficial/institutional holdings | Filing/XML where available | Rarely |
| Extension beyond current universe | **1-A, 1-K, 1-SA, 1-U; C, C-AR** | Regulation A and crowdfunding issuer disclosures, useful for some small issuers | Filing documents and any structured attachments | More likely, depending on document |

**Scope boundary:** the initial 1,630 CIKs may include companies with different filing obligations, inactive issuers, and firms without ticker metadata. Company size must be measured explicitly. SEC filer status, SIC, and filed revenue/assets can create coverage cohorts; a true large/mid/small **market-cap** classification requires a dated share-price/share-count or float source. SEC public-float/filer categories are not interchangeable with ordinary market-cap tiers. Smaller reporting companies can use scaled disclosures, so detail and history can differ by issuer. [SEC smaller reporting company guide][5]

Form 11-K is a **benefit plan**, while 13F describes a **manager's holdings**. Neither is the issuer's operating revenue or an extra expense to add to the income statement. Similar caution applies to proxy compensation and merger/prospectus amounts: they may describe transactions, commitments, or stock grants rather than booked current-period cash costs. The SEC's form descriptions and exhibit guidance support this separation. [EDGAR guide][4]

## Access, keys, and online documents

| Source | What it provides | Credentials | Access pattern |
| --- | --- | --- | --- |
| SEC Submissions API | Issuer names, ticker/exchange metadata, filing history, accession, form, dates and primary document | **None** for public data | `https://data.sec.gov/submissions/CIK##########.json` where CIK has 10 digits; follow `filings.files` for older history |
| SEC Company Facts API | Standard-taxonomy, entity-wide XBRL facts and units across filings | **None** | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` |
| SEC bulk archives | Nightly Submissions and Company Facts snapshots | **None** | `submissions.zip` and `companyfacts.zip` linked from the [API page][1]; useful for large backfills |
| SEC Financial Statement and Notes Data Sets | Filed numeric and text facts, custom tags, dimensions, rendering/presentation/calculation relationships | **None** | Monthly/quarterly ZIPs on the [dataset page][2]; large downloads, filter to the 1,630 CIKs after download |
| SEC EDGAR archive | Human-readable primary filings, full submission text, individual exhibits, source XBRL/XML | **None** | `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_without_dashes}/`; resolve actual document filenames from the filing index |
| Existing Massive API | Current challenge's 8-K disclosure tags and options/market data | Existing `MASSIVE_API_KEY`, locally stored in ignored `.env` | Keep its event/market data provenance and license separate from SEC fundamentals |
| OCRmyPDF/Tesseract | Searchable text from scanned PDFs | **None** | Local or approved remote compute; software has no per-page API fee, but compute/review costs remain |
| AWS Textract or Google Document AI, optional | OCR and table/layout extraction for difficult scans | Cloud account, billing, and IAM/service credentials | Only if the measured scan rate and quality justify a managed service |
| Tiger Cloud | Team-queryable issuer, filing, facts, and quality tables | Tiger project/service access or a dedicated least-privilege database role | Never publish database credentials or cloud tokens in Git |

The SEC's `data.sec.gov` API explicitly has **no authentication or API keys** and does not support browser CORS, so run ingestion from a backend/CLI rather than directly from a web page. Scripted retrieval needs an identifying `User-Agent` with a real contact address, caching, compression, and a **global ceiling of 10 requests per second across all workers**. The previous local attempt to fetch `company_tickers.json` returned HTTP 403; diagnose access with a small, correctly identified request before a bulk job. The 403 does not change the SEC's documented public access policy. [SEC APIs][1] · [EDGAR access and fair use][3]

The online link for each filing should be the **SEC accession index**, which lists the documents actually submitted. Store the primary-document and exhibit URLs from that index as well. The complete submission `.txt` is a useful archival fallback. SEC links are public; a source file can later be mirrored in private object storage with its SHA-256 to protect reproducibility against corrections, removals, or network access issues. Keep the original SEC URL in every row. [EDGAR document access][3]

## A source hierarchy for each number

1. **Discover:** build an issuer and filing manifest from each CIK's Submissions response, including older `filings.files`, amendments, accepted/filing dates where available, reporting date, form, accession, primary document, and item/exhibit metadata.
2. **Get standardized facts:** use Company Facts for broad coverage and fast comparisons. It contains only qualifying **standard-taxonomy, entity-wide** facts. It omits custom issuer tags and many segment/dimensional facts. Do not use `frames` for exact fiscal-period statements because it chooses facts nearest calendar periods. [SEC APIs][1]
3. **Get detailed filed facts:** use the Financial Statement and Notes dataset for custom tags, dimensions, note text, presentation order and calculation arcs. Its documented `SUB`, `TAG`, `DIM`, `NUM`, `TXT`, `REN`, `PRE`, and `CAL` tables provide accession-level links. Preserve `ddate`, `qtrs`, `datp`, and `durp`: the first two are rounded dates/durations, and the latter two indicate their offsets. Recover and verify the **exact** start/end or instant dates from the source XBRL context before period matching or quarter derivation, especially for 52/53-week years. Long `TXT` values can be truncated and flat `NUM` values have limited decimal places, so read original filings/XBRL for full-fidelity evidence. The SEC says the data are **as filed** and may contain redundancies or inaccuracies; always retain the source accession and compare important amounts with the filing. [Dataset][2] · [Dataset data dictionary][6]
4. **Read the filing and attachments:** parse iXBRL/HTML and source XBRL/XML, including notes, exhibits and tables. Use the SEC archive document list to find filenames instead of guessing. An earnings release in EX-99 can predate a 10-Q; label it preliminary until the periodic report confirms it. [EDGAR access][3]
5. **OCR only the exceptions:** first test whether a PDF page has usable text. If not, use OCRmyPDF/Tesseract. Use a table-aware managed OCR service only when ordinary OCR cannot preserve a material financial table. Record page, bounding box, confidence, engine/version, and original document hash. Human-review low-confidence or arithmetically inconsistent material amounts. OCR output is a derived observation, never the original document. [OCRmyPDF modes][7] · [Textract table output][8]

This hierarchy keeps the 8-K announcement, later 10-Q, and audited 10-K as distinct evidence. It avoids silently replacing earlier numbers with later restatements.

## What a company profile should contain

Each metric is scoped to **CIK + filing accession + exact period + unit/currency + consolidated or dimensional context + as-of date**. The profile should carry both the number and a click-through source, plus a quality flag.

| Profile area | Reported fields to seek | Main source and checks |
| --- | --- | --- |
| Identity and coverage | Legal/current/former name, tickers, exchanges, SIC, filer status, fiscal year end, reporting currency, active/foreign status | Submissions and dataset `SUB`; changes are dated |
| Income | Revenue categories, cost of revenue, gross profit if presented, operating expense categories, operating income, interest/non-operating items, tax, net income, EPS | 10-K/Q or 20-F/40-F/6-K; align duration, units, signs, and reported subtotals |
| Balance sheet | Cash, receivables, inventory, assets, payables, debt, leases, liabilities, equity, noncontrolling/temporary interests | Exact instant date; assets versus the issuer's presented liabilities/equity bridge |
| Cash and capital | Operating/investing/financing cash flows, capex, acquisitions, debt issued/repaid, dividends, repurchases, FX, restricted cash | Exact duration; reconcile reported cash roll-forward, then connect debt/equity changes to notes and 8-Ks |
| Notes and commitments | Debt maturities/rates/covenants, leases, tax, pensions, contingencies, commitments, related parties | Detailed XBRL notes and filing/exhibits; label future commitments separately from current expenses |
| Operations and segments | Segment/geographic revenue and profit, products, customer concentration, share counts | Dimensional XBRL plus segment table and eliminations; never add segments to consolidated totals twice |
| Material changes | Earnings releases, financing, M&A, contract events, non-reliance/restatements, auditor and leadership changes | 8-K and exhibits, then later periodic reports; event links to impacted metrics |
| Governance and funding | Officer/director compensation, insider ownership, offerings, dilution | Proxy, offering and ownership forms; keep transaction amounts distinct from recognized revenue/expense |

For small public issuers, scaled reporting can mean fewer periods or fewer line items. For foreign issuers, annual and interim cadence, IFRS versus US-GAAP, and reporting currency vary. Some CIKs may be funds or other entity types that need a separate financial template; classify them before applying operating-company equations. Public EDGAR cannot reveal every invoice, customer payment, supplier cost, or private-company ledger. A complete **reported** financial profile is achievable; a complete transaction-level cash ledger is not. [SEC API taxonomy scope][1] · [SEC smaller reporting guide][5] · [EDGAR guide][4]

## Making the numbers add up honestly

Use arithmetic as a **quality check** on disclosed statements, not as a way to invent undisclosed detail. Preserve two versions of each period: **as known on a historical date** (only filings available by then) and **latest restated/recast** (newest relevant filing). `10-K/A`, `10-Q/A`, later comparative columns, and 8-K Item 4.02 can change the correct value. [SEC APIs][1] · [8-K form][9]

| Check | Expected bridge | Common reason it needs explanation |
| --- | --- | --- |
| Gross profit | Revenue minus cost of revenue = **reported gross profit**, if that subtotal exists | Multiple revenue/cost categories, presentation differences, rounding |
| Operating result | Gross profit minus included operating expenses, plus/minus other operating items = **reported operating income** | Banks/insurers or issuers without this subtotal; custom tags and signs |
| Net result | Pretax income minus income tax = **reported net income**, adjusted for the issuer's presented structure | Discontinued operations, attributable-to-parent vs consolidated net income |
| Balance sheet | Assets = liabilities + equity, using the issuer's classification | Redeemable/temporary equity, noncontrolling interests, missing dimensions |
| Cash roll-forward | Beginning cash + CFO + CFI + CFF + FX/other reported reconciling items = ending cash | Restricted cash definitions, FX, acquisitions, presentation |
| Segment bridge | Segment totals + corporate items/eliminations = consolidated reported amount | Intersegment sales and different profit measures |
| Quarterly bridge | Full year duration minus the matching year-to-date/interim durations yields a derived missing quarter | Later restatements, fiscal calendar changes, 53-week year, mismatched units |

The income statement is **accrual** accounting. Net income is not cash from operations; cash flow adjusts for noncash items and working capital. Debt proceeds are financing cash, not revenue. A purchase commitment is not automatically an expense. A stock grant's fair value is not automatically cash paid. Keep those categories distinct. [FASB cash-flow standard][10]

Reconcile only facts with the same entity, **exact source-context start/end or instant date**, currency/unit and dimensional scope. Never treat the flat dataset's rounded `ddate`/`qtrs` as exact dates; keep its `datp`/`durp` offsets and verify the original context. Prefer the filer-reported subtotal, then use XBRL calculation/presentation relationships and visible filing tables to explain its components. Use the XBRL `decimals` accuracy when deciding whether a residual is explainable by rounding; log the actual difference and explanation. An unmatched line stays `unresolved` or `not_disclosed`, with a link to the original filing. The SEC dataset's `CAL` and `PRE` tables help, but its own documentation warns that as-filed submissions can contain inconsistencies. [Dataset dictionary][6] · [SEC XBRL guide][11]

## Proposed Tiger shape and delivery sequence

Place the new corpus in a separate `financial_profiles` schema so the existing `quant_hacks` 8-K study stays reproducible:

| Table | Key fields and purpose |
| --- | --- |
| `issuers` | CIK, current name, ticker history, SIC, filer type, fiscal year end, reporting currency, coverage state |
| `filings` | CIK, accession, form, filed/accepted/report dates, amendment relation, SEC index URL, fetch/hash state |
| `documents` | Accession, document sequence/type, filename, SEC URL, MIME, SHA-256, storage URI, text/OCR status |
| `facts_raw` | Accession, taxonomy/tag/version, value, unit, exact source-context period start/end or instant, original rounded `ddate`/`qtrs` and `datp`/`durp`, dimensions, decimals, source document/page, retrieval time |
| `metrics_normalized` | Canonical metric, reported/derived status, source fact IDs, accounting scope, period, unit, as-of version, confidence |
| `reconciliation_checks` | Check name, operand fact IDs, reported result, computed result, residual, rounding allowance, status and review note |
| `extraction_runs` | Dataset snapshot, parser/OCR version, job settings, errors, processing timestamps and costs |
| `coverage` | Per-CIK/per-year expected versus found forms, statement/notes availability, unresolved critical checks |

Keep original documents in the SEC archive and, if durable mirrored access is required, in object storage. Store metadata, parsed facts, search text, and source hashes in Tiger. Avoid copying every large PDF binary into PostgreSQL; use a URL/storage pointer so teammates can open the original and the derived text side by side.

1. **Access pilot:** select roughly 30 CIKs by filer status, SIC, foreign/domestic status and filed revenue/assets (not by assumed ticker cap). Confirm SEC retrieval from the execution host with a declared real-contact `User-Agent`, global rate limiter, and no 403. Verify online filing index and Company Facts for each.
2. **Core backfill:** for all 1,630 CIKs, ingest identity, full filing manifest, Company Facts, and relevant SEC Financial Statement and Notes rows. Process large historical ZIPs on the configured `home-pc` via detached `tmux`, then import filtered results to Tiger. Start with recent years for an end-to-end check; expand to all available structured history without changing the schema.
3. **Document layer:** attach SEC primary documents and financial exhibits for core forms. Parse iXBRL/HTML/XML, then classify PDF pages for selective OCR. Preserve raw hashes and page references.
4. **Accounting layer:** map common metrics by industry/taxonomy, add issuer-specific custom tag mappings, produce both as-filed and latest-restated views, run reconciliation checks, and queue exceptions for review.
5. **Daily maintenance:** poll changed submissions, process new filings/amendments, keep a snapshot watermark, and refresh impacted facts and quality checks. Batch historical work from SEC bulk data; respect the SEC's aggregate request limit.

**Acceptance evidence:** all 1,630 CIKs have an issuer/coverage record; every included accession has a working SEC source link or an explicit unavailable status; every published amount carries accession, period, unit, scope and extraction method; every supported statement has a reconciliation result with residual or reason it cannot be checked; amendments do not overwrite historical as-of values; a stratified manual sample of large, mid and small/foreign/specialized issuers checks against the rendered filings. Coverage percentages and unresolved residuals should be reported, not hidden.

## Operating cost and access choices

SEC public data and the open-source OCR option have **no per-request/per-page API-key charge**. Compute, storage, Tiger service usage, monitoring, and manual accounting review still cost money. Managed OCR should be an opt-in fallback after counting scan pages in a pilot. As an **illustrative calculation, not a forecast for these 1,630 companies**, 50,000 scanned pages would cost about **$75** for AWS Textract text-only at $0.0015/page or **$750** for its table feature at $0.015/page in the cited US West (Oregon) examples, before other cloud/storage charges. Google lists Enterprise Document OCR at $1.50 per 1,000 pages after the first 1,000 free, with processor/plan details on its pricing page. Check current region and contract prices before purchase. [AWS pricing][12] · [Google pricing][13]

The better cost lever is **not sending born-digital filings through OCR**. SEC structured data, HTML and text-layer PDFs already carry searchable values; OCR can lose table structure or misread signs and decimals. OCRmyPDF's `skip` mode preserves pages with existing text. [OCRmyPDF modes][7]

## Source links

[1]: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
[2]: https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets
[3]: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
[4]: https://www.investor.gov/introduction-investing/getting-started/researching-investments/using-edgar-research-investments
[5]: https://www.sec.gov/resources-small-businesses/small-business-compliance-guides/amendments-smaller-reporting-company-definition
[6]: https://www.sec.gov/files/aqfsn_1.pdf
[7]: https://ocrmypdf.readthedocs.io/en/stable/advanced.html
[8]: https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html
[9]: https://www.sec.gov/file/form8-kpdf
[10]: https://storage.fasb.org/aop_fas95.pdf
[11]: https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-08-14.pdf
[12]: https://aws.amazon.com/textract/pricing/
[13]: https://cloud.google.com/document-ai/pricing
