"""Census Quarterly Services Survey: software publishers (NAICS 5112), 2022 onward.

Fills the industry-baseline item in checklist section 16. It gives the sector's quarterly
revenue and expenses, so each company's growth can be compared with the industry's
(the abnormal-growth benchmark for section 20).

Uses CENSUS_API_KEY from .env. One API call per quarter, cached under
data/packaged_software/extracts/_cache/census_qss/. Output: data/packaged_software/extracts/census/qss_software_publishers.csv

Codes used (from the QSS variable list):
  category_code 5112T      NAICS 5112, software publishers
  data_type_code QREV      quarterly revenue, $ thousands
  data_type_code QEXP      quarterly expenses, $ thousands
  data_type_code PQREV     revenue, percent change from the same quarter last year
  seasonally_adj           'no' is kept as published; the seasonally adjusted series is
                           written too, so either can be used

Caveat: this is an industry aggregate, not per company. Figures are for the whole
Census sample of software publishers, which is not the same set as the 168 companies.
Standard library only.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "extracts" / "_cache" / "census_qss"
OUT = HERE / "extracts" / "census" / "qss_software_publishers.csv"
API = "https://api.census.gov/data/timeseries/eits/qss"
CATEGORY = "5112T"
DATA_TYPES = {"QREV", "QEXP", "PQREV"}
START_YEAR = 2022
# time and time_slot_id are predicates, not fields: the API rejects them in get=
GET = "cell_value,category_code,data_type_code,seasonally_adj"


def census_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("CENSUS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("CENSUS_API_KEY is not set in .env")


def fetch_quarter(quarter: str, key: str) -> list[list[str]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"{quarter}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    url = f"{API}?get={GET}&for=us:*&time={quarter}&time_slot_id=0&key={key}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            # A quarter with no published data returns an error body; record it as empty
            if exc.code == 400:
                data = []
                break
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.3)
    return data


def quarters_through_latest() -> list[str]:
    today = dt.date.today()
    out = []
    for year in range(START_YEAR, today.year + 1):
        for q in range(1, 5):
            # A quarter counts once it has ended, plus a lag for publication
            quarter_end = dt.date(year, q * 3 % 12 or 12, 28)
            if quarter_end < today - dt.timedelta(days=90):
                out.append(f"{year}-Q{q}")
    return out


def main() -> int:
    key = census_key()
    rows = []
    for quarter in quarters_through_latest():
        data = fetch_quarter(quarter, key)
        if not data:
            print(f"{quarter}: no data published")
            continue
        header, body = data[0], data[1:]
        idx = {name: header.index(name) for name in header}
        kept = [r for r in body if r[idx["category_code"]] == CATEGORY and r[idx["data_type_code"]] in DATA_TYPES]
        for r in kept:
            rows.append({
                "quarter": r[idx["time"]],
                "data_type": r[idx["data_type_code"]],
                "seasonally_adjusted": r[idx["seasonally_adj"]],
                "value": r[idx["cell_value"]],
            })
        print(f"{quarter}: {len(kept)} rows")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["quarter", "data_type", "seasonally_adjusted", "value"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["quarter"], r["data_type"], r["seasonally_adjusted"])))

    quarters = sorted({r["quarter"] for r in rows})
    print(f"\nWrote {len(rows)} rows to {OUT}")
    if quarters:
        print(f"  quarters: {quarters[0]} to {quarters[-1]} ({len(quarters)} quarters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
