"""Record issuer trading symbols actually observed in archived SEC filings.

Observations link symbols to CIKs, but do not establish exact symbol validity dates.
"""
import csv
import html
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SYMBOL = re.compile(r'<ix:nonnumeric\b[^>]*name\s*=\s*[\"\']dei:TradingSymbol[\"\'][^>]*>(.*?)</ix:nonnumeric\s*>', re.I | re.S)


def main():
    with (HERE / "packaged_software_companies.csv").open(encoding="utf-8-sig", newline="") as source:
        companies = {int(c["cik"]): c for c in csv.DictReader(source)}
    with (ROOT / "data/packaged_software/extracts/sec/filings_index.csv").open(encoding="utf-8-sig", newline="") as source:
        filings = list(csv.DictReader(source))
    observed = {}
    for f in sorted(filings, key=lambda f: f["filing_date"]):
        if int(f["cik"]) not in companies or f["form"] not in ("10-K", "10-Q", "20-F", "40-F"):
            continue
        path = ROOT / f["local_path"]
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        c = companies[int(f["cik"])]
        for match in SYMBOL.finditer(raw):
            symbol = html.unescape(re.sub(r"<[^>]+>", "", match[1])).strip().upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", symbol) or symbol in ("NONE", "NA", "NOTAPPLICABLE"):
                continue
            key = (c["cik"], symbol)
            if key not in observed:
                url = f"https://www.sec.gov/Archives/edgar/data/{int(c['cik'])}/{f['accession'].replace('-', '')}/{f['primary_document']}"
                observed[key] = {"cik": c["cik"], "ticker": c["ticker"], "alias": symbol,
                                 "first_observed_filing_date": f["filing_date"], "last_observed_filing_date": f["filing_date"],
                                 "evidence_url": url, "mapping_status": "observed_dei_TradingSymbol_exact_validity_dates_unverified"}
            observed[key]["last_observed_filing_date"] = f["filing_date"]
    fields = ["cik", "ticker", "alias", "first_observed_filing_date", "last_observed_filing_date", "evidence_url", "mapping_status"]
    target = HERE / "news_ticker_aliases.csv"
    with target.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(observed[key] for key in sorted(observed))
    print(f"Recorded {len(observed)} SEC-observed CIK/symbol pairs, including {sum(v['alias'] != v['ticker'] for v in observed.values())} alternative symbols -> {target}")


if __name__ == "__main__":
    main()
