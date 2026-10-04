"""Text flags from every 10-K / 10-K/A on disk, one row per filing (2022 onward).

build_filing_signals.py flags only each company's latest 10-K. This covers the whole
timeline, so a flag can be tracked from year to year.

Reads data/packaged_software/extracts/sec/<TICKER>/10-K/ and 10-K_A/ and writes:
  output/tenk_text_flags.csv       one row per filing, with a count per flag
  output/tenk_flag_snippets.csv    one snippet per (filing, flag) so matches can be checked

Flags are keyword matches, not verified findings. The snippets file exists so a sample
can be read before any flag is used in analysis.
Standard library only, read-only on the extract folder.
"""

from __future__ import annotations

import csv
import html
import re
from pathlib import Path

import sec_common

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT_FLAGS = HERE / "output" / "tenk_text_flags.csv"
OUT_SNIPS = HERE / "output" / "tenk_flag_snippets.csv"
TAG_RE = re.compile(r"<[^>]+>")

FLAGS = {
    # Section 8: cyber governance disclosure, required in 10-Ks for FY2023 onward
    "item_1c_cyber_section": re.compile(r"item\s*1c\b", re.I),
    # Section 3: distress language. "substantial doubt" is the accounting trigger phrase
    "substantial_doubt_going_concern": re.compile(r"substantial\s+doubt[^.]{0,120}going\s+concern", re.I),
    "going_concern_any_mention": re.compile(r"going\s+concern", re.I),
    # Section 9: internal control problems.
    # The bare phrases "material weakness" and "restatement" appear in nearly every 10-K's
    # risk factors ("if we identify a material weakness..."), so these require the company
    # to be describing its own actual finding, not a hypothetical.
    "material_weakness_any_mention": re.compile(r"material\s+weakness", re.I),
    "material_weakness_identified": re.compile(
        r"(?:we|the\s+company|management)\s+(?:have|has|had|identified|concluded|determined)"
        r"[^.]{0,120}material\s+weakness(?:es)?"
        r"|material\s+weakness(?:es)?\s+(?:in\s+our\s+internal\s+control[^.]{0,60})?"
        r"(?:was|were|has\s+been|have\s+been)\s+identified", re.I),
    "restatement_any_mention": re.compile(r"restate(?:d|ment)", re.I),
    "restated_own_financials": re.compile(
        r"restate(?:d|ment)\s+of\s+(?:our|the\s+company's|its)\s+(?:previously\s+issued\s+)?"
        r"(?:consolidated\s+)?financial\s+statements"
        r"|(?:we|the\s+company)\s+(?:have\s+)?restated\s+(?:our|its)", re.I),
    # Section 6: customer concentration
    "customer_pct_of_revenue": re.compile(
        r"(?:accounted|represent(?:ed|s)?)\s+(?:for\s+)?(?:approximately\s+)?(?:more\s+than\s+)?"
        r"\d{1,2}(?:\.\d)?%\s+of\s+(?:our\s+)?(?:total\s+)?(?:revenue|net revenue|revenues)", re.I),
    # Section 19: AI-mention intensity
    "artificial_intelligence": re.compile(r"artificial\s+intelligence|machine\s+learning", re.I),
    # Section 18: cloud cost proxies
    "cloud_provider_mention": re.compile(r"amazon\s+web\s+services|\bAWS\b|microsoft\s+azure|google\s+cloud", re.I),
    # Section 10: litigation
    "patent_infringement": re.compile(r"patent\s+infringement", re.I),
    "securities_class_action_any_mention": re.compile(r"(?:securities|shareholder)\s+class\s+action", re.I),
    "class_action_filed_against_company": re.compile(
        r"class\s+action[^.]{0,120}(?:filed|commenced|brought)\s+against\s+(?:us|the\s+company)"
        r"|(?:filed|commenced|brought)[^.]{0,80}class\s+action[^.]{0,60}against\s+(?:us|the\s+company)", re.I),
}


