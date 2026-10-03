"""Combine the built factor outputs into one row per company for the 168-company universe.

Sources (all already on disk):
  packaged_software_companies.csv          identity (cik, ticker, name, sic)
  output/8k_item_by_company.csv            8-K item counts (scan_8k_items.py)
  output/item_105_by_company.csv           Item 1.05 cyber incidents (scan_item_105.py)
  output/rule_of_40.csv                    latest Rule of 40 (derive_rule_of_40.py)
  data/packaged_software/extracts/company_metrics/fundamentals_quarterly.csv   latest TTM revenue, operating cash flow
  output/company_summary.csv               federal contract totals, exact-name matches
  data/packaged_software/extracts/company_news/news_articles.csv               news candidates per company

Writes output/company_factors.csv. Columns that have no source yet are left blank,
so the file shows what is still missing.
Standard library only.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "output" / "company_factors.csv"
ITEMS_8K = ["1.01", "1.02", "1.05", "2.01", "2.02", "2.03", "2.04", "2.05", "2.06",
            "4.01", "4.02", "5.02", "5.07", "8.01", "7.01"]


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    companies = read_rows(HERE / "packaged_software_companies.csv")
    by_8k = {r["ticker"]: r for r in read_rows(HERE / "output" / "8k_item_by_company.csv")}
    by_105 = {r["ticker"]: r for r in read_rows(HERE / "output" / "item_105_by_company.csv")}
    contracts = {r["cik"].zfill(10): r for r in read_rows(HERE / "output" / "company_summary.csv")}

    # Latest Rule of 40 per company (rows are in period order within each company)
    latest_r40: dict[str, dict] = {}
    for r in read_rows(HERE / "output" / "rule_of_40.csv"):
        latest_r40[r["ticker"]] = r

    # Latest quarter revenue and operating cash flow (TTM) per company
    latest_fund: dict[str, dict] = {}
    for r in read_rows(HERE / "extracts" / "company_metrics" / "fundamentals_quarterly.csv"):
        prev = latest_fund.get(r["ticker"])
        if prev is None or r["period_end"] > prev["period_end"]:
            latest_fund[r["ticker"]] = r

    news_count: dict[str, int] = defaultdict(int)
    news_path = HERE / "extracts" / "company_news" / "news_articles.csv"
    for r in read_rows(news_path):
        news_count[r["ticker"]] += 1

    # Sources added after the first version of this table
    kev = {r["ticker"]: r for r in read_rows(HERE / "output" / "kev_by_company.csv")}
    lei = {r["ticker"]: r for r in read_rows(HERE / "output" / "company_lei.csv")}
    identity = {r["ticker"]: r for r in read_rows(HERE / "output" / "company_identity.csv")}
    signals = {r["ticker"]: r for r in read_rows(HERE / "output" / "filing_signals.csv")}
    fedreg = {r["ticker"]: r for r in read_rows(HERE / "output" / "federal_register_by_company.csv")}
    details = {r["ticker"]: r for r in read_rows(HERE / "output" / "ticker_details.csv")}
    enforcement = {r["ticker"]: r for r in read_rows(HERE / "output" / "sec_enforcement_by_company.csv")}

    # 10-K text flags: keep the latest filing per company, plus a count of filings scanned
    tenk_latest: dict[str, dict] = {}
    tenk_count: dict[str, int] = defaultdict(int)
    for r in read_rows(HERE / "output" / "tenk_text_flags.csv"):
        tenk_count[r["ticker"]] += 1
        prev = tenk_latest.get(r["ticker"])
        if prev is None or r["filing_date"] > prev["filing_date"]:
            tenk_latest[r["ticker"]] = r
    TENK_FLAGS = ["item_1c_cyber_section", "substantial_doubt_going_concern",
                  "material_weakness_identified", "restated_own_financials",
                  "customer_pct_of_revenue", "artificial_intelligence",
                  "cloud_provider_mention", "patent_infringement",
                  "class_action_filed_against_company"]

    fields = (["cik", "ticker", "name", "sic", "exchanges", "fiscal_year_end",
               "state_of_incorporation", "lei", "lei_match_confidence",
               "domain", "total_employees", "list_date", "market_cap",
               "sec_enforcement_actions",
               "latest_period_end", "ttm_revenue", "ttm_operating_cash_flow",
               "latest_rule_of_40", "contract_awards_exact", "contract_total_usd_exact",
               "cyber_incidents_item_1_05", "cyber_wording_filings",
               "kev_total", "kev_since_2022", "kev_ransomware_linked",
               "insider_filings_since_2022", "ownership_filings_since_2022",
               "late_filing_notices_since_2022", "sec_comment_letters_since_2022",
               "federal_register_documents", "news_articles",
               "tenk_filings_scanned", "latest_tenk_date"]
              + [f"tenk_{f}" for f in TENK_FLAGS]
              + [f"8k_item_{i.replace('.', '_')}" for i in ITEMS_8K])

    rows = []
    for c in companies:
        t = (c["ticker"] or "").strip()
        cik = c["cik"].zfill(10)
        f = latest_fund.get(t, {})
        r40 = latest_r40.get(t, {})
        k = by_8k.get(t, {})
        ct = contracts.get(cik, {})
        ident = identity.get(t, {})
        sig = signals.get(t, {})
        k_ev = kev.get(t, {})
        l_ei = lei.get(t, {})
        tenk = tenk_latest.get(t, {})
        row = {
            "cik": cik, "ticker": t, "name": c["name"], "sic": c["sic"],
            "exchanges": ident.get("exchanges", ""),
            "fiscal_year_end": ident.get("fiscal_year_end", ""),
            "state_of_incorporation": ident.get("state_of_incorporation", ""),
            "lei": l_ei.get("lei", ""),
            "lei_match_confidence": l_ei.get("match_confidence", ""),
            "domain": details.get(t, {}).get("domain", ""),
            "total_employees": details.get(t, {}).get("total_employees", ""),
            "list_date": details.get(t, {}).get("list_date", ""),
            "market_cap": details.get(t, {}).get("market_cap", ""),
            "sec_enforcement_actions": enforcement.get(t, {}).get("matched_releases", ""),
            "kev_total": k_ev.get("kev_total", ""),
            "kev_since_2022": k_ev.get("kev_since_2022", ""),
            "kev_ransomware_linked": k_ev.get("kev_ransomware_linked", ""),
            "insider_filings_since_2022": sig.get("form3_4_insider_filings", ""),
            "ownership_filings_since_2022": sig.get("sc13d_13g_ownership_filings", ""),
            "late_filing_notices_since_2022": sig.get("late_filing_notices", ""),
            "sec_comment_letters_since_2022": sig.get("sec_comment_letters", ""),
            "federal_register_documents": fedreg.get(t, {}).get("total_matching_documents", ""),
            "tenk_filings_scanned": tenk_count.get(t, 0),
            "latest_tenk_date": tenk.get("filing_date", ""),
            "latest_period_end": f.get("period_end", ""),
            "ttm_revenue": f.get("ttm_revenue", ""),
            "ttm_operating_cash_flow": f.get("ttm_operating_cash_flow", ""),
            "latest_rule_of_40": r40.get("rule_of_40", "") if r40 else "",
            "contract_awards_exact": ct.get("award_count_exact_name", ""),
            "contract_total_usd_exact": ct.get("total_exact_name", ""),
            "cyber_incidents_item_1_05": by_105.get(t, {}).get("item_105_filings", ""),
            "cyber_wording_filings": k.get("cyber_wording_filings", ""),
            "news_articles": news_count.get(t, 0) if news_path.exists() else "",
        }
        for flag in TENK_FLAGS:
            row[f"tenk_{flag}"] = tenk.get(flag, "")
        for i in ITEMS_8K:
            row[f"8k_item_{i.replace('.', '_')}"] = k.get(i, "")
        rows.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    filled = {k: sum(1 for r in rows if r[k] not in ("", None)) for k in fields}
    print(f"Wrote {len(rows)} companies to {OUT}")
    for k in fields[4:]:
        print(f"  {k}: {filled[k]} of {len(rows)} filled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
