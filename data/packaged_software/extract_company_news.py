"""Real historical Massive news API metadata for the current software universe.

Candidate announcements are not confirmed company contracts or employee adoption.
Requires the existing MASSIVE_API_KEY and entitlement to news back to 2022.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from sec_common import env_value

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NEWS = "https://api.massive.com/v2/reference/news"
FIELDS = ["cik", "ticker", "name", "queried_ticker", "ticker_alias_evidence_url", "article_id", "published_utc", "title", "description", "publisher", "article_url", "associated_tickers", "candidate_category", "company_role", "review_status", "source_api", "history_limitation"]
COVERAGE_FIELDS = ["cik", "ticker", "name", "queried_tickers", "requested_start", "requested_end", "status", "article_count", "candidate_count", "earliest_published_utc", "latest_published_utc", "error", "http_status", "ticker_mapping_scope"]


def clean_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ("api.massive.com", "api.polygon.io"):
        raise ValueError("Unexpected pagination host; refusing to send credentials")
    pairs = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query) if k.lower() not in ("apikey", "api_key")]
    return urllib.parse.urlunsplit(("https", "api.massive.com", parsed.path, urllib.parse.urlencode(pairs), ""))


class NewsClient:
    def __init__(self, cache):
        self.key = env_value("MASSIVE_API_KEY")
        self.cache = cache
        self.last = None

    def page(self, url):
        url = clean_url(url)
        target = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if target.exists():
            return json.loads(target.read_text(encoding="utf-8"))
        if not self.key:
            raise ValueError("MASSIVE_API_KEY is not configured")
        for attempt in range(4):
            if self.last is not None:
                time.sleep(max(0, 0.25 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.key}", "User-Agent": "QuantHacks-research/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    data = json.load(response)
                if data.get("status") not in (None, "OK"):
                    raise ValueError("News API reported an unsuccessful response")
                if data.get("next_url"):
                    data["next_url"] = clean_url(data["next_url"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(data), encoding="utf-8")
                return data
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
                delay = 60 if exc.code == 429 else 2 ** attempt
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise
                delay = 2 ** attempt
            time.sleep(delay)


def query(ticker, start, end, limit=1000):
    return NEWS + "?" + urllib.parse.urlencode({"ticker": ticker, "published_utc.gte": start,
                                               "published_utc.lt": (dt.date.fromisoformat(end) + dt.timedelta(days=1)).isoformat(),
                                               "order": "asc", "sort": "published_utc", "limit": limit})


def category(text):
    if re.search(r"\b(?:artificial intelligence|generative AI|AI|ChatGPT|Copilot|OpenAI|Anthropic|large language model|LLM)\b", text, re.I):
        if re.search(r"\b(?:partner\w*|agreement|contract|collaborat\w*|deploy\w*|rollout|roll out|employees?|workforce|adopt\w*)\b", text, re.I):
            return "ai_announcement_candidate"
    if re.search(r"\b(?:cloud|hosting|hardware|land|data cent(?:er|re))\b", text, re.I) and re.search(r"\b(?:spend\w*|purchas\w*|contract|agreement|commitment|invest\w*)\b", text, re.I):
        return "cloud_or_physical_asset_announcement_candidate"
    return ""


def company_articles(client, aliases, start, end):
    for alias, evidence_url in aliases.items():
        url = query(alias, start, end)
        pages = set()
        while url:
            if url in pages:
                raise ValueError("News API repeated a pagination URL")
            pages.add(url)
            data = client.page(url)
            for article in data.get("results", []):
                yield article, alias, evidence_url
            url = data.get("next_url")


def run(args):
    with args.companies.open(encoding="utf-8-sig", newline="") as source:
        companies = list(csv.DictReader(source))
    if args.check_api:
        client = NewsClient(args.cache)
        data = client.page(query("MSFT", args.start, args.start[:4] + "-12-31", 1))
        articles = data.get("results", [])
        if not articles or articles[0].get("published_utc", "")[:4] != args.start[:4]:
            raise ValueError("No article returned for requested historical year; entitlement not verified")
        print(f"Historical news API verified: {articles[0]['published_utc']} (key not displayed).")
        return 0
    alias_map = {}
    if args.aliases.exists():
        with args.aliases.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                alias_map.setdefault(row["cik"], {})[row["alias"]] = row["evidence_url"]
    args.output.mkdir(parents=True, exist_ok=True)
    client = NewsClient(args.cache)
    coverage, candidates = [], []
    raw_path = args.output / "news_articles.csv"
    auth_failure = None
    with raw_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for i, company in enumerate(companies, 1):
            print(f"Historical news {i}/{len(companies)}: {company['ticker']}", flush=True)
            seen, dates, matches, error, http_status = set(), [], 0, "", ""
            status = "retrieved_current_and_SEC_observed_symbols"
            aliases = {company["ticker"]: "", **alias_map.get(company["cik"], {})}
            try:
                if auth_failure:
                    raise PermissionError("Provider access failed earlier in this run")
                for article, alias, evidence_url in company_articles(client, aliases, args.start, args.end):
                    aid = article.get("id")
                    published = article.get("published_utc", "")
                    if not aid or not args.start <= published[:10] <= args.end:
                        raise ValueError("Missing article ID or historical publication date outside requested range")
                    if aid in seen:
                        continue
                    seen.add(aid)
                    dates.append(published)
                    kind = category(article.get("title", "") + " " + article.get("description", ""))
                    row = {**{k: company[k] for k in ("cik", "ticker", "name")}, "article_id": aid,
                           "queried_ticker": alias, "ticker_alias_evidence_url": evidence_url,
                           "published_utc": published, "title": article.get("title", ""), "description": article.get("description", ""),
                           "publisher": article.get("publisher", {}).get("name", ""), "article_url": article.get("article_url", ""),
                           "associated_tickers": ";".join(article.get("tickers", [])), "candidate_category": kind,
                           "company_role": "unresolved_article_ticker_association_only", "review_status": "unreviewed_news_metadata",
                           "source_api": NEWS, "history_limitation": "retrospective_news_metadata_SEC_observed_symbols_exact_validity_dates_unverified_not_full_vintage"}
                    writer.writerow(row)
                    if kind:
                        candidates.append(row)
                        matches += 1
            except Exception as exc:
                error, http_status = type(exc).__name__, getattr(exc, "code", "")
                status = "partial_fetch_failed" if seen else "fetch_failed_unknown_history"
                if http_status in (401, 402, 403):
                    auth_failure = http_status
                if isinstance(exc, PermissionError) and auth_failure:
                    http_status = auth_failure
            coverage.append({**{k: company[k] for k in ("cik", "ticker", "name")}, "requested_start": args.start, "requested_end": args.end,
                             "queried_tickers": ";".join(aliases),
                             "status": status, "article_count": len(seen), "candidate_count": matches,
                             "earliest_published_utc": min(dates, default=""), "latest_published_utc": max(dates, default=""),
                             "error": error, "http_status": http_status,
                             "ticker_mapping_scope": "current_and_SEC_observed_aliases_exact_validity_dates_unverified"})
    for name, fields, rows in (("news_announcement_candidates.csv", FIELDS, candidates), ("news_coverage.csv", COVERAGE_FIELDS, coverage)):
        with (args.output / name).open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    failures = [c for c in coverage if c["error"]]
    manifest = {"run_at": dt.datetime.now(dt.timezone.utc).isoformat(), "source_api": NEWS,
                "start": args.start, "end": args.end, "companies": len(companies), "candidate_rows": len(candidates),
                "article_rows": sum(c["article_count"] for c in coverage), "failed_companies": len(failures),
                "status": "complete_with_errors" if failures else "complete", "api_key_variable": "MASSIVE_API_KEY",
                "limitations": ["SEC-observed symbol aliases have no verified active-date intervals; reuse and entity changes require review", "news metadata can be revised; not full point-in-time history", "candidates are not confirmed contracts, adoption or spending"]}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{manifest['status']}: {manifest['article_rows']} article rows, {len(candidates)} candidates -> {args.output}")
    return int(bool(failures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=Path, default=HERE / "packaged_software_companies.csv")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    parser.add_argument("--cache", type=Path, default=ROOT / "data/packaged_software/extracts/_cache/company_news")
    parser.add_argument("--output", type=Path, default=ROOT / "data/packaged_software/extracts/company_news")
    parser.add_argument("--check-api", action="store_true")
    parser.add_argument("--aliases", type=Path, default=HERE / "news_ticker_aliases.csv")
    args = parser.parse_args()
    if dt.date.fromisoformat(args.end) < dt.date.fromisoformat(args.start):
        parser.error("End must not precede start")
    raise SystemExit(run(args))
