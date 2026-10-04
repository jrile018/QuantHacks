# REIT-labeled issuers in the 8-K universe

Snapshot: 2026-10-03. Source: `data/processed/tiger_8k_company_sectors.csv`.
The filter is SEC SIC `6798` (Real Estate Investment Trusts), joined by CIK.
It finds **53 filers**, of which **39 have at least one ticker string** in the
export and **14 have none**. The 53 account for **69 8-K rows** in the local
event export. SIC is a filer classification, not proof of a current REIT tax
election, common-share listing, option listing, or market liquidity. Ticker
strings can include preferred shares and historical symbols.

## What the local options data supports

The saved Massive cache has 8-K disclosure records for these 53 CIKs, but its
only saved option-chain underlying is **GD**. The 744-row
`data/processed/options_expiration_inventory.csv` is also entirely GD. There
are **no saved REIT option contracts or option bars** here with which to score
these issuers' option liquidity, implied volatility, or option returns.
This is a source inventory and issuer filter, not a REIT options backtest.

## Where to find the financial information

1. Open the issuer's SEC link in the table below and filter for **10-K**. In
   Item 8, read the independent auditor's report, audited statements, notes,
   and, where applicable, the real estate and accumulated depreciation
   **Schedule III** in Item 15. A filing may be HTML/iXBRL rather than PDF.
2. Filter for **10-Q** for interim statements and debt, lease, occupancy, or
   impairment updates. These statements are unaudited, although the interim
   information is generally reviewed by an independent accountant.
3. Filter for **8-K** and open the filing's **Documents** list to locate
   attached EX-99 earnings releases, investor presentations, and other
   exhibits. Those materials can include property tables and FFO/AFFO
   reconciliations; they are not automatically audited.
