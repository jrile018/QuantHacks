"""Extract values (not just flags) from filing text, for three partial checklist items.

6.1  customer concentration: the actual percentage and the sentence stating it, from 10-Ks.
     XBRL cannot supply this: the concentration tag is dimensioned per customer and the
     companyfacts API drops dimensions, leaving only 1 of 168 companies with a usable value.
19.5 legal proceedings: the size of each 10-K's Item 3 discussion and which case types it
     names, so a company with real litigation is separable from one with a one-line "none".
9.6  abrupt executive departures: 8-K Item 5.02 filings whose text says the departure was
     immediate or a resignation, rather than a planned retirement or transition.

Writes:
  output/customer_concentration.csv   one row per (10-K, percentage found)
  output/legal_proceedings.csv        one row per 10-K
  output/executive_departures.csv     one row per Item 5.02 8-K with departure language

Every row keeps the matched sentence, because these are text matches and some will be wrong.
Standard library only. Read-only on the extract folder.
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
OUT = HERE / "output"
TAG_RE = re.compile(r"<[^>]+>")

# A customer above a threshold share of revenue. Captures the percent and who it refers to.
CONCENTRATION_RE = re.compile(
    r"(?P<who>(?:one|two|three|a\s+single|our\s+largest|the\s+largest|no\s+single)?\s*"
    r"(?:customer|client|reseller|distributor|partner)s?)[^.]{0,120}?"
    r"(?P<pct>\d{1,2}(?:\.\d)?)\s*%\s*(?:or\s+more\s+)?of\s+(?:our\s+)?(?:total\s+|consolidated\s+)?"
    r"(?:revenue|revenues|net\s+revenue|net\s+revenues|sales)"
    r"|(?:accounted|represented|comprised)\s+for\s+(?:approximately\s+)?(?P<pct2>\d{1,2}(?:\.\d)?)\s*%"
    r"\s+of\s+(?:our\s+)?(?:total\s+)?(?:revenue|revenues|sales)", re.I)
# Item 3 Legal Proceedings, up to the next item heading. A 10-K names Item 3 twice: once
# in the table of contents, where the "body" is just a page number, and once as the real
# section. Taking the first match gave a median body of 4 characters, so all matches are
# collected and the longest is used.
ITEM3_RE = re.compile(r"item\s*3\.?\s*[-–—:]?\s*legal\s+proceedings(?P<body>.{0,40000}?)item\s*4", re.I | re.S)


def longest_item3(text: str) -> str:
    bodies = [m.group("body") for m in ITEM3_RE.finditer(text)]
    return max(bodies, key=len) if bodies else ""
CASE_TYPES = {
    "patent": re.compile(r"patent\s+(?:infringement|litigation)", re.I),
    "securities_class_action": re.compile(r"securities\s+class\s+action", re.I),
    "shareholder_derivative": re.compile(r"derivative\s+(?:action|complaint|suit)", re.I),
    "employment": re.compile(r"(?:wage|employment|discrimination|labor)\s+(?:claim|suit|action|lawsuit)", re.I),
    "privacy_data": re.compile(r"(?:privacy|data\s+breach|biometric|BIPA)\b", re.I),
    "contract_dispute": re.compile(r"breach\s+of\s+contract", re.I),
    "antitrust": re.compile(r"antitrust", re.I),
}
NO_LITIGATION_RE = re.compile(
    r"not\s+(?:currently\s+)?(?:a\s+party|involved)[^.]{0,80}(?:material\s+)?(?:legal|litigation)"
    r"|no\s+material\s+(?:pending\s+)?legal\s+proceedings", re.I)
# Departure language. "Immediate" or a resignation reads differently from a planned retirement.
DEPARTURE = {
    "immediate": re.compile(r"effective\s+immediately|with\s+immediate\s+effect", re.I),
    "resigned": re.compile(r"(?:resigned|resignation|stepped\s+down|tendered\s+(?:his|her|their)\s+resignation)", re.I),
    "terminated": re.compile(r"(?:terminated|removed\s+from|dismissed)\s+(?:the\s+)?(?:employment|position|office)?", re.I),
    # "retire" alone matched 895 of 898 filings, because every 5.02 mentions retirement
    # plans and transition arrangements. This requires a person retiring, and the lookahead
    # keeps benefit-plan wording out.
    "planned_retirement": re.compile(
        r"(?:will\s+retire|intends?\s+to\s+retire|announced\s+(?:his|her|their)\s+retirement"
        r"|retirement\s+from\s+the\s+(?:Company|Board)|decision\s+to\s+retire)"
        r"(?!\s+(?:plan|savings|benefit|account))", re.I),
    "for_cause": re.compile(r"\bfor\s+cause\b", re.I),
}
ROLES = re.compile(r"\b(Chief\s+Executive\s+Officer|CEO|Chief\s+Financial\s+Officer|CFO|"
                   r"Chief\s+Operating\s+Officer|COO|Chief\s+Technology\s+Officer|CTO|President)\b", re.I)


def text_of(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(TAG_RE.sub(" ", raw)).split())


def sentence_at(text: str, pos: int, pad: int = 170) -> str:
    return text[max(0, pos - pad): pos + pad]


# "no customer accounted for more than 10% of revenue" states the opposite of
# concentration. Recording it as a 10% customer inverts the meaning, so each match is
# classified instead of assumed.
NEGATED_RE = re.compile(
    r"\b(?:no|none\s+of|not\s+any|nor\s+(?:any|did))\b[^.]{0,60}$", re.I)


# A bounded subject ("one customer", "two customers", "our largest customer") is a real
# concentration statement. A bare plural catches aggregate and geographic shares instead:
# Snowflake's "97% of our revenue" is a capacity-arrangement total and Procore's "14%" is
# revenue from outside the US. Filter on this column before using the percentages.
COUNTED_SUBJECT_RE = re.compile(
    r"^(?:one|two|three|four|five|a\s+single|our\s+largest|the\s+largest|no\s+single|no)\b", re.I)


def concentration_specificity(who: str) -> str:
    return "counted_or_single" if COUNTED_SUBJECT_RE.match((who or "").strip()) else "generic_plural"


def concentration_statement(text: str, start: int, who: str) -> str:
    before = text[max(0, start - 90): start] + " " + (who or "")
    if NEGATED_RE.search(before) or re.match(r"\s*no\b", who or "", re.I):
        return "no_customer_at_or_above"
    return "customer_at_or_above"


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    conc_rows, legal_rows, dep_rows = [], [], []
    for c in companies:
        ticker = (c["ticker"] or "").strip()
        if not ticker:
            continue
        base = {"cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"]}

        for form in ("10-K", "10-K_A"):
            folder = SEC / ticker / form
            if not folder.exists():
                continue
            for date, _f, doc in sec_common.filing_documents(SEC / ticker, [form]):
                t = text_of(doc)

                seen = set()
                for m in CONCENTRATION_RE.finditer(t):
                    pct = m.group("pct") or m.group("pct2")
                    if not pct:
                        continue
                    key = (date, pct)
                    if key in seen:
                        continue
                    seen.add(key)
                    who = (m.group("who") or "").strip()
                    conc_rows.append({**base, "form": form.replace("_", "/"), "filing_date": date,
                                      "statement": concentration_statement(t, m.start(), who),
                                      "specificity": concentration_specificity(who),
                                      "pct_of_revenue": float(pct),
                                      "refers_to": who[:40],
                                      "sentence": sentence_at(t, m.start())})

                body = longest_item3(t)
                row = {**base, "form": form.replace("_", "/"), "filing_date": date,
                       "item3_found": "yes" if body else "no",
                       "item3_chars": len(body),
                       "states_no_material_litigation": "yes" if body and NO_LITIGATION_RE.search(body) else "no"}
                for name, rx in CASE_TYPES.items():
                    row[f"case_{name}"] = len(rx.findall(body)) if body else ""
                legal_rows.append(row)

        for form in ("8-K", "8-K_A"):
            folder = SEC / ticker / form
            if not folder.exists():
                continue
            for _d, _f, doc in sec_common.filing_documents(SEC / ticker, [form]):
                t = text_of(doc)
                if not re.search(r"item\s*5\.02", t, re.I):
                    continue
                flags = {name: ("yes" if rx.search(t) else "no") for name, rx in DEPARTURE.items()}
                if flags["resigned"] == "no" and flags["terminated"] == "no" and flags["immediate"] == "no":
                    continue  # an appointment-only 5.02, not a departure
                roles = sorted({r.group(0).upper() for r in ROLES.finditer(t)})
                m = DEPARTURE["resigned"].search(t) or DEPARTURE["immediate"].search(t)
                dep_rows.append({**base, "form": form.replace("_", "/"),
                                 "filing_date": doc.parent.name.split("_")[0],
                                 **flags,
                                 "roles_mentioned": "; ".join(roles)[:60],
                                 "sentence": sentence_at(t, m.start()) if m else ""})

    OUT.mkdir(parents=True, exist_ok=True)
    for path, rows in (("customer_concentration.csv", conc_rows),
                       ("legal_proceedings.csv", legal_rows),
                       ("executive_departures.csv", dep_rows)):
        if not rows:
            continue
        with (OUT / path).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    pos=[r for r in conc_rows if r["statement"]=="customer_at_or_above"]
    print(f"customer_concentration: {len(conc_rows)} statements, {len({r['ticker'] for r in conc_rows})} companies")
    strict=[r for r in pos if r["specificity"]=="counted_or_single"]
    print(f"  a customer at/above the threshold: {len(pos)} statements, {len({r['ticker'] for r in pos})} companies")
    print(f"    of those, a counted/single customer: {len(strict)} statements, {len({r['ticker'] for r in strict})} companies")
    print(f"  explicitly no customer above it:   {len(conc_rows)-len(pos)} statements")
    print(f"legal_proceedings: {len(legal_rows)} filings, Item 3 found in "
          f"{sum(1 for r in legal_rows if r['item3_found'] == 'yes')}, "
          f"'no material litigation' in {sum(1 for r in legal_rows if r['states_no_material_litigation'] == 'yes')}")
    print(f"executive_departures: {len(dep_rows)} filings, {len({r['ticker'] for r in dep_rows})} companies")
    print(f"  immediate: {sum(1 for r in dep_rows if r['immediate'] == 'yes')} | "
          f"for cause: {sum(1 for r in dep_rows if r['for_cause'] == 'yes')} | "
          f"planned retirement wording: {sum(1 for r in dep_rows if r['planned_retirement'] == 'yes')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
