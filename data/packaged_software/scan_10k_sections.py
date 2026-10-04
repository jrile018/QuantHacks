"""Section-level 10-K analysis: risk-factor change, MD&A tone, and the mention network.

Covers three checklist items from filings already on disk:
  19.2  risk-factor changes over time   Item 1A compared with the same company's prior 10-K
  19.4  MD&A tone                       Item 7 scored with a word list
  14.2  10-K mention network            which universe companies name each other

Section extraction takes the longest match for each item heading, because a 10-K names
every item twice: once in the table of contents, where the "section" is a page number, and
once as the real section.

Risk-factor change is the Jaccard distance between the two years' sentence sets: 0 means
the section is unchanged, 1 means entirely rewritten. Sentences are compared rather than
words so that reordering a paragraph does not read as a rewrite.

Tone uses a small built-in finance word list. This is NOT the Loughran-McDonald dictionary,
which the project plans to version separately; treat the tone columns as a rough indicator
and not as a validated measure. The counts are reported raw so they can be rescaled.

Mention matching reuses the rules the enforcement and Federal Register scans needed: word
boundaries, and a single short word is matched only with its legal suffix, because "Block",
"Box" and "Aware" otherwise match ordinary prose.

Writes:
  output/tenk_sections.csv        one row per 10-K: section sizes, tone counts, change score
  output/tenk_mention_network.csv one row per (filer, mentioned company, filing)
Standard library only. Read-only on the extract folder.
"""

from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from pathlib import Path

import sec_common

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = HERE / "output"
TAG_RE = re.compile(r"<[^>]+>")
SUFFIX_RE = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|the)\b\.?", re.I)
SECURITY_RE = re.compile(
    r"\s*(?:Class\s+[A-Z]\s+)?(?:Common\s+Stock|Common\b|Ordinary\s+Shares?|Capital\s+Stock|"
    r"subordinate\s+voting\s+shares?|Warrants?|Units?)\s*$", re.I)
MIN_SINGLE_TOKEN = 10

SECTIONS = {
    "item_1a_risk_factors": (r"item\s*1a\.?\s*[-–—:]?\s*risk\s+factors", r"item\s*1b|item\s*2\b"),
    "item_7_mda": (r"item\s*7\.?\s*[-–—:]?\s*management['’]?s?\s+discussion", r"item\s*7a|item\s*8\b"),
}

# A deliberately small finance word list. Not Loughran-McDonald; see the module docstring.
POSITIVE = {"growth", "growing", "strong", "strength", "improved", "improvement", "increase",
            "increased", "favorable", "gain", "gains", "profitable", "profitability", "success",
            "successful", "efficient", "efficiency", "opportunity", "opportunities", "record",
            "expansion", "exceeded", "outperformed", "accelerated", "robust"}
NEGATIVE = {"decline", "declined", "decrease", "decreased", "weak", "weakness", "loss", "losses",
            "adverse", "adversely", "unfavorable", "impairment", "deterioration", "shortfall",
            "litigation", "restructuring", "downturn", "volatile", "volatility", "uncertain",
            "uncertainty", "risk", "risks", "failure", "failed", "delay", "delays", "breach",
            "default", "difficult", "challenging", "headwind", "headwinds"}
UNCERTAIN = {"may", "might", "could", "possibly", "uncertain", "approximate", "approximately",
             "believe", "believes", "expect", "expects", "estimate", "estimates", "assume",
             "assumes", "depend", "depends", "unpredictable"}
WORD_RE = re.compile(r"[a-z']{2,}")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def text_of(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(TAG_RE.sub(" ", raw)).split())


def longest_section(text: str, start_pat: str, end_pat: str) -> str:
    best = ""
    for m in re.finditer(start_pat, text, re.I):
        tail = text[m.end(): m.end() + 400000]
        stop = re.search(end_pat, tail, re.I)
        body = tail[: stop.start()] if stop else tail
        if len(body) > len(best):
            best = body
    return best


def sentence_set(text: str) -> set[str]:
    """Normalized sentences for year-to-year comparison.

    Digits are dropped before comparing. Risk factors are largely carried forward with the
    year and figures updated, so keeping numbers made almost every sentence differ and
    pushed the median change to 0.43, which reads as a rewrite when nothing material moved.
    """
    out = set()
    for s in SENTENCE_RE.split(text):
        norm = " ".join(WORD_RE.findall(s.lower()))
        if len(norm) > 40:      # skip fragments and headings
            out.add(norm)
    return out


# A change score needs a real section on both sides. A filing whose Item 1A came out tiny
# (smaller reporting companies may omit risk factors) would otherwise score 1.0 and read as
# a complete rewrite when the extraction simply found nothing.
MIN_SENTENCES_FOR_CHANGE = 30


def jaccard_distance(a: set[str], b: set[str]) -> float | None:
    if not a or not b:
        return None
    return round(1 - len(a & b) / len(a | b), 4)


def tone_counts(text: str) -> dict[str, int]:
    words = WORD_RE.findall(text.lower())
    return {
        "words": len(words),
        "positive_words": sum(1 for w in words if w in POSITIVE),
        "negative_words": sum(1 for w in words if w in NEGATIVE),
        "uncertain_words": sum(1 for w in words if w in UNCERTAIN),
    }


