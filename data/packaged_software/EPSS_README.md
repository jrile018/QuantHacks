# Historical EPSS features for packaged-software companies

`extract_epss.py` uses the 168 entries in `packaged_software_companies.csv` by
default. No additional packages or EPSS key are required. An optional
`NVD_API_KEY` is read from the environment or the repository `.env`, without
printing it. The Census key is unrelated.

## Run

From the repository root:

```powershell
# Every published daily snapshot since January 1, 2022, through yesterday UTC.
python data/packaged_software/extract_epss.py

# Smaller alternative: first day of each month, not monthly averages.
python data/packaged_software/extract_epss.py --frequency monthly --output data/extracts/epss_monthly

# Short validation run on selected companies.
python data/packaged_software/extract_epss.py --tickers ADBE,MSFT --start 2022-01-01 --end 2022-01-02 --output data/extracts/epss_smoke
```

Daily history involves thousands of bulk downloads and can take a long time.
The extractor reads one date at a time and discards the bulk file after selecting
the target CVEs. `--keep-bulk-cache` retains those files, potentially several GB.
`--summary-only` omits the per-CVE output. Successful dates are checkpointed so
rerunning the **same command** resumes. For a different date range, company
selection, mapping or frequency, use a different output directory. NVD results
are cached under `data/extracts/_cache/epss`; this cache is deliberately a fixed
retrieval snapshot, not an automatically refreshed feed. To refresh NVD, choose a
new `--cache` and `--output` directory. Failed vendors and dates appear in the
manifest; a run with failures exits with status 1.
If a bulk date is inaccessible, the extractor tries the original download host
and then FIRST's dated API. API recovery verifies every row's date; because that
endpoint does not provide model metadata, its model is explicitly labeled
`unavailable_from_api`. API scores can have more decimal precision than bulk CSV
scores. A date that fails all sources remains a manifest error, never a substitute
date or a zero score.

## Outputs

- `company_epss_history.csv`: one row for every company and successful score date.
- `summary/YYYY-MM-DD.csv`: the same rows partitioned by date.
- `cves/YYYY-MM-DD.csv.gz`: company/CVE scores and percentiles, with original NVD
  publication timestamps and matched vendors. CSVs can be read with pandas
  `read_csv`, which infers gzip compression.
- `company_cve_inventory.json`: the retrieved current company/CVE associations.
- `mapping_coverage.csv`: all company aliases, observed application vendors and
  unconfirmed aliases, to make mapping gaps inspectable.
- `manifest.json`: parameters, NVD retrieval times, model versions, dates and errors.

All joins use CIK, with ticker and name retained for convenience. Multiple mapped
vendors are deduplicated by CVE before computing a company's features.

## Meaning and limits

EPSS is a CVE-level probability of observed exploitation in the next 30 days.
It is **not** a probability of a company breach, evidence that a company uses a
product, a measure of financial losses, or evidence that vulnerable products are
still unpatched. These features summarize CVEs affecting products attributed to
the company. They describe **product-vulnerability exposure**, not the company's
internal IT estate. The extractor only includes application (`a`) CPEs; operating
systems and hardware are excluded. Counts cover all eligible retrieved CVEs,
including old vulnerabilities, not just recent or unpatched vulnerabilities.

`epss_company_mapping.csv` supplies conservative direct current-brand aliases.
These are curated starting aliases, not a complete ownership database. NVD's
returned CPE configurations must mark the matching application/vendor as
`vulnerable: true`; merely mentioning a product as a prerequisite does not count.
An alias with no matching CVEs is **not** proof that the company has no vulnerable
products. Unmapped companies remain in the output. Subsidiaries, acquired brands,
renames and ambiguous vendor identities need additional review. A company with
scores may still have incomplete vendor coverage.

To add a reviewed alias, edit its company's `cpe_vendors` field (semicolon-separated
for multiple aliases), set `mapping_status` to `curated_current_brand`, and record
the supporting evidence and ownership scope. Do not include an acquired vendor
throughout history without recognizing the resulting ownership leakage. Query
existence alone is insufficient evidence of company ownership.

Coverage statuses are explicit:

| Status | Meaning |
| --- | --- |
| `unmapped` | No curated vendor alias; scores and counts unknown. |
| `nvd_fetch_failed` | At least one vendor failed; company scores and counts unknown. |
| `no_current_matching_cves` | No directly vulnerable application CVEs returned for the chosen alias. |
| `no_eligible_cves_on_date` | Matching CVEs exist today but none have a publication date on/before this snapshot. |
| `no_epss_scores` | Eligible CVEs exist but none occur in the EPSS file. |
| `partial_epss_coverage` | Only some eligible CVEs occur in the EPSS file. |
| `scored` | All eligible retrieved CVEs have scores; vendor mapping can still be incomplete. |

Mean, median and maximum are calculated **only over scored CVEs**. Missing scores
are blank, never imputed to zero. A zero high-score count is written only when at
least one score exists. `score_coverage_fraction` measures EPSS coverage of the
retrieved CVEs, not coverage of all the company's products. The default 0.10
threshold is a configurable research choice, not an official company-risk cutoff.
Large vendors and long-established products naturally have more public CVEs, so
counts and maxima are biased by product breadth, age and disclosure practices.
No synthetic combined company probability or historical CVSS value is produced.

## Historical interpretation

The EPSS probability, percentile and model version come from the **actual dated
FIRST snapshot**. CVEs published after the snapshot date are excluded. Historical
EPSS dates exist from April 14, 2021, so January 2022 is supported. Models changed
in February 2022, March 2023 and March 2025 (and may change again); use the recorded
`model_version` when comparing dates rather than assuming one constant model.
Early files before February 4, 2022 have no embedded metadata: their date comes
from the dated download filename and their model is explicitly labeled
`v1_inferred_from_release_date`. If a historical file lacks percentiles, the
extractor preserves them as blank. The manifest records the date source.

Every row carries
`retrospective_current_universe_and_nvd_mapping_not_point_in_time`.
Historical EPSS does **not** make this a fully point-in-time trading dataset:

- The company universe is the repository's current list, with survivorship bias.
- CPE associations, publication fields and ownership aliases use current NVD and
  company information, which may have been added or corrected after the score date.
- A current company may not have existed, been publicly traded or owned a product
  in 2022. Tickers also change.

A strict backtest needs historical universe membership, product ownership validity
periods, archived NVD associations and the time each daily snapshot became
available. This extractor is suitable for retrospective research with those limits
explicitly represented; do not label its output as point-in-time safe.

Sources: [FIRST EPSS data](https://www.first.org/epss/data_stats),
[FIRST EPSS API](https://api.first.org/epss/),
[NVD CVE API](https://nvd.nist.gov/developers/vulnerabilities),
[NVD API guidance](https://nvd.nist.gov/developers/start-here).
