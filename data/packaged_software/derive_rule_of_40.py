"""Add a Rule of 40 score to the quarterly fundamentals.

Rule of 40 = year-over-year revenue growth + free-cash-flow margin, both as percentage points.
Reads data/extracts/company_metrics/fundamentals_quarterly.csv and writes
output/rule_of_40.csv with one row per company-quarter where both inputs exist.

Caveat: the FCF margin in the source file is operating cash flow minus physical capex,
so capitalized software is not deducted. Standard FCF definitions vary.
Standard library only.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "data" / "extracts" / "company_metrics" / "fundamentals_quarterly.csv"
OUT = HERE / "output" / "rule_of_40.csv"
FIELDS = ["cik", "ticker", "name", "period_end", "rev_growth_pct", "fcf_margin_pct", "rule_of_40"]


def to_pct(value: str) -> float | None:
    return round(float(value) * 100, 2) if value not in ("", None) else None


def main() -> int:
    rows = []
    with SRC.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            growth = to_pct(r["rev_growth_yoy_q"])
            fcf = to_pct(r["fcf_physical_capex_margin"])
            if growth is None or fcf is None:
                continue
            rows.append({
                "cik": r["cik"], "ticker": r["ticker"], "name": r["name"],
                "period_end": r["period_end"],
                "rev_growth_pct": growth, "fcf_margin_pct": fcf,
                "rule_of_40": round(growth + fcf, 2),
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    passing = sum(1 for r in rows if r["rule_of_40"] >= 40)
    tickers = {r["ticker"] for r in rows}
    print(f"Wrote {len(rows)} company-quarters for {len(tickers)} companies to {OUT}")
    print(f"Rule of 40 or higher: {passing} of {len(rows)} ({100 * passing / max(len(rows), 1):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
