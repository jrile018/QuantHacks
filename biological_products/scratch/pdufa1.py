import re, pandas as pd
ev = pd.read_csv("events_8k.csv")
t = ev.supporting_text.fillna("")
hit = ev[t.str.contains(r"PDUFA|target action date|goal date", case=False, regex=True)].copy()
months = "January|February|March|April|May|June|July|August|September|October|November|December"
pat = re.compile(r"(?:PDUFA|target action date|goal date)[^.]{0,200}?((?:%s)\s+\d{1,2},\s+\d{4})" % months, re.I)
def dates(s):
    return "|".join(sorted(set(m.group(1) for m in pat.finditer(s))))
hit["pdufa_dates"] = hit.supporting_text.map(dates)
hit["snippet"] = hit.supporting_text.str.replace(r"\s+", " ", regex=True).str[:300]
hit[["tickers", "cik", "accession_number", "filing_date", "tertiary_category", "pdufa_dates", "snippet"]].to_csv("pdufa_mentions.csv", index=False)
print(len(ev), "8-K rows;", len(hit), "mention PDUFA/target action date;", (hit.pdufa_dates != "").sum(), "with an extractable date;", hit.cik.nunique(), "companies")
print(hit.tertiary_category.value_counts().head(6))
x = hit[hit.pdufa_dates != ""].sample(min(6, (hit.pdufa_dates != "").sum()), random_state=1)
for _, r in x.iterrows(): print(r.filing_date, r.tickers, "|", r.pdufa_dates, "|", r.snippet[:200])
