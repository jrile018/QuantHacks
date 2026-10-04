"""Link federal contract awards to the 8-K filings that announce them.

For each exact-name federal award, look for 8-K or 8-K/A filings by the same company within
a window around the award's start date, and keep a link only when the filing text supports
it. A date match alone is not enough, since companies file many 8-Ks; a link needs the award
amount (in $ millions or the full dollar figure) or the awarding agency to appear in the
filing or in its linked press-release exhibit.

Match levels:
  amount_and_agency   both the amount and the agency appear
  amount              the amount appears
  agency_and_contract the agency appears with the word "contract" in the same filing
  none                no supporting text in the window (the award was not announced by 8-K)

Writes:
  output/award_8k_links.csv     one row per award, with the best linked filing and match level
  output/award_8k_summary.csv   counts by match level, overall and by company

Standard library only. Read-only on the extract folder.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import re
from collections import Counter, defaultdict
from pathlib import Path

import sec_common

HERE = Path(__file__).resolve().parent
SEC = HERE / "extracts" / "sec"
OUT = HERE / "output"
COMPANIES = HERE / "packaged_software_companies.csv"
WINDOW_BEFORE = 10     # days before the award start that still count
WINDOW_AFTER = 30      # days after the award start
TAG_RE = re.compile(r"<[^>]+>")


def text_of(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(TAG_RE.sub(" ", raw)).split())


def amount_forms(amount: float) -> list[str]:
    """How the award amount might be written in a filing: full dollars, or millions."""
    forms = []
    if amount >= 1_000_000:
        millions = amount / 1_000_000
        forms.append(f"${millions:,.1f} million")
        forms.append(f"${millions:,.0f} million")
    forms.append(f"${amount:,.0f}")
    return forms


def agency_terms(agency: str) -> list[str]:
    """Short forms of an awarding agency that a filing would plausibly use."""
    terms = {agency.lower()}
    for key, short in (("Department of Defense", "Defense"), ("Department of Homeland Security", "Homeland Security"),
                       ("Department of Veterans Affairs", "Veterans"), ("General Services Administration", "General Services"),
                       ("Department of Energy", "Energy"), ("Department of Health", "Health"),
                       ("Department of the Army", "Army"), ("Department of the Navy", "Navy"),
                       ("Department of the Air Force", "Air Force"), ("National Aeronautics", "NASA")):
        if key.lower() in agency.lower():
            terms.add(short.lower())
    return sorted(t for t in terms if len(t) >= 4)


def main() -> int:
    # Join on CIK, not name: the award file's recipient names do not match the universe's
    # names, which dropped most awards before any filing was checked.
    cik_to_ticker = {c["cik"].zfill(10): c["ticker"] for c in csv.DictReader(COMPANIES.open(encoding="utf-8")) if c["ticker"]}
    ticker_by_name = {c["name"]: c["ticker"] for c in csv.DictReader(COMPANIES.open(encoding="utf-8")) if c["ticker"]}
    awards = [r for r in csv.DictReader((OUT / "contract_awards.csv").open(encoding="utf-8"))
              if r.get("exact_name_match") in ("True", "true", "1") and r.get("start_date")]
    for r in awards:
        r["ticker"] = cik_to_ticker.get(r["cik"].zfill(10), "")
    awards = [r for r in awards if r["ticker"]]
    print(f"{len(awards)} exact-name awards with a start date, for {len({r['ticker'] for r in awards})} companies")

    # Each company's 8-K filings: date, folder, and the text of the filing plus its exhibits
    filings: dict[str, list[tuple[dt.date, str, str]]] = defaultdict(list)
    for name, ticker in ticker_by_name.items():
        for form in ("8-K", "8-K_A"):
            base = SEC / ticker / form
            if not base.exists():
                continue
            for folder in sorted(base.iterdir()):
                if not folder.is_dir():
                    continue
                date = dt.date.fromisoformat(folder.name.split("_")[0])
                main_doc = sec_common.primary_document(folder)
                parts = []
                if main_doc:
                    parts.append(text_of(main_doc))
                for ex in folder.iterdir():
                    if ex.is_file() and ex != main_doc and re.search(r"ex[-_]?99|press", ex.name, re.I):
                        parts.append(text_of(ex))
                filings[ticker].append((date, folder.name, " ".join(parts)))

    rows = []
    for a in awards:
        ticker = a["ticker"]
        start = dt.date.fromisoformat(a["start_date"])
        amount = float(a["award_amount"] or 0)
        agency = a.get("awarding_agency", "")
        lo, hi = start - dt.timedelta(days=WINDOW_BEFORE), start + dt.timedelta(days=WINDOW_AFTER)
        best = ("none", "", "")
        for date, folder, text in filings.get(ticker, []):
            if not (lo <= date <= hi):
                continue
            low = text.lower()
            has_amount = any(f.lower() in low for f in amount_forms(amount)) if amount else False
            has_agency = any(t in low for t in agency_terms(agency))
            if has_amount and has_agency:
                level = "amount_and_agency"
            elif has_amount:
                level = "amount"
            elif has_agency and "contract" in low:
                level = "agency_and_contract"
            else:
                continue
            rank = ["none", "agency_and_contract", "amount", "amount_and_agency"].index(level)
            if rank > ["none", "agency_and_contract", "amount", "amount_and_agency"].index(best[0]):
                best = (level, str(date), folder)
        rows.append({
            "ticker": ticker, "company_name": a.get("company_name", ""), "award_id": a["award_id"],
            "start_date": a["start_date"], "award_amount": amount, "awarding_agency": agency,
            "match_level": best[0], "linked_8k_date": best[1], "linked_8k_folder": best[2],
        })

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "award_8k_links.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["ticker"], r["start_date"])))

    levels = Counter(r["match_level"] for r in rows)
    by_company = defaultdict(Counter)
    for r in rows:
        by_company[r["ticker"]][r["match_level"]] += 1
    with (OUT / "award_8k_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "awards", "amount_and_agency", "amount", "agency_and_contract", "none"])
        for t in sorted(by_company):
            c = by_company[t]
            w.writerow([t, sum(c.values())] + [c.get(k, 0) for k in
                       ("amount_and_agency", "amount", "agency_and_contract", "none")])

    total = len(rows)
    print(f"\n{total} awards")
    for k in ("amount_and_agency", "amount", "agency_and_contract", "none"):
        print(f"  {k:20} {levels.get(k, 0):>5}  ({100 * levels.get(k, 0) / total:.0f}%)")
    linked = total - levels.get("none", 0)
    dollars = sum(r["award_amount"] for r in rows)
    dollars_linked = sum(r["award_amount"] for r in rows if r["match_level"] != "none")
    print(f"linked to an 8-K: {linked} awards, ${dollars_linked/1e9:.2f}B of ${dollars/1e9:.2f}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
