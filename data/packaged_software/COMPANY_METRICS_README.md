# SEC financial metrics and AI/cloud disclosure evidence, since 2022

This pipeline uses **real SEC Company Facts API responses and SEC filings** for
all entries in `packaged_software_companies.csv`. The first extraction reuses the
168 cached Company Facts responses and downloaded filings beginning January 2022.
There are no simulated financial amounts, inferred cloud bills or estimated AI
contract values. The live SEC API was also verified with the configured contact
header.

## Credentials and dependencies

| Source | Configuration | Purpose |
| --- | --- | --- |
| SEC Company Facts and submissions APIs / EDGAR archives | `SEC_USER_AGENT=Your Name actual-contact@example.com` | Required contact header for downloads; **not an API key**. Already configured in `.env`. |
| Massive News API | Existing `MASSIVE_API_KEY` | Historical news titles, summaries, publishers, links and publication timestamps. Your existing key successfully returned a January 2022 article. |
| FIRST EPSS | None | The separate `extract_epss.py` fetches actual dated vulnerability scores. |
| NVD | Optional `NVD_API_KEY` | Faster CVE mapping for the EPSS extractor; not needed for financial metrics. |
| Census | Existing `CENSUS_API_KEY` | Used by the separate industry extractor, not company cloud/AI spending. |

Both SEC scripts load `SEC_USER_AGENT` from `.env`, with environment variables
taking precedence. No additions to `requirements.txt` are required: the new code
uses Python's standard library.

No additional provider account or key is required for this extraction. SEC data
needs no subscription; the news extractor uses your existing Massive access.
Massive's 2022 news requires historical entitlement (the Basic plan's documented
window is two years); your key's 2022 access was verified live.
**HG Insights projections are not
historical actual spending**, so they are not included in the 2022 backfill.
Commercial XBRL/news APIs could add convenience or additional source coverage,
but a key does not make undisclosed costs public. No `HG_API_KEY`, `SEC_API_KEY`
or OpenAI key is consumed by this pipeline.

## Run from the repository root

```powershell
# Use the genuine SEC data already downloaded, with no network requests.
python data/packaged_software/extract_company_metrics.py --offline

# Process the cache and fetch any missing Company Facts responses.
python data/packaged_software/extract_company_metrics.py --start 2022-01-01

# Add real news API records and announcement candidates from 2022 onward.
python data/packaged_software/extract_ticker_aliases.py
python data/packaged_software/extract_company_news.py --start 2022-01-01

# Verify the existing Massive key can actually retrieve the historical year.
python data/packaged_software/extract_company_news.py --check-api

# Check .env against the live public Company Facts API, without logging the header.
python data/packaged_software/extract_company_metrics.py --check-api

# Refresh the filing index and download missing documents before rerunning metrics.
# Adding linked exhibits expands press-release and contract coverage and can be slow.
python data/packaged_software/extract_sec_filings.py --start 2022-01-01 --with-exhibits --refresh-facts
python data/packaged_software/extract_company_metrics.py --start 2022-01-01
```

Both extractors accept `--end YYYY-MM-DD`. Their default end is the current date.
The existing SEC downloader includes foreign-report forms (20-F, 40-F, 6-K and
amendments); the metrics extractor currently harmonizes only USD us-gaap facts.
The downloader skips cached documents, limits SEC requests and follows older
submissions pages so a recent-only API response doesn't cut off 2022 history.
`--with-exhibits` downloads recognizable linked Ex. 99 / Ex. 10 HTML/text files;
it does not guarantee every exhibit, PDF attachment or non-SEC press release.

## Output: `data/extracts/company_metrics/`

- `reported_financial_facts.csv`: source-reported standard-tag values, units,
  period starts/ends, filing dates, accession numbers, unique fact IDs and links.
  Multiple filings/restatements are retained. Facts from before 2022 are included
  only when required as explicit context for 2022 TTM or YoY calculations.
- `fundamentals_quarterly.csv`: discrete-quarter and TTM metrics and ratios,
  from period ends on/after January 1, 2022 through `--end`.
- `quarterly_metric_sources.csv`: exact source fact IDs, derivation methods,
  availability dates and accounting-basis warnings for quarterly/TTM values.
- `financial_coverage.csv`: one row per company/metric, including missing tags,
  source-fact counts, observed dates and output-quarter coverage.
- `filing_tagged_asset_and_cloud_facts.csv`: standard/custom inline XBRL facts
  mentioning land, buildings, equipment, hardware, software, hosting or cloud.
  Original tags, dimensions, units, periods, numeric scales and filing links are
  preserved. These are tagged disclosures; their business interpretation needs
  review before being added to standardized company totals. Unsupported numeric
  transformations remain blank with a reason rather than being guessed.
- `disclosure_evidence.csv`: bounded passages about employee AI adoption,
  AI partnerships, cloud costs/commitments and hardware/land disclosures.
  Every passage has a filing link/date and `unreviewed_text_candidate` status.
  Risk/policy language is separated when detected. Company role in partnerships
  remains unresolved. Numeric mentions are separate unvalidated strings:
  `amount_usd` and `employee_seats` remain blank until verified. Exact repeated
  excerpts are deduplicated; similar paraphrases still need event-level review.
