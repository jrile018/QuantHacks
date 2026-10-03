# Industry breakdown of the Tiger 8-K company universe

**Snapshot:** October 3, 2026. **Universe:** 1,630 distinct SEC CIKs in the local Tiger 8-K company export. These are the filers in this study, not a sample of every public company. Each CIK counts once, regardless of how many 8-Ks it filed.

## Main finding

**Manufacturing is the largest broad industry group: 689 of 1,630 filers (42.27%).** This older SIC category includes pharmaceutical products, biological products, medical instruments, semiconductors, and many other types of products. It should not be read as only heavy industry or factories. Services is next (19.51%), followed by finance, insurance, and real estate (17.42%).

The largest *specific* SIC industry is **pharmaceutical preparations** (147 filers, 9.02% of the universe). Prepackaged software follows with 80 (4.91%), then biological products with 59 (3.62%).

## Broad industry split

The categories below use the divisions of the [Standard Industrial Classification (SIC) Manual][sic-manual]. The examples explain what each division covers; they are not separate counts. Percentages use **all 1,630 CIKs** as the denominator, including those without a verified SIC code.

| Broad industry (SIC range) | Plain-language meaning and examples | Filers | Share |
| --- | --- | ---: | ---: |
| **Manufacturing (20–39)** | Makes physical or chemical products; includes drugs, medical devices, electronics, food, machinery, and vehicles | **689** | **42.27%** |
| Services (70–89) | Provides software, business, professional, health, entertainment, or other services | 318 | 19.51% |
| Finance, insurance & real estate (60–67) | Banks, lenders, brokers, insurers, property businesses, REITs, and investment/holding companies | 284 | 17.42% |
| Retail trade (52–59) | Sells to end customers; includes stores and restaurants | 92 | 5.64% |
| Transportation, communications & utilities (40–49) | Carriers, telecom and media networks, and utility providers | 85 | 5.21% |
| Mining, oil & gas (10–14) | Extracts minerals, crude oil, or natural gas | 60 | 3.68% |
| **Unknown / unclassified** | No verified SIC code in the metadata snapshot | **34** | **2.09%** |
| Wholesale trade (50–51) | Distributes goods mainly to other businesses | 31 | 1.90% |
| Construction (15–17) | Building and specialty contracting | 23 | 1.41% |
| Agriculture, forestry & fishing (01–09) | Farms, forestry, fishing, and related activities | 14 | 0.86% |
| **Total** | One row per distinct CIK | **1,630** | **100% before rounding** |

The displayed percentages add to 99.99% because each row is rounded to two decimal places.

## Largest specific industries

These are four-digit SIC industries inside the broad groups above. They illustrate what drives the totals; this list is not an additional set of companies to add to the broad-sector table.

| SIC | Industry | Filers | Share of all 1,630 |
| --- | --- | ---: | ---: |
| 2834 | Pharmaceutical preparations | 147 | 9.02% |
| 7372 | Prepackaged software | 80 | 4.91% |
| 2836 | Biological products, excluding diagnostic substances | 59 | 3.62% |
| 6798 | Real estate investment trusts (REITs) | 53 | 3.25% |
| 3841 | Surgical and medical instruments | 41 | 2.52% |
| 6022 | State commercial banks | 39 | 2.39% |
| 7389 | Other business services | 31 | 1.90% |
| 6021 | National commercial banks | 26 | 1.60% |
| 6199 | Other finance services | 25 | 1.53% |
| 1311 | Crude petroleum and natural gas | 24 | 1.47% |

The three product categories **2834, 2836, and 3841** contain 247 filers combined (15.15% of all 1,630). This is a useful illustration of health-related manufacturing, **not** a complete count of the healthcare sector: hospitals, medical services, diagnostics, and other health businesses have different SIC codes.

## What the terms and numbers mean

- **CIK:** the SEC's persistent identifier for a filer. We joined by CIK, not ticker, because tickers can change, disappear, or be reused.
- **SIC:** an industry code for the filer's primary activity. A diversified company can serve several markets even though this report places it in one SIC group. The SEC's [Submissions API][sec-api] provides SIC metadata for individual filers.
- **Sector / broad industry:** our plain-language label for an SIC *division*. This is **not** a GICS or modern stock-market sector classification. For example, software is in SIC Services, while pharmaceuticals are in SIC Manufacturing.
- **Filers:** distinct CIKs, not number of 8-K filings, customers, employees, or subsidiaries.
- **Share:** `filers in group / 1,630 × 100`. For Manufacturing, `689 / 1,630 × 100 = 42.27%`.

These are **company-count shares**. They do not say what proportion of sales, profit, employment, market value, or option activity belongs to each group. Nor do they identify the customer industries a company serves.

## Data and reproducibility

1. The denominator comes from the local Tiger 8-K export, `data/processed/tiger_8k_companies.csv`, which had 1,630 unique CIKs. The export is ignored by Git along with downloaded study data; this Markdown report records the aggregate snapshot.
2. SEC-derived filer metadata came from the public [Datamule listed and unlisted filer files][metadata], pinned to commit [`7e5587b50f6dba3045f9e03a03b5a44339555e00`][metadata-commit] (committed October 2, 2026). The files provide `cik`, `sic`, and `sicDescription`. An exact CIK join produced 1,375 matches from the listed file and 221 more from the unlisted file: **1,596 classified; 34 unclassified**. The large unlisted file was streamed, retaining only matching CIKs.
3. Each matched four-digit SIC was assigned to the [SIC Manual division][sic-manual] shown in the table. Missing SIC values stayed Unknown. We counted distinct CIKs, then divided every count by 1,630.
4. Display names in the local company list were joined separately by CIK: 1,517 from a [current SEC-derived ticker mapping][current-names] and 113 from an [October 2025 CIK archive][archived-names]. The industry counts depend on CIK and SIC, not on name or ticker matching. Older names can differ from a filer's current legal name.

The local detail exports are `data/processed/tiger_8k_company_sectors.csv` (one row per CIK) and `data/processed/tiger_8k_sector_split.csv` (the broad split). The SIC metadata snapshot is dated October 2, 2026; it may not equal each company's classification **at the date of its 2024–2026 filing**. Rebuild a historical sector analysis with filing-date SIC histories if that distinction matters for backtests.

[sic-manual]: https://www.osha.gov/data/sic-manual
[sec-api]: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
[metadata]: https://github.com/john-friedman/datamule-data/tree/7e5587b50f6dba3045f9e03a03b5a44339555e00/data/filer_metadata
[metadata-commit]: https://github.com/john-friedman/datamule-data/commit/7e5587b50f6dba3045f9e03a03b5a44339555e00
[current-names]: https://github.com/jadchaar/sec-cik-mapper/tree/main/mappings/stocks
[archived-names]: https://github.com/GTocchi/edgar-cik-api
