# Company financial source catalog

## Scope and status

The requested universe is `data/processed/tiger_8k_company_names.csv` (1,630 CIKs).
CIK is the stable issuer key; names and tickers in the input can change. This
document records the source plan and URL rules. It is **not** evidence that each
filing or PDF has been retrieved or that the 1,630 company folders are complete.

The generated catalog belongs in `data/financial_research/` and should keep
each issuer's original CIK, company name, source URL, document format, form,
accession, filing date, and verification status. A source should never be
presented as a verified PDF merely because a URL can be constructed.

## Where to read a company's financials

| Source | What it answers | URL rule |
| --- | --- | --- |
| EDGAR company page | The issuer's complete public filing history and current identity | `https://www.sec.gov/edgar/browse/?CIK={cik10}&owner=exclude` |
| Submissions JSON | Filing form, accession, dates, primary document and older submission-history file names | `https://data.sec.gov/submissions/CIK{cik10}.json` |
| Company Facts JSON | Standard-taxonomy, entity-wide reported XBRL facts across filings | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json` |
| Filing index | Exact filed document list, including any PDFs and exhibits | `https://www.sec.gov/Archives/edgar/data/{cik_integer}/{accession_no_dashes}/{accession}-index.html` |
| Filing directory JSON | Machine-readable names and formats of files in an accession | `https://www.sec.gov/Archives/edgar/data/{cik_integer}/{accession_no_dashes}/index.json` |
| Filing complete text | Full submitted filing including header and documents | `https://www.sec.gov/Archives/edgar/data/{cik_integer}/{accession_no_dashes}/{accession}.txt` |
| Filing primary document | Annual/quarterly/current report as actually filed; often HTML, not PDF | Filename comes from Submissions JSON; append to the filing directory |
| SEC Financial Statement and Notes Data Sets | Custom XBRL tags, dimensional facts, statement presentation/calculation, and note text | `https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets` |

The [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
explains Submissions and Company Facts, including older-history files and bulk
ZIP archives. The [EDGAR access guide](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
documents archive paths and asks automated clients to declare a contact in
their User-Agent. The [Financial Statement and Notes Data Sets guide (PDF)](https://www.sec.gov/files/aqfsn_1.pdf)
defines the detailed `SUB`, `TAG`, `DIM`, `NUM`, `TXT`, `REN`, `PRE`, and `CAL`
tables. Dataset rows are as filed and should be checked against the original
filing.

### Filing priority

1. **Annual:** 10-K/10-K/A, 20-F/20-F/A, 40-F/40-F/A. Read audited financial
   statements, notes, MD&A, segment disclosures, auditor opinion, and risks.
2. **Interim:** 10-Q/10-Q/A and foreign issuer 6-K/6-K/A. Read period-specific
   statements, notes, liquidity changes, and updated risks.
3. **Material events:** 8-K/8-K/A and attached earnings releases, financing,
   acquisition, or restatement exhibits. Read the exhibit itself, not just the
   event headline.
4. **Ownership and capital:** DEF 14A and related proxies, S-1/F-1/S-3,
   prospectus supplements, S-4 and merger proxies, Forms 3/4/5, Schedule
   13D/G. These explain pay, dilution, control, and deals; their amounts do
   not automatically belong in the operating statements.
5. **Issuer-specific:** Funds, banks, insurers, BDCs, and benefit plans need
   their own accounting interpretation and sometimes additional forms.

PDF availability is accession-specific. Many SEC financial reports are HTML
and XBRL; the catalog should list each actual `.pdf` returned by the filing
directory, plus HTML, XML, JSON, text, spreadsheets, and other filed files.
Investor-relations presentation PDFs can supplement filings but must retain
their separate publisher, date, and URL. They should not replace the filed
financial statements.

## Output structure and graph

```text
data/financial_research/
  README.md
  companies/
    CIK0001084869/
      company.json
      resources.csv
      filings.csv
      documents.csv
      pdfs.csv
      companyfacts.json
      README.md
  graph/
    nodes.csv
    edges.csv
    source-map.mmd
  runs/
    run-status.json
```

The graph should link `issuer -> filing -> filed document`,
`issuer -> SEC API endpoint`, `filing -> report period`, and
`filing -> form family`. An amendment should link to the original accession
only when the relationship can be established from source evidence. Preserve
source URL and retrieval status on every resource node. CSV graph files make
the full graph searchable and importable; a Mermaid overview can show the
source hierarchy without rendering thousands of nodes as an unreadable image.

## HiPerGator execution

Use the [GitHub Slurm HPC operator skill](https://github.com/tianyudu/slurm-hpc-agent-skill/blob/main/slurm-hpc-operator/SKILL.md)
for read-only discovery, resource sizing, `sbatch` submission, and job
monitoring. Apply the site-specific [HiPerGator computation rules](https://help.rc.ufl.edu/doc/HPG_Computation):
run the catalog job on a compute node from `/blue/<group>/<user>`, not the
login node or home directory. Discover the account, partition, and quota from
the connected account before submitting. Keep the SEC request rate below its
[10 requests per second aggregate ceiling](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits),
use the supplied contact email in request headers only, cache responses, and
resume from a per-company checkpoint. Do not put credentials or the contact
email in generated public catalog files.

The current `docs/financial-profile-research.md` explains accounting scope,
restatements, reconciliation, and why no public source can expose every
internal transaction of a company.

## Execution record (2026-10-03)

- HiPerGator workspace: /blue/ai-workshop/kkatiyar/quant_hacks_financial_research.
- The input CSV and script were transferred and checked against their local
  SHA-256 hashes before execution.
- Slurm job 44529521 generated the **base** catalog for all 1,630 CIKs:
  1,630 completed folders, 6,521 graph nodes, 6,520 graph edges, and no
  reported errors. This pass generated endpoint URLs only; it did not fetch
  filing directories or verify PDFs.
- Slurm job 44529782 is the one-company **full** SEC access pilot. Its result
  must be read from pilot-44529782.out and catalog/runs/run-status.json before
  submitting the full backfill. This status entry does not claim that the
  pilot has finished or succeeded.
- Local source script: scripts/build_company_source_catalog.py. The remote
  copy has SHA-256
  01e00e52f54652780be753efb6db2c69b90c1869e911e535e9ad31964121cba8.
