# Synthetic REIT money-analysis example

All numbers, issuer identifiers and URLs in this fixture are made up. This is an offline behavior demonstration, not a filing, real company result or accuracy benchmark.

From the repository root:

```powershell
.venv/Scripts/python.exe scripts/analyze_reit_money.py --collection-dir examples/reit_money_analysis/input
```

The input has a cash inflow of $100 million stated twice with the same context, a separate $100 million debt balance, and a custom $250 million facility amount. The first becomes one observation with two evidence locations. The balance remains separate; the custom amount requires review. A loan table and an agreement-style excerpt remain unresolved candidates.

Expected output: two parsed records, one review record and two candidates. An unchanged second run reuses the analysis. Inputs use paths relative to their collection directory; generated outputs contain local resolved evidence paths and should be regenerated after moving the fixture.
