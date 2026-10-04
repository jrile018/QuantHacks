# REIT document workflow audit

Audited 2026-10-03 against the local working tree. This report describes local code and offline behavior; it does not claim live collection, deployment, or measured OCR accuracy on REIT tables.

The authoritative code for this audit is in this shared checkout on `codex/options-export`: `scripts/collect_reit_financials.py`, `src/reit_cash_facts.py`, and `src/document_ocr.py`, with their focused tests. Changes from other chats were preserved. No commit, push, or deployment was performed for this audit.

**Verdict:** The inexpensive extraction order is appropriate: use structured financial data and original HTML, reuse digital PDF text, and reserve OCR for scanned or suspicious pages. The largest weaknesses were document selection and coverage. Those were improved during this audit. A complete automatic loan database still requires extracting and checking the original debt/loan tables and agreement terms.

The previous default used the 53 SIC 6798 CIKs in the Tiger export and began alphabetically. That export omits AMT, the REIT in `src/config.py`'s configured options universe. `configs/reit_pilot_companies.csv` now starts with AMT, followed by AAT, BXMT, and AGNC to test different disclosure patterns. Those comparison companies are not asserted to belong to the configured options universe. Issuer identities are supported by [AMT's SEC index](https://www.sec.gov/Archives/edgar/data/1053507/000105350726000133/0001053507-26-000133-index.htm), [AAT's index](https://www.sec.gov/Archives/edgar/data/1500217/0001500217-26-000012-index.htm), [BXMT's index](https://www.sec.gov/Archives/edgar/data/1061630/000106163026000069/0001061630-26-000069-index.html), and [AGNC's index](https://www.sec.gov/Archives/edgar/data/1423689/000142368926000099/0001423689-26-000099-index.htm).

**Evidence matrix**

| Capability | Previously claimed/intended | Evidence and verified state | Gap or action |
|---|---|---|---|
| Company selection | REIT companies associated with the options research | **done locally:** explicit pilot starts with AMT; input CIKs are normalized and deduplicated | Broad SIC screening still needs issuer/subtype verification; the 53-company CSV remains an optional input |
| Periodic financial statements | Recent filings provide cash-flow facts | **done locally:** newest original 10-K and 10-Q are reserved when the cap allows; regression tests cover newer unrelated 8-Ks | Current submissions history only; historical backfill is separate |
| Financing events and amendments | Loan/debt documents are available | **done locally:** relevant 8-K item selection; amendments remain separate evidence | Selection is bounded; a missing report is recorded, not treated as no activity |
| Agreement and supplemental exhibits | Primary filing text contains the needed detail | **done locally:** bounded SEC index discovery for EX-10, EX-4 and EX-99; distinct document paths | Exhibit caps can omit additional documents; investor-site-only supplements remain outside this collector |
| Repeat-run cost | Cache avoids repeated work | **done locally:** source hash, source identity, extraction revision and settings govern text reuse | Hashing remains necessary; dependency upgrades require a revision/settings change to force reprocessing |
| Financial facts | Selected cash/debt movement figures | **partial:** more standard monetary tags, separate flows and balance snapshots, original tags/units/periods, exact CompanyFacts response hash | Custom and dimensional loan/debt detail still needs filing extraction |
| Cash arithmetic | Matching reported components reconcile | **done locally:** accession/period/currency matching, separate cash bases and FX inclusion, explicit missing/conflicting facts, rounding bound only when precision is actually supplied | A numerical match is not validation of tagging, table meaning, or a transaction ledger |
| Hybrid PDFs | Native text means OCR is unnecessary | **partial:** sparse native text plus substantial image area triggers OCR; dense image-heavy pages receive review flags | Image rectangles are a heuristic; native text quantity cannot prove completeness |
| OCR quality and provenance | Per-page text/confidence/hash | **partial:** word coordinates, review flags, native/OCR overlap flag, effective resolution, engine versions and resource cleanup | Row/column associations and important amounts require source review or a tested table parser |
| Access failures | Requests stop on SEC denial | **done locally:** sticky 403/429 stop, atomic files, partial error manifest and requested/attempted/completed company counts | Sudden process termination can leave the previous summary snapshot; raw/text files remain individually atomic |
| Live accuracy and compute cost | Suitable for real REIT research | **not verifiable yet:** offline tests and primary-source format checks only | A real SEC contact email and a representative live pilot are still required |

A real example explains why exhibit coverage matters: AAT's April 2026 8-K index lists the credit agreement as EX-10.1 and the press release as EX-99.1. Reading only the primary 8-K misses the attached contract. The same filing has both the corporate REIT and its operating partnership as filers, which is why text artifacts now include CIK in their identity. [AAT filing index](https://www.sec.gov/Archives/edgar/data/1500217/0001500217-26-000012-index.htm)

**Why CompanyFacts is a first pass**

The SEC API aggregates standard-taxonomy facts applying to the entire issuer. It does not supply all custom or dimensional facts, so a missing API tag cannot establish that a loan or payment did not exist. Original debt notes, loan schedules and exhibits are retained as the next evidence source. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

Detail facts can overlap: debt issuance may appear as a broad total and as secured/unsecured categories; loan sales and collections may appear both jointly and separately. The collector preserves each reported tag and labels its amount kind and direction. It does not synthesize a total by adding all detail rows. New standard concepts were checked against the [FASB 2025 taxonomy schema](https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd). Historical cash tags are also retained for older reports.

Cash reconciliations distinguish totals including FX from totals excluding FX. An excluding-FX total can be checked against operating, investing and financing flows without inventing a zero FX figure. When FX is included but absent from the evidence, the check stays incomplete. Different cash bases are not paired with one another's FX tags. [XBRL US Data Quality Committee cash-flow guidance](https://github.com/DataQualityCommittee/documentation/blob/master/guidance/cashflows.md)

**Other optimization choices**

| Choice | Expected benefit | Added work/cost | Decision |
|---|---|---|---|
| Find filed agreements and supplements | Better loan and financing evidence | One small filing index plus bounded documents | Implemented |
| Reuse unchanged extraction | Removes repeat OCR and HTML parsing | Cheap source hashing and cache checks | Implemented |
| Crawl every one of the 15 URL sources | Broader discovery, potentially duplicate reports | More site-specific rules and repeated documents | Keep the 15 as a source guide; add investor-site supplements only to close a demonstrated gap |
| Parse filing XBRL/HTML tables for missing debt and loan details | Custom tags, dimensions, maturities, collateral and loan schedules | Moderate parser/evaluation work | Highest-value next implementation after the pilot identifies exact missing fields |
| Download all SEC bulk archives | Efficient for a large issuer corpus | Large downloads and storage | Use for a substantial backfill; per-CIK cached requests fit the current small pilot |
| Apply a paid table OCR service to every PDF | Table-aware output | Per-page fees, duplicate work on digital documents | Evaluate only flagged table pages against a checked sample |
| Train or fine-tune OCR | Possible specialized benefit | High compute and dataset effort | No evidence justifies it yet |

Tesseract documents limitations for tables without custom layout analysis. PDFium also does not provide document layout analysis merely by extracting text. This is why recognition confidence and preserved word boxes are diagnostics rather than proof of a correct loan schedule. [Tesseract quality guidance](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html), [pypdfium2 API](https://pypdfium2.readthedocs.io/en/stable/python_api.html)

AWS Textract and Azure Document Intelligence provide table structure, but vendor features alone do not establish which engine is most accurate for these documents. A small comparison on flagged pages would measure amount/sign/unit/period accuracy and row association before selecting a paid fallback. [Textract tables](https://docs.aws.amazon.com/textract/latest/dg/how-it-works-tables.html), [Azure layout analysis](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)

Separate concurrent work has added an optional local GLM OCR backend and a finite-manifest batch runner (`src/glm_document_ocr.py`, `scripts/run_document_batch.py`). The GLM backend requires CUDA and a pinned model revision; it is not connected to the REIT collector. Its shared text output and the transcript adapter's table candidates do not establish correct table structure. Real model execution, environment provisioning and REIT amount/table accuracy remain unverified in this audit. This is a possible later fallback, not evidence that a GPU run improves the current workflow. Native extraction and selective Tesseract remain the collector's current inexpensive path.

**Next verification:** use the four pilot issuer types, manually check a small set of debt/loan tables and reported cash flows, and record field accuracy, omissions, processing time and pages requiring OCR. Twenty to thirty representative pages are a practical initial evaluation design, not an established accuracy benchmark. Use timestamped output directories when preserving successive research snapshots. Public reports provide material disclosed activity and selected loans; they cannot guarantee every company bank transfer.

The default remains one company, four primary filings, and at most two selected exhibits per filing: at most 12 documents per company. SEC metadata refreshes after 24 hours; unmodified extracted documents are reused. Requests default to two per second, below the SEC's stated ten-request ceiling. No cloud OCR, training, bulk backfill, or recurring job was started during the audit. [SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

**Verification:** all 42 focused REIT tests passed (16 collection, 11 facts, 15 OCR); the three modules compiled, collector CLI help ran, and `git diff --check` passed. Independent review found no remaining Critical/Important issue in these changes. The wider shared-workspace unittest discovery ran 130 tests and reported three errors in separate concurrent work: two imports require unavailable `pytest`, and one options-learning test raised `IndexError`. Those components were not changed to satisfy this audit. Offline regression results demonstrate tested behavior, not live SEC coverage or financial-table accuracy.

## Step 3 continuation

The user subsequently authorized deep research and improvement of money-record organization before a live pilot. A separate offline analyzer now preserves filing-level numeric contexts, table structure and source-linked review candidates. See [the research and implementation report](reit-money-extraction-research.md) and [the design](superpowers/specs/2026-10-03-reit-money-records-design.md). This improves local extraction; interpreting every loan term, PDF table structure and real-document accuracy still requires further implementation/evaluation.

## PDF meaning fix and live extension

The subsequent authorized interpretation fix correctly classifies 14/14 unchanged sampled PDF assertions automatically, separating period cash movement, debt balances, facility commitments, unused capacity and conditional expansions. Currency context is sourced separately. A four-issuer SEC collection completed with 35 documents and 187 CompanyFacts observations; broader analysis remains partial. The [updated real-filing report](reit-real-filing-pilot.md) records exact outputs, review findings and remaining limits. This continuation assumes OCR works and does not audit OCR.
