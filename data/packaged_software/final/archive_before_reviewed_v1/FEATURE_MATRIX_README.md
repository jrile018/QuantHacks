# Backtest feature matrix

**File:** `feature_matrix_backtest.csv`
**Dictionary:** `FEATURE_MATRIX_DICTIONARY.csv` (every column, its role and meaning)

## Rows
One row per company per calendar quarter: 2,334 rows, 168 companies, 2022Q1 to 2026Q3.

- 2,090 rows have an outcome (`label_excess_return_63d`).
- 244 rows are unlabelled: the 2026Q3 quarter, whose 63-day window has not closed yet. They are kept for live use and must be excluded from any test.
- 1,516 rows fall in the 2024Q1+ evaluation window. The rest are warm-up history.

## Columns
122 columns in four groups:

| Group | Columns | Use |
|---|---|---|
| Identifiers | `cik`, `ticker`, `name`, `quarter`, `quarter_end` | Join and index. Use `cik`, never `ticker`. |
| Membership | `membership_status`, `exit_date`, `survivorship_flag`, `survivorship_note`, `in_evaluation_window` | Control which rows a backtest may use. |
| Outcome | `label_excess_return_63d` | What is being predicted. |
| Features | 36 features, each with `__present` and `__rank` | Inputs. |

Each feature appears three times: the raw value, `__present` (1 = value exists), and `__rank` (cross-sectional rank within the quarter, scaled -1 to 1).

## Rules to keep when backtesting
1. Every feature was public by its quarter end. Do not join anything else without an as-of date.
2. Ranks use only that quarter's companies, so they add no future information.
3. The universe is survivors only. Every row has `survivorship_flag = 1`, so results are optimistic until acquired companies are added.
4. Connectedness, 13F common ownership and subsidiary counts are NOT in this file. They are computed over the whole sample and would leak the future.
5. Sparse features (auditor changes, federal awards, goodwill, convertibles, divestitures, contingencies) are too thin to carry a model alone.