- `disclosure_coverage.csv`: all companies, documents/exhibits scanned, missing
  documents, candidate counts and explicit scan scope.
- `unresolved.csv`: any fetch or parsing failures.
- `manifest.json`: range, counts, API URLs, cache hashes and limitations.

## Additional output: `data/extracts/company_news/`

`extract_company_news.py` retrieves actual Massive News API records beginning
January 2022, follows every pagination URL, caches sanitized API responses and
deduplicates article IDs within each company. `news_articles.csv` retains title,
summary, publisher, source URL and UTC publication time. The filtered
`news_announcement_candidates.csv` finds AI agreement/deployment and cloud/asset
announcements; these are **unreviewed metadata candidates**, not contract values,
confirmed employee usage or directional trading signals. `news_coverage.csv` and
the manifest include all 168 companies and any missing provider access.

`extract_ticker_aliases.py` records `dei:TradingSymbol` values actually present in
the companies' SEC filings. `news_ticker_aliases.csv` keeps the CIK, symbol,
observed filing dates and source URL. News queries include these observed symbols
as well as the current ticker (e.g. SQ/XYZ and NLOK/GEN), and record the queried
symbol and its evidence. Exact active-date intervals are **not established** by
these observations: ticker reuse, share classes, SPAC predecessors and entity
changes require review. Company attribution is an article/ticker association,
not proof that the company was the buyer or deployed AI internally. Publication
timestamps and historical metadata are not a complete archive of article revisions.
Do not assume the requested start equals the first available article for every
company. The existing key was verified against an actual January 2022 API record.

## Metric definitions and missingness

R&D, sales/marketing, revenue, operating income, cash flow, stock compensation,
physical asset purchases, broader productive-asset purchases, software cash
payments, capitalized software additions, acquisitions and amortization are kept
distinct. Balance metrics include assets, goodwill, PP&E, land, machinery,
buildings, lease assets, capitalized software, hosting implementation costs,
deferred revenue, RPO and purchase obligations.

Missing is always blank, never zero. A company without a separate hardware/cloud
amount isn't assumed to spend nothing. PP&E balances are **not purchases**;
purchase commitments are **not quarterly spending**. Machinery can include more
than computing hardware. Hosting implementation assets are **not cloud bills**.
Purchase obligations can include multiple vendors/services and must not be
relabeled as AI/cloud contracts without supporting disclosure.

`PaymentsToAcquireProductiveAssets` includes software/intangibles, so it is not
used as a physical-capex fallback. Capitalized-software additions are an accrual
concept and are not equated with software-development cash payments.
`fcf_physical_capex_margin` is (TTM operating cash flow - TTM physical-asset cash
purchases) / TTM revenue and is blank if either cash input is missing. This is a
named convention; it does not subtract unidentified software spending or purport
to match every company's adjusted FCF definition. The previous mixed-quarter
"Rule of 40" and ambiguous capitalization-share ratios are not generated.

## Historical availability

This is historical disclosure extraction, not creation of backdated information.
Period end, filing date and conservative availability date are separate fields.
Availability is the calendar day after the latest filing used; exact SEC
acceptance timestamps are retained by refreshed filing indexes but are not yet
used for intraday alignment. Filter on availability before using a feature.

The earliest filed eligible fact is chosen across candidate tags, with tag priority
only breaking ties. Same-accession cumulative values are used for quarter
differencing where available; otherwise a cross-filing difference is explicitly
flagged `cross_filing_basis_unverified`. Annual-minus-three-quarter Q4 values are
also flagged. TTM requires four contiguous quarters with compatible start/end
dates. Strict research can exclude rows marked
`contains_cross_filing_basis_unverified` or use only direct source facts. Values
and aggregate ratios containing such derivations are not fully verified against
restatement bases.

The current 168-company universe has survivorship/ownership-history limitations.
A newly public company may have no disclosed 2022 quarter; no artificial row is
invented. A contract described in a later filing is not dated back to its claimed
signing date. Likewise, the first occurrence in scanned filings is not necessarily
the first public press announcement. Generic partnership language does not prove
employee deployment, paid seats or active usage. Public SEC data cannot supply a
complete historical bill-by-vendor dataset for every company.

EPSS remains in `data/extracts/epss_monthly/`; it uses actual dated FIRST snapshots
and has its own CVE/company mapping coverage and unavailable-date manifest. It
is not silently merged into quarterly financial records. The Census industry
and USAspending datasets remain separate: industry totals and government awards
are not substitutes for a company's cloud purchases or AI adoption.

Sources: [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[Massive News API](https://massive.com/docs/rest/stocks/news),
[SEC developer guidance](https://www.sec.gov/about/developer-resources),
[FIRST EPSS](https://api.first.org/epss/),
[HG spend field definitions](https://data-docs.hginsights.com/v2/guides/understanding-hg-data).