def mention_patterns(name: str) -> tuple[re.Pattern | None, re.Pattern | None]:
    """(with_suffix, bare) patterns for a company name.

    Both are returned so a match can say which form it found. The bare form alone is
    unreliable for names that are ordinary phrases: "Quantum Computing Inc." reduces to
    "Quantum Computing", which matched eight filings simply discussing the technology.
    Filtering to with-suffix matches gives the precise network; the bare count is kept
    because a genuine mention often omits the suffix ("Atlassian", "Salesforce").
    """
    cleaned = " ".join(SECURITY_RE.sub("", name).strip().rstrip(",").split())
    bare = " ".join(SUFFIX_RE.sub(" ", cleaned).split())
    with_suffix = re.compile(rf"\b{re.escape(cleaned)}", re.I) if cleaned else None
    bare_pat = None
    if bare and (len(bare.split()) >= 2 or len(bare) >= MIN_SINGLE_TOKEN):
        bare_pat = re.compile(rf"\b{re.escape(bare)}\b", re.I)
    return with_suffix, bare_pat


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    patterns = []
    for c in companies:
        with_suffix, bare = mention_patterns(c["name"])
        if with_suffix is not None or bare is not None:
            patterns.append((c["ticker"], c["name"], with_suffix, bare))
    print(f"{len(patterns)} of {len(companies)} companies have a matchable name")

    section_rows, mention_rows = [], []
    prior: dict[str, tuple[str, set[str]]] = {}
    for c in companies:
        ticker = (c["ticker"] or "").strip()
        if not ticker:
            continue
        docs = sec_common.filing_documents(SEC / ticker, ["10-K", "10-K_A"])
        for date, form, doc in docs:
            t = text_of(doc)
            row = {"cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                   "form": form, "filing_date": date, "document_chars": len(t)}
            risk = longest_section(t, *SECTIONS["item_1a_risk_factors"])
            mda = longest_section(t, *SECTIONS["item_7_mda"])
            row["risk_factors_chars"] = len(risk)
            row["mda_chars"] = len(mda)
            for k, v in tone_counts(mda).items():
                row[f"mda_{k}"] = v
            if row["mda_words"]:
                row["mda_net_tone_per_1k_words"] = round(
                    1000 * (row["mda_positive_words"] - row["mda_negative_words"]) / row["mda_words"], 2)
                row["mda_uncertainty_per_1k_words"] = round(
                    1000 * row["mda_uncertain_words"] / row["mda_words"], 2)
            else:
                row["mda_net_tone_per_1k_words"] = ""
                row["mda_uncertainty_per_1k_words"] = ""
            sentences = sentence_set(risk)
            row["risk_factor_sentences"] = len(sentences)
            prev = prior.get(ticker)
            row["prior_filing_date"] = prev[0] if prev else ""
            row["risk_factor_change_vs_prior"] = ""
            row["risk_sentences_added"] = ""
            row["risk_sentences_removed"] = ""
            row["change_score_note"] = ""
            if not prev:
                row["change_score_note"] = "no_prior_filing"
            elif len(sentences) < MIN_SENTENCES_FOR_CHANGE or len(prev[1]) < MIN_SENTENCES_FOR_CHANGE:
                row["change_score_note"] = (
                    f"section_too_small_to_compare (this={len(sentences)}, prior={len(prev[1])})")
            else:
                row["risk_factor_change_vs_prior"] = jaccard_distance(sentences, prev[1]) or ""
                row["risk_sentences_added"] = len(sentences - prev[1])
                row["risk_sentences_removed"] = len(prev[1] - sentences)
            if sentences:
                prior[ticker] = (date, sentences)
            section_rows.append(row)

            for other_ticker, other_name, with_suffix, bare in patterns:
                if other_ticker == ticker:
                    continue
                n_suffix = len(with_suffix.findall(t)) if with_suffix else 0
                n_bare = len(bare.findall(t)) if bare else 0
                if n_suffix or n_bare:
                    mention_rows.append({
                        "filer_cik": c["cik"].zfill(10), "filer_ticker": ticker,
                        "filing_date": date, "form": form,
                        "mentioned_ticker": other_ticker, "mentioned_name": other_name,
                        "mentions_with_legal_suffix": n_suffix,
                        "mentions_bare_name": n_bare,
                        "match_form": "with_suffix" if n_suffix else "bare_name_only",
                    })

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "tenk_sections.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(section_rows[0].keys()))
        w.writeheader()
        w.writerows(section_rows)
    with (OUT / "tenk_mention_network.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filer_cik", "filer_ticker", "filing_date", "form",
                                          "mentioned_ticker", "mentioned_name",
                                          "mentions_with_legal_suffix", "mentions_bare_name",
                                          "match_form"])
        w.writeheader()
        w.writerows(mention_rows)

    with_risk = sum(1 for r in section_rows if r["risk_factors_chars"])
    with_mda = sum(1 for r in section_rows if r["mda_chars"])
    with_change = sum(1 for r in section_rows if r["risk_factor_change_vs_prior"] != "")
    print(f"tenk_sections: {len(section_rows)} filings | Item 1A found {with_risk} | "
          f"Item 7 found {with_mda} | change score {with_change}")
    strict = [r for r in mention_rows if r["match_form"] == "with_suffix"]
    edges = {(r["filer_ticker"], r["mentioned_ticker"]) for r in mention_rows}
    strict_edges = {(r["filer_ticker"], r["mentioned_ticker"]) for r in strict}
    print(f"mention network: {len(mention_rows)} rows, {len(edges)} pairs, "
          f"{len({r['filer_ticker'] for r in mention_rows})} filers naming someone")
    print(f"  named with a legal suffix (precise): {len(strict)} rows, {len(strict_edges)} pairs")
    changed = [r for r in section_rows if r["risk_factor_change_vs_prior"] != ""]
    if changed:
        vals = sorted(float(r["risk_factor_change_vs_prior"]) for r in changed)
        print(f"  risk-factor change scored for {len(changed)} filings, median {vals[len(vals)//2]:.3f}")
    skipped = sum(1 for r in section_rows if str(r.get("change_score_note", "")).startswith("section_too_small"))
    print(f"  change score withheld, section too small: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
