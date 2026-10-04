"""Common-ownership layer from SEC 13F holdings (ownership edges for connectedness).

Two companies are linked when the same institutional managers hold them. For each quarter
the holdings are a manager x company matrix of market value. A company's vector is its
manager-holding profile, and the edge weight is the cosine similarity of two profiles:
1 means the same managers hold the two in the same proportions, 0 means no overlap.
Weights are averaged over the quarters in the window, so a link has to persist.

Scope: 13F quarters from 2022-Q1 onward. The evaluation window starts in January 2024, but
2022-2023 is kept as warm-up history, as the project plan requires, so the edges have the
same history as the rest of the dataset.
Company matching is by normalized issuer name to the 13F CUSIP table. A name that does not
match exactly is left out and counted, rather than fuzzy-matched into a wrong company.
Common-stock classes only (COM, ORD, CL A).

Writes:
  output/common_ownership_edges.csv   company pair, average cosine, quarters observed
  output/common_ownership_coverage.csv per-quarter coverage: companies matched, managers
Standard library only apart from numpy. Caches the downloaded zips under extracts/13f.
"""

from __future__ import annotations

import csv
import io
import re
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE / "extracts" / "13f"
OUT = HERE / "output"
COMPANIES = HERE / "packaged_software_companies.csv"
INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
BASE = "https://www.sec.gov"
START_YEAR = 2022
MIN_QUARTERS = 2          # a pair must co-occur in at least this many quarters
PASSIVE_SHARE = 0.40      # managers holding more than this share of the universe are dropped
MIN_COSINE = 0.05         # drop near-zero similarity to keep the file readable
UA = "quanthacks-research k.katiyar2006@gmail.com"
SUFFIX_RE = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|"
    r"the|class|common|stock|com|cl|new|de|ord|shs|ordinary|shares?)\b\.?", re.I)
COMMON_TITLES = ("COM", "ORD", "CL A", "COMMON")


def core(name: str) -> str:
    # ".com" must go before punctuation is stripped, or "Salesforce.com" keeps a stray token
    text = re.sub(r"\.com", " ", name, flags=re.I)
    cleaned = SUFFIX_RE.sub(" ", re.sub(r"[^A-Za-z0-9& ]", " ", text))
    cleaned = re.sub(r"(corp|corporation|inc|incorporated|com)", " ", cleaned, flags=re.I)
    return " ".join(cleaned.split()).upper()


def issuer_of(cusip: str) -> str:
    """The first six characters of a CUSIP identify the issuer. Share classes differ only
    in the last two or three, so matching on six collapses Alphabet's classes A and C into
    one company, and stops "MICROSOFT CORP" and "Microsoft Corporation" from being separate
    issuers."""
    return cusip[:6]


def quarter_links() -> list[tuple[str, str]]:
    """(label, url) for every 13F data set from START_YEAR onward, oldest first."""
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    # The index uses two naming schemes: "2022q1_form13f.zip" for older sets and
    # "01jan2024-29feb2024_form13f.zip" for newer ones. Both are read, keyed by quarter.
    found = sorted(set(re.findall(r"/files/structureddata/data/form-13f-data-sets/([^\"'\s<>]+_form13f\.zip)", html)))
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    out = {}
    for name in found:
        # Each file is keyed by its start date, not a quarter label. The newer files cover
        # uneven spans (Jan-Feb, Mar-May, Jun-Aug...), so two of them can share a calendar
        # quarter, and keying by quarter would silently drop one.
        q = re.match(r"(\d{4})q([1-4])_", name)
        m = re.match(r"(\d{2})([a-z]{3})(\d{4})-", name)
        if q:
            year, month = int(q.group(1)), (int(q.group(2)) - 1) * 3 + 1
        elif m:
            year, month = int(m.group(3)), months.index(m.group(2)[:3]) + 1
        else:
            continue
        if year < START_YEAR:
            continue
        label = f"{year}-{month:02d}"
        out[label] = (label, f"{BASE}/files/structureddata/data/form-13f-data-sets/{name}")
    return [out[k] for k in sorted(out)]


