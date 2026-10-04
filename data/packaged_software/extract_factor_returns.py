"""Fama-French benchmark and factor returns, 2022 onward (public files, no API key).

Fills the factor-returns line of checklist section 15 and gives section 20 the benchmark
series that abnormal-return tests need.

Downloads the daily research factor files from the Ken French data library and writes
output/factor_returns_daily.csv with one row per trading day:
  mkt_rf  market excess return      smb  size      hml  value
  rf      risk-free rate            mom  momentum (from the separate momentum file)
All values are percent per day, as published.

Note: these are market-wide series, not per company. Pairing them with company returns
needs the price data, which is not pulled yet.
Standard library only.
"""

from __future__ import annotations

import csv
import io
import re
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "extracts" / "_cache" / "factor_returns"
OUT = HERE / "output" / "factor_returns_daily.csv"
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {
    "factors": ("F-F_Research_Data_Factors_daily_CSV.zip", ["mkt_rf", "smb", "hml", "rf"]),
    "momentum": ("F-F_Momentum_Factor_daily_CSV.zip", ["mom"]),
}
START = "20220101"
DATE_ROW_RE = re.compile(r"^\s*(\d{8})\s*,(.+)$")


def download(filename: str) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / filename
    if cache_file.exists():
        return cache_file.read_bytes()
    req = urllib.request.Request(BASE + filename, headers={"User-Agent": "quanthacks-research"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
    cache_file.write_bytes(body)
    return body


def parse(filename: str, columns: list[str]) -> dict[str, dict[str, str]]:
    """Return {yyyymmdd: {column: value}} for the daily rows at or after START.

    The files carry a text header, then daily rows, and the annual-factor files append a
    second block. Only rows whose first field is an 8-digit date are kept, so the header
    and any trailing block are skipped without needing to count lines.
    """
    data = download(filename)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        raw = z.read(z.namelist()[0]).decode("latin-1")
    out: dict[str, dict[str, str]] = {}
    for line in raw.splitlines():
        m = DATE_ROW_RE.match(line)
        if not m:
            continue
        date, rest = m.group(1), m.group(2)
        if date < START:
            continue
        values = [v.strip() for v in rest.split(",")]
        if len(values) < len(columns):
            continue
        out[date] = dict(zip(columns, values[: len(columns)]))
    return out


def main() -> int:
    merged: dict[str, dict[str, str]] = {}
    for name, (filename, columns) in FILES.items():
        rows = parse(filename, columns)
        print(f"{name}: {len(rows)} daily rows from {filename}")
        for date, values in rows.items():
            merged.setdefault(date, {}).update(values)

    all_columns = [c for _, cols in FILES.values() for c in cols]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date"] + all_columns)
        w.writeheader()
        for date in sorted(merged):
            row = {"date": f"{date[:4]}-{date[4:6]}-{date[6:]}"}
            row.update({c: merged[date].get(c, "") for c in all_columns})
            w.writerow(row)

    dates = sorted(merged)
    complete = sum(1 for d in dates if all(merged[d].get(c) for c in all_columns))
    print(f"Wrote {len(dates)} trading days to {OUT}")
    print(f"  range: {dates[0]} to {dates[-1]}")
    print(f"  days with every factor present: {complete} of {len(dates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