def read_text(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(TAG_RE.sub(" ", raw)).split())


# Spot-checking the strict flags showed two kinds of surviving false positive:
#  1. conditional risk-factor language ("If we have a material weakness...",
#     "could result in a restatement of our financial statements")
#  2. compensation clawback policies, which describe a restatement as a trigger
#     ("the date a restatement of our financial statements was determined")
# Matches whose preceding text carries either marker are not counted as findings.
CONDITIONAL_RE = re.compile(
    r"\b(if|could|may|might|would|should|unless|in\s+the\s+event|risk\s+that|failure\s+to|"
    r"were\s+to|any\s+such|potential(?:ly)?|possibility)\b", re.I)
CLAWBACK_RE = re.compile(
    r"\b(clawback|claw\s*back|recoupment|recovery\s+policy|incentive\s+compensation|"
    r"erroneously\s+awarded|repayment)\b", re.I)
# How far back to look for those markers. One clause, not a whole paragraph.
LOOKBACK = 140

# Flags where a hypothetical mention is a false positive, not a weaker finding
CONTEXT_CHECKED = {"material_weakness_identified", "restated_own_financials",
                   "class_action_filed_against_company", "substantial_doubt_going_concern"}


def is_hypothetical(text: str, start: int, flag: str) -> bool:
    before = text[max(0, start - LOOKBACK): start]
    if CONDITIONAL_RE.search(before):
        return True
    if flag == "restated_own_financials" and CLAWBACK_RE.search(before):
        return True
    return False


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    flag_rows: list[dict] = []
    snip_rows: list[dict] = []
    for c in companies:
        ticker = (c["ticker"] or c["cik"]).strip()
        for form_dir in ("10-K", "10-K_A"):
            base = SEC / ticker / form_dir
            if not base.exists():
                continue
            for doc in sec_common.filing_documents(SEC / ticker, [form_dir]):
                doc = doc[2]
                folder = doc.parent.name
                text = read_text(doc)
                row = {
                    "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                    "form": form_dir.replace("_", "/"),
                    "filing_date": folder.split("_")[0], "filing_folder": folder,
                    "text_chars": len(text),
                }
                for flag, rx in FLAGS.items():
                    hits = list(rx.finditer(text))
                    if flag in CONTEXT_CHECKED:
                        kept = [m for m in hits if not is_hypothetical(text, m.start(), flag)]
                        row[flag] = len(kept)
                        row[f"{flag}_hypothetical_dropped"] = len(hits) - len(kept)
                    else:
                        kept = hits
                        row[flag] = len(hits)
                    if kept:
                        m = kept[0]
                        snip_rows.append({
                            "ticker": ticker, "filing_date": row["filing_date"], "flag": flag,
                            "snippet": text[max(0, m.start() - 150): m.start() + 250],
                            "local_path": str(doc.relative_to(ROOT)).replace("\\", "/"),
                        })
                flag_rows.append(row)

    OUT_FLAGS.parent.mkdir(parents=True, exist_ok=True)
    fields = (["cik", "ticker", "name", "form", "filing_date", "filing_folder", "text_chars"]
              + list(FLAGS) + [f"{f}_hypothetical_dropped" for f in FLAGS if f in CONTEXT_CHECKED])
    with OUT_FLAGS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(flag_rows)
    with OUT_SNIPS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "filing_date", "flag", "snippet", "local_path"])
        w.writeheader()
        w.writerows(snip_rows)

    years = sorted({r["filing_date"][:4] for r in flag_rows})
    print(f"Wrote {len(flag_rows)} filings for {len({r['ticker'] for r in flag_rows})} companies, years {years}")
    for flag in FLAGS:
        filings = sum(1 for r in flag_rows if r[flag])
        companies_with = len({r["ticker"] for r in flag_rows if r[flag]})
        print(f"  {flag}: {filings} filings, {companies_with} companies")
    print(f"Snippets for checking: {len(snip_rows)} in {OUT_SNIPS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