def fetch(label: str, url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    local = CACHE / f"{label}.zip"
    if not local.exists():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        local.write_bytes(urllib.request.urlopen(req, timeout=600).read())
        time.sleep(0.5)
    return local


def issuer_map_for(cusip_names: dict[str, set[str]], companies: list[dict]) -> dict[str, str]:
    """universe ticker -> issuer key (six-character CUSIP stem), matched on normalized name.

    A name that maps to more than one issuer is excluded rather than guessed at.
    """
    by_core: dict[str, set[str]] = defaultdict(set)
    for cusip, names in cusip_names.items():
        for nm in names:
            by_core[core(nm)].add(issuer_of(cusip))
    out = {}
    for c in companies:
        k = core(re.sub(r"\s*(Class\s+[A-Z]\s+)?Common Stock.*$", "", c["name"], flags=re.I))
        issuers = by_core.get(k, set())
        if len(issuers) == 1:
            out[c["ticker"]] = next(iter(issuers))
    return out


def main() -> int:
    companies = [r for r in csv.DictReader(COMPANIES.open(encoding="utf-8")) if r["ticker"]]
    links = quarter_links()
    print(f"{len(links)} quarterly 13F data sets from {START_YEAR}")

    pair_sum: dict[tuple[str, str], float] = defaultdict(float)
    pair_n: dict[tuple[str, str], int] = defaultdict(int)
    coverage = []

    for label, url in links:
        zpath = fetch(label, url)
        with zipfile.ZipFile(zpath) as z:
            # Archive layouts differ between quarters (case and folders), so match by name
            member = next((n for n in z.namelist() if n.lower().endswith("infotable.tsv")), None)
            if member is None:
                print(f"{label}: no INFOTABLE in archive ({z.namelist()[:4]}); skipped")
                continue
            table = list(csv.DictReader(io.TextIOWrapper(z.open(member), encoding="utf-8"), delimiter="\t"))

        cusip_names: dict[str, set[str]] = defaultdict(set)
        for r in table:
            if any(t in r["TITLEOFCLASS"].upper() for t in COMMON_TITLES):
                cusip_names[r["CUSIP"]].add(r["NAMEOFISSUER"])
        ticker_cusip = issuer_map_for(cusip_names, companies)
        cusip_ticker = {v: k for k, v in ticker_cusip.items()}  # issuer key -> ticker

        # manager x company market value
        managers = sorted({r["ACCESSION_NUMBER"] for r in table})
        m_index = {m: i for i, m in enumerate(managers)}
        tickers = sorted(ticker_cusip)
        t_index = {t: i for i, t in enumerate(tickers)}
        M = np.zeros((len(managers), len(tickers)))
        for r in table:
            t = cusip_ticker.get(issuer_of(r["CUSIP"]))
            if t is None:
                continue
            try:
                M[m_index[r["ACCESSION_NUMBER"]], t_index[t]] += float(r["VALUE"] or 0)
            except (KeyError, ValueError):
                continue

        # Each company's profile over managers, normalized so a large manager does not
        # dominate by size alone
        # Passive confound: a manager holding most of the universe (index funds) makes every
        # pair look similar. Drop managers that hold more than PASSIVE_SHARE of the matched
        # companies, so the remaining overlap reflects active or concentrated holdings.
        held_count = (M > 0).sum(axis=1)
        keep = held_count <= PASSIVE_SHARE * max(len(tickers), 1)
        M = M[keep]
        col = M.copy()
        norm = np.linalg.norm(col, axis=0)
        norm[norm == 0] = 1
        U = col / norm
        S = U.T @ U
        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                s = float(S[i, j])
                if s >= MIN_COSINE and M[:, i].any() and M[:, j].any():
                    key = (tickers[i], tickers[j])
                    pair_sum[key] += s
                    pair_n[key] += 1
        coverage.append({"quarter": label, "companies_matched": len(tickers),
                         "managers": len(managers), "holding_rows": len(table)})
        print(f"{label}: {len(tickers)} companies matched, {len(managers)} managers, {len(table)} holdings")
        del table, M, col, U, S

    edges = []
    for key, total in pair_sum.items():
        n = pair_n[key]
        if n >= MIN_QUARTERS:
            edges.append({"company_a": key[0], "company_b": key[1],
                          "mean_cosine": round(total / len(links), 4),
                          "quarters_observed": n})
    edges.sort(key=lambda r: -r["mean_cosine"])

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "common_ownership_edges.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["company_a", "company_b", "mean_cosine", "quarters_observed"])
        w.writeheader()
        w.writerows(edges)
    with (OUT / "common_ownership_coverage.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(coverage[0].keys()))
        w.writeheader()
        w.writerows(coverage)
    print(f"\n{len(edges)} common-ownership edges (cosine >= {MIN_COSINE} in >= {MIN_QUARTERS} quarters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
