"""Cache the pharma ranking, FDA bulk data, and current trial records.

The ClinicalTrials.gov v2 API returns current records, not historical versions.
Existing Group A history files are never touched. This script uses at most
three workers, retries 429 and server errors, and never replaces a cache file.
"""

import argparse
import csv
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup


UA = "Abhay (UF student) abhay.dronavalli@gmail.com"
RANK_URL = "https://www.chemanalyst.com/ChemAnalyst/PharmaCompanies"
MANIFEST_URL = "https://api.fda.gov/download.json"
CT_URL = "https://clinicaltrials.gov/api/v2/studies"
ALIASES = {
    "Johnson & Johnson": ("Johnson & Johnson", "Janssen", "Janssen Research & Development", "Janssen Biotech", "Janssen Pharmaceuticals", "JNJ"),
    "Roche": ("Roche", "Genentech", "F. Hoffmann-La Roche", "Hoffmann-La Roche"),
    "Eli Lilly": ("Eli Lilly", "Lilly", "Eli Lilly and Company"),
    "Pfizer": ("Pfizer", "Pfizer Inc"),
    "AbbVie": ("AbbVie", "AbbVie Inc"),
    "AstraZeneca": ("AstraZeneca", "Astra Zeneca", "MedImmune"),
    "Novartis": ("Novartis", "Novartis Pharmaceuticals", "Sandoz"),
    "Merck": ("Merck & Co", "Merck Sharp & Dohme", "MSD"),
    "Sanofi": ("Sanofi", "Sanofi Pasteur", "Genzyme"),
    "Novo Nordisk": ("Novo Nordisk", "Novo Nordisk A/S"),
    "Bristol-Myers Squibb": ("Bristol-Myers Squibb", "Bristol Myers Squibb", "BMS", "Celgene"),
    "GSK": ("GSK", "GlaxoSmithKline", "GlaxoSmithKine", "GlaxoSmithKline Biologicals"),
    "Amgen": ("Amgen", "Amgen Inc"),
    "Gilead Sciences, Inc.": ("Gilead Sciences", "Gilead", "Kite Pharma"),
    "CSL": ("CSL", "CSL Behring", "Seqirus"),
    "Regeneron": ("Regeneron", "Regeneron Pharmaceuticals"),
    "Vertex Pharmaceuticals": ("Vertex Pharmaceuticals", "Vertex"),
    "Biogen": ("Biogen", "Biogen Idec"),
    "Moderna": ("Moderna", "ModernaTX"),
    "Takeda": ("Takeda", "Takeda Pharmaceutical", "Shire"),
}
TICKERS = {"Johnson & Johnson": "JNJ", "Roche": "RHHBY", "Eli Lilly": "LLY", "Pfizer": "PFE",
           "AbbVie": "ABBV", "AstraZeneca": "AZN", "Novartis": "NVS", "Merck": "MRK",
           "Sanofi": "SNY", "Novo Nordisk": "NVO", "Bristol-Myers Squibb": "BMY",
           "GSK": "GSK", "Amgen": "AMGN", "Gilead Sciences, Inc.": "GILD", "CSL": "CSL.AX",
           "Regeneron": "REGN", "Vertex Pharmaceuticals": "VRTX", "Biogen": "BIIB",
           "Moderna": "MRNA", "Takeda": "TAK"}


def get_bytes(url, params=None):
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json,text/html,*/*"})
    for attempt in range(5):
        response = session.get(url, params=params, timeout=60)
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 2 ** attempt + random.random()))
            continue
        response.raise_for_status()
        return response.content
    response.raise_for_status()


def cached(path, url, params=None):
    if path.exists():
        return path.read_bytes(), "cached"
    body = get_bytes(url, params)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(body)
    return body, "downloaded"


def ranking(data):
    folder = data / "raw" / "research_cache"
    html, state = cached(folder / "top100_ranking.html", RANK_URL)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table")
    if table is None:
        raise ValueError("Ranking page has no table")
    rows = []
    for tr in table.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.select("td")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        rank = int(cells[0])
        company = re.sub(r"\s+[123]$", "", cells[1]).strip()
        if company == "GlaxoSmithKine":
            company = "GSK"
        if company == "Janssen/ Johnson & Johnson":
            company = "Johnson & Johnson"
        aliases = ALIASES.get(company, (company,))
        rows.append(dict(rank=rank, company=company, aliases=";".join(dict.fromkeys(aliases)),
                         ticker=TICKERS.get(company, ""), revenue_2025_musd=cells[2], source_url=RANK_URL))
    if len(rows) != 100 or [row["rank"] for row in rows] != list(range(1, 101)):
        raise ValueError(f"Expected ranks 1 to 100; got {len(rows)} rows")
    output = data / "raw" / "top100_pharma.csv"
    if not output.exists():
        with output.open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    print(f"Ranking: {state}; 100 rows; {output}", flush=True)
    return rows


def fda(data):
    folder = data / "raw" / "research_cache"
    body, state = cached(folder / "fda_download_manifest.json", MANIFEST_URL)
    manifest = json.loads(body)
    partition = manifest["results"]["drug"]["drugsfda"]["partitions"][0]
    url = partition["file"]
    path = folder / Path(url).name
    content, zip_state = cached(path, url)
    if content[:2] != b"PK":
        raise ValueError("FDA bulk response is not a ZIP file")
    print(f"FDA manifest: {state}; export {manifest['results']['drug']['drugsfda']['export_date']}; records {partition['records']}", flush=True)
    print(f"FDA bulk: {zip_state}; bytes {len(content)}; {path}", flush=True)


def pull_company(row, root):
    rank, company = int(row["rank"]), row["company"]
    folder = root / f"{rank:03d}"
    count = 0
    states = []
    for alias_number, phrase in enumerate(row["aliases"].split(";")):
        if len(phrase) < 5:
            continue
        page = 0
        token = None
        while True:
            params = {"query.spons": phrase,
                      "filter.advanced": "AREA[StartDate]RANGE[2018-01-01,MAX]",
                      "pageSize": 1000, "countTotal": "true"}
            if token:
                params["pageToken"] = token
            path = folder / f"alias_{alias_number:02d}" / f"page_{page:04d}.json"
            content, state = cached(path, CT_URL, params)
            payload = json.loads(content)
            count += len(payload.get("studies", []))
            states.append(state)
            token = payload.get("nextPageToken")
            if not token:
                break
            page += 1
            time.sleep(0.25)
    return rank, company, count, len(states), "cached" if all(x == "cached" for x in states) else "downloaded"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--mode", choices=["ranking", "fda", "trials", "all"], default="all")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.workers <= 3:
        parser.error("workers must be 1 to 3")
    rows = ranking(args.data) if args.mode in ("ranking", "trials", "all") else None
    if args.mode in ("fda", "all"):
        fda(args.data)
    if args.mode in ("trials", "all"):
        root = args.data / "raw" / "research_cache" / "ct_v2_group_b"
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(pull_company, row, root) for row in rows[:args.limit]]
            for i, future in enumerate(as_completed(futures), start=1):
                rank, company, count, pages, state = future.result()
                eta = (args.limit - i) * (time.monotonic() - start) / i / 60
                print(f"Trial search {i}/{args.limit}: rank {rank} {company}; {count} records; {pages} pages; {state}; ETA {eta:.1f} min", flush=True)


if __name__ == "__main__":
    main()
