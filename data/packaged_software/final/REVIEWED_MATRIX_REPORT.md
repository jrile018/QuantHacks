# Reviewed matrix rebuild — October 4, 2026

The canonical `feature_matrix_backtest.csv` has been rebuilt for diagnostic research.
The previous matrix and its documentation remain in `archive_before_reviewed_v1/`.
The SQLite database and root/output copies remain legacy snapshots; they were not
silently rewritten. No consumer acceptance or executable trading qualification is claimed.

## Coverage

| Measure | Original | Reviewed |
|---|---:|---:|
| Issuers | 168 | 168 |
| Ended calendar quarters since 2022 | 19 | 19 |
| Issuer-quarter rows | 2,334 | 3,192 |
| Raw feature definitions | 37 | 83 |
| Populated raw feature cells | 70.10% | 38.74% |
| Rows with diagnostic return labels | 2,090 | 2,300 |

The percentages have different denominators. The new matrix exposes absent history,
adds sparse financial/cloud definitions, and withholds unverified award predictors.
On the original rows and shared features, the reviewed population rate is 63.48%.
The full grid is an observation/missingness grid, not 3,192 eligible trade decisions.

Selected reviewed feature coverage across 3,192 rows:

| Feature | Populated rows | Population | Issuers with any value |
|---|---:|---:|---:|
| Quarterly revenue | 2,718 | 85.15% | 168 |
| Quarterly R&D | 2,380 | 74.56% | 151 |
| TTM revenue | 2,307 | 72.27% | 160 |
| Revenue growth | 2,702 | 84.65% | 167 |
| R&D / revenue | 2,010 | 62.97% | 144 |
| Gross margin | 2,019 | 63.25% | 144 |
| Physical-capex FCF margin | 2,068 | 64.79% | 149 |
| RPO | 1,737 | 54.42% | 113 |
| Quarterly acquisition payments | 766 | 24.00% | 85 |
| TTM acquisition payments | 1,311 | 41.07% | 110 |

R&D excluding acquired in-process costs is a separate definition; it is not silently
merged with generic R&D. Rule of 40 has only 10 cells because growth and FCF must have
the same economic period. Sparse derivatives are not required for the initial study.

Cloud adds 66 populated feature cells across 22 issuers: 25 commitment disclosure
cells, 21 Appian agreement-spending cells and 20 source-specific expense cells.
These selected cells differ from the larger observation count because reported
comparative periods and repeated filings are not added together or forced into rows.
All underlying observations remain in `feature_matrix_observations.csv` and producer
tables. Contract totals, remaining obligations, annual minimums, mixed associated
services, segment expenses and period spending are separate definitions.

## Repairs and verification

- Equal values receive average tied ranks; constant groups receive zero ranks.
- Financial inputs use the conservative metric/dependency validation layer.
- Dated source selection replaces silent duplicate overwrites; conflicting values
  at the selected period/availability grain remain missing.
- Government award predictors are blank pending historical clocks and amount vintages.
- Price labels use reviewed prices and require provider issuer/share identity match
  and every intervening factor-calendar session. Entry is next-session close and
  exit exactly 63 sessions later. The matched market return is compounded.
- Cloud source bytes match 51 pinned source-file hashes. No property events enter.
- Every feature cell has selected provenance or an explicit missing reason.

Seven focused matrix tests and five financial-quality tests pass. Independent
verification passes all 13 checks in `feature_matrix_validation.json`, including
all populated labels, ranks, input/output hashes and availability cutoffs.

Unlabelled rows: 380 lack a required price session, 176 require identity review,
and 336 lack a mature outcome or the required factor-calendar coverage.

These checks do not certify accounting semantics, actual historical receipt times,
dated universe membership, corporate actions/dividends or feasible execution. The
matrix uses daily historical replay assumptions, not the shared 15:30 New York clock.
Legacy event/annual metrics remain unqualified diagnostics. The initial strategy
study should use reviewed financial blocks separately from those legacy features.

## Reproduction

```powershell
.\venv\Scripts\python.exe data/packaged_software/rebuild_reviewed_matrix.py
.\venv\Scripts\python.exe data/packaged_software/verify_reviewed_matrix.py
.\venv\Scripts\python.exe tests/test_reviewed_matrix.py
.\venv\Scripts\python.exe -m unittest discover -s tests -p test_financial_quality.py
```

The manifest pins producer inputs and matrix artifacts. No API downloads, model
fitting, backtests, paid acquisition or database mutations occurred in this rebuild.