4. For machine-readable data use SEC
   [Submissions](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
   for accession and document names, and Company Facts for standardized XBRL
   facts. The [SEC Financial Statement and Notes Data Sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets)
   have custom tags and dimensional detail that Company Facts can omit.
   Preserve the accession, filing/acceptance time, fiscal period, unit, and
   amendment/restatement status of every extracted value.
5. If a PDF is preferred, check the exact accession's Documents list or the
   issuer's investor-relations annual reports. Do not assume every 10-K has a
   PDF. A PDF annual report may be filed later as an exhibit or shareholder
   report and should be linked back to the SEC filing it represents.

**Verified examples from this 53-issuer list:** [Sterling Real Estate Trust's
2025 10-K](https://www.sec.gov/Archives/edgar/data/1412502/000110465926026323/sret-20251231x10k.htm)
contains the auditor's report and Schedule III; [EastGroup Properties' 2025
annual-report PDF](https://www.sec.gov/Archives/edgar/data/49600/000004960026000021/annualreport2025.pdf)
contains Schedule III; [Cherry Hill Mortgage Investment's filed annual-report
PDF](https://www.sec.gov/Archives/edgar/data/1571776/000114036126015898/ny20070031x3_ars.pdf)
illustrates that a mortgage REIT's assets and risks differ from a property
owner's. These examples do not verify a particular annual report for every row
below.

## How to read a REIT's audit and operating direction

- **Audit scope:** A 10-K has audited GAAP statements and an independent
  registered public accounting firm's report. Read the opinion, any critical
  audit matters, internal-control opinion if present, the notes, and debt and
  impairment assumptions. A 10-Q is an interim review, not an annual audit.
- **Equity/property REITs:** Track occupancy, rents, lease expirations,
  same-property NOI, development and maintenance capex, acquisitions and
  dispositions, interest expense, debt maturities, covenant headroom, and
  Schedule III's property cost/depreciation details where applicable. FFO is
  supplemental to GAAP income; AFFO definitions vary by issuer. Do not treat
  either as cash flow or as automatically audited.
- **Mortgage/credit REITs:** Focus on loan or mortgage-asset composition,
  credit allowances, fair value marks, funding and repo maturities, leverage,
  hedges, net interest spread, and book value. A property-owner occupancy
  model does not map cleanly to a mortgage lender.
- **REIT status:** IRS Form 1120-REIT is a tax return, not a routine public
  SEC filing. Verify the company's stated REIT election and any qualification
  risk in its own 10-K; SIC alone is insufficient.
- **For options research:** Join the CIK to a dated common-stock ticker and
  dated option root. Record the signal's public release time, then test only
  contracts that existed and had usable quotes at entry. Compare expected
  catalysts and the move priced by the option, rather than interpreting a
  strong balance sheet as an automatic long-call signal.

The [SEC investor guide](https://www.investor.gov/introduction-investing/getting-started/researching-investments/using-edgar-research-investments)
explains 10-K and 10-Q audit status. The
[PCAOB commercial real estate audit report](https://pcaobus.org/news-events/news-releases/news-release-detail/pcaob-staff-report-highlights-important-auditing-considerations-related-to-commercial-real-estate)
highlights impairment, credit losses, going concern, and interim review risk.
[Nareit defines FFO](https://www.reit.com/glossary/funds-operation-ffo) and
[notes that AFFO is not standardized](https://www.reit.com/glossary/adjusted-funds-operations-affo).

## Basic APIs to add beside SEC and your Massive options data

| Source | REIT use | Access and backtest caution |
| --- | --- | --- |
| [FRED / ALFRED](https://fred.stlouisfed.org/docs/api/fred/) | Treasury yields, policy rates, mortgage rates, credit spreads, property-market indicators | Free API key. Use ALFRED vintages and release dates so a historical trade sees only the value then published. |
| [BLS Public Data API](https://www.bls.gov/developers/home.htm) | Local employment and wages around each property's markets | Unregistered v1 is limited; registered v2 provides higher limits. These are metro/industry signals, not issuer revenue. |
| [Census Economic Indicators API](https://api.census.gov/data/timeseries.html) | Retail sales, construction, housing and trade activity relevant to retail, residential and industrial properties | Join by property type/geography and publication date; national totals may be too broad for a local portfolio. |
| [EIA Open Data](https://www.eia.gov/opendata/) | Electricity, natural gas and petroleum costs for data centers, industrial and other energy-intensive properties | Free API key; sector relevance depends on lease terms and who bears utility costs. |
| [Alpha Vantage earnings calendar](https://www.alphavantage.co/documentation/) | Expected earnings dates for event windows | Key required; standard free usage is [25 requests/day](https://www.alphavantage.co/support/). Calendar dates can move, so retain each historical snapshot. |

The filings and these APIs describe disclosed company facts or outside
conditions. They do not expose private rent rolls, appraisals, borrower files,
or audit workpapers. For trading, test whether any added signal improves a
point-in-time baseline beyond the option premium, spread, and event calendar.

## All 53 SIC 6798 filers

The SEC links are issuer landing pages constructed from the CIK in the local
export. They let you retrieve each company's actual filings and document
lists; no claim is made that every issuer has a PDF or current listed options.

| Company | CIK / SEC filings | Ticker strings in export | 8-K rows |
| --- | --- | --- | ---: |
| Alpine Income Property Trust, Inc. | [0001786117](https://www.sec.gov/edgar/browse/?CIK=0001786117&owner=exclude) | PINE | 2 |
| American Strategic Investment Co. | [0001595527](https://www.sec.gov/edgar/browse/?CIK=0001595527&owner=exclude) | NYC | 1 |
| Americold Realty Trust | [0001455863](https://www.sec.gov/edgar/browse/?CIK=0001455863&owner=exclude) | COLD | 1 |
| Apollo Realty Income Solutions, Inc. | [0001882850](https://www.sec.gov/edgar/browse/?CIK=0001882850&owner=exclude) | — | 1 |
| ARES INDUSTRIAL REAL ESTATE INCOME TRUST Inc. | [0001625941](https://www.sec.gov/edgar/browse/?CIK=0001625941&owner=exclude) | — | 1 |
| Brt Apartments Corp. | [0000014846](https://www.sec.gov/edgar/browse/?CIK=0000014846&owner=exclude) | BRT | 1 |
| Cantor Fitzgerald Income Trust, Inc. | [0001666244](https://www.sec.gov/edgar/browse/?CIK=0001666244&owner=exclude) | — | 1 |
| Cherry Hill Mortgage Investment Corp | [0001571776](https://www.sec.gov/edgar/browse/?CIK=0001571776&owner=exclude) | CHMI; CHMIpA; CHMIpB | 1 |
| Creative Media & Community Trust Corp | [0000908311](https://www.sec.gov/edgar/browse/?CIK=0000908311&owner=exclude) | CMCT | 1 |
| Crown Castle Inc. | [0001051470](https://www.sec.gov/edgar/browse/?CIK=0001051470&owner=exclude) | CCI | 2 |
| Cto Realty Growth, Inc. | [0000023795](https://www.sec.gov/edgar/browse/?CIK=0000023795&owner=exclude) | CTO; CTOpA | 2 |
| Diamondrock Hospitality Co | [0001298946](https://www.sec.gov/edgar/browse/?CIK=0001298946&owner=exclude) | DRH; DRHpA | 1 |
| Eastgroup Properties Inc | [0000049600](https://www.sec.gov/edgar/browse/?CIK=0000049600&owner=exclude) | EGP | 1 |
| Equity Residential | [0000906107](https://www.sec.gov/edgar/browse/?CIK=0000906107&owner=exclude) | EQR | 1 |
| Essential Properties Realty Trust, Inc. | [0001728951](https://www.sec.gov/edgar/browse/?CIK=0001728951&owner=exclude) | EPRT | 1 |
| Extra Space Storage Inc. | [0001289490](https://www.sec.gov/edgar/browse/?CIK=0001289490&owner=exclude) | EXR | 1 |
| Farmland Partners Inc. | [0001591670](https://www.sec.gov/edgar/browse/?CIK=0001591670&owner=exclude) | FPI | 1 |
| Four Corners Property Trust, Inc. | [0001650132](https://www.sec.gov/edgar/browse/?CIK=0001650132&owner=exclude) | FCPT | 2 |
| Frontview Reit, Inc. | [0001988494](https://www.sec.gov/edgar/browse/?CIK=0001988494&owner=exclude) | FVR | 2 |
| Fs Credit Real Estate Income Trust, Inc. | [0001690536](https://www.sec.gov/edgar/browse/?CIK=0001690536&owner=exclude) | — | 1 |
| Granite Point Mortgage Trust Inc. | [0001703644](https://www.sec.gov/edgar/browse/?CIK=0001703644&owner=exclude) | GPMT; GPMTpA | 1 |
| Healthcare Realty Trust Inc | [0001360604](https://www.sec.gov/edgar/browse/?CIK=0001360604&owner=exclude) | HR | 2 |
| Healthpeak Properties, Inc. | [0000765880](https://www.sec.gov/edgar/browse/?CIK=0000765880&owner=exclude) | DOC; PEAK | 1 |
| Hg Holdings, Inc. | [0000797465](https://www.sec.gov/edgar/browse/?CIK=0000797465&owner=exclude) | — | 1 |
| Inland Real Estate Income Trust, Inc. | [0001528985](https://www.sec.gov/edgar/browse/?CIK=0001528985&owner=exclude) | — | 1 |
| Invesco Commercial Real Estate Finance Trust, Inc. | [0001976927](https://www.sec.gov/edgar/browse/?CIK=0001976927&owner=exclude) | — | 1 |
| Invesco Mortgage Capital Inc. | [0001437071](https://www.sec.gov/edgar/browse/?CIK=0001437071&owner=exclude) | IVR; IVRpB; IVRpC | 2 |
| Kilroy Realty Corp | [0001025996](https://www.sec.gov/edgar/browse/?CIK=0001025996&owner=exclude) | KRC | 1 |
| Lineage, Inc. | [0001868159](https://www.sec.gov/edgar/browse/?CIK=0001868159&owner=exclude) | LINE | 1 |
| Ltc Properties Inc | [0000887905](https://www.sec.gov/edgar/browse/?CIK=0000887905&owner=exclude) | LTC | 1 |
| Lxp Industrial Trust | [0000910108](https://www.sec.gov/edgar/browse/?CIK=0000910108&owner=exclude) | LXP; LXPpC | 2 |
| Macerich Co | [0000912242](https://www.sec.gov/edgar/browse/?CIK=0000912242&owner=exclude) | MAC | 1 |
| Nexpoint Diversified Real Estate Trust | [0001356115](https://www.sec.gov/edgar/browse/?CIK=0001356115&owner=exclude) | NXDT; NXDTpA | 1 |
| Nexpoint Real Estate Finance, Inc. | [0001786248](https://www.sec.gov/edgar/browse/?CIK=0001786248&owner=exclude) | NREF; NREFpA | 2 |
| Nexpoint Residential Trust, Inc. | [0001620393](https://www.sec.gov/edgar/browse/?CIK=0001620393&owner=exclude) | NXRT | 2 |
| Nnn Reit, Inc. | [0000751364](https://www.sec.gov/edgar/browse/?CIK=0000751364&owner=exclude) | NNN | 1 |
| Nuveen Global Cities REIT, Inc. | [0001711799](https://www.sec.gov/edgar/browse/?CIK=0001711799&owner=exclude) | — | 1 |
| Postal Realty Trust, Inc. | [0001759774](https://www.sec.gov/edgar/browse/?CIK=0001759774&owner=exclude) | PSTL | 2 |
| Rexford Industrial Realty, Inc. | [0001571283](https://www.sec.gov/edgar/browse/?CIK=0001571283&owner=exclude) | REXR; REXRpB; REXRpC | 1 |
| Rithm Property Trust Inc. | [0001614806](https://www.sec.gov/edgar/browse/?CIK=0001614806&owner=exclude) | AJX; RPT; RPTpC | 1 |
| Rlj Lodging Trust | [0001511337](https://www.sec.gov/edgar/browse/?CIK=0001511337&owner=exclude) | RLJ; RLJpA | 1 |
| Sachem Capital Corp. | [0001682220](https://www.sec.gov/edgar/browse/?CIK=0001682220&owner=exclude) | SACC; SACH; SACHpA; SCCB; SCCC; SCCD; SCCE; SCCF; SCCG | 2 |
| Sculptor Diversified Real Estate Income Trust, Inc. | [0001914496](https://www.sec.gov/edgar/browse/?CIK=0001914496&owner=exclude) | — | 2 |
| Selectis Health, Inc. | [0000727346](https://www.sec.gov/edgar/browse/?CIK=0000727346&owner=exclude) | — | 1 |
| Seven Hills Realty Trust | [0001452477](https://www.sec.gov/edgar/browse/?CIK=0001452477&owner=exclude) | SEVN | 1 |
| Site Centers Corp. | [0000894315](https://www.sec.gov/edgar/browse/?CIK=0000894315&owner=exclude) | SITC; SITCpA | 1 |
| Sterling Real Estate Trust | [0001412502](https://www.sec.gov/edgar/browse/?CIK=0001412502&owner=exclude) | — | 3 |
| STORE CAPITAL LLC | [0001538990](https://www.sec.gov/edgar/browse/?CIK=0001538990&owner=exclude) | — | 1 |
| Summit Healthcare REIT, Inc | [0001310383](https://www.sec.gov/edgar/browse/?CIK=0001310383&owner=exclude) | — | 1 |
| Sun Communities Inc | [0000912593](https://www.sec.gov/edgar/browse/?CIK=0000912593&owner=exclude) | SUI | 1 |
| Tpg Re Finance Trust, Inc. | [0001630472](https://www.sec.gov/edgar/browse/?CIK=0001630472&owner=exclude) | TRTX; TRTXpC | 1 |
| Two Harbors Investment Corp. | [0001465740](https://www.sec.gov/edgar/browse/?CIK=0001465740&owner=exclude) | TWO; TWOpA; TWOpB; TWOpC | 2 |
| VINEBROOK HOMES TRUST, INC. | [0001755755](https://www.sec.gov/edgar/browse/?CIK=0001755755&owner=exclude) | — | 1 |
