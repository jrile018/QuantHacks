import os, re, html, time, requests, pandas as pd
UA = {"User-Agent": os.environ["SEC_UA"]}
ev = pd.read_csv("events_8k.csv")
sel = ev[ev.tertiary_category.str.contains("result|regulatory|clinical|business_update|presentation|guidance|earnings|financial", na=False)]
f = sel.drop_duplicates("accession_number")[["accession_number", "cik", "filing_date", "tickers"]]
done = set()
if os.path.exists("pdufa_full.csv"): done = set(pd.read_csv("pdufa_full.csv", usecols=["accession_number"]).accession_number)
todo = f[~f.accession_number.isin(done)]
print(len(f), "filings selected;", len(todo), "left to fetch")
months = "January|February|March|April|May|June|July|August|September|October|November|December"
pat = re.compile(r"(PDUFA|target action date|goal date).{0,250}?((?:%s)\s+\d{1,2},\s+\d{4})" % months, re.I | re.S)
buf = []
def flush():
    global buf
    if buf:
        pd.DataFrame(buf).to_csv("pdufa_full.csv", mode="a", header=not os.path.exists("pdufa_full.csv"), index=False); buf = []
for i, r in enumerate(todo.itertuples()):
    url = "https://www.sec.gov/Archives/edgar/data/%d/%s.txt" % (int(r.cik), r.accession_number)
    dates, snip, status = "", "", "ok"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=UA, timeout=90)
            if resp.status_code in (403, 429): time.sleep(20); continue
            if resp.status_code != 200: status = "http%d" % resp.status_code; break
            txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", resp.text)))
            ms = list(pat.finditer(txt))
            dates = "|".join(sorted(set(m.group(2) for m in ms)))
            snip = txt[max(0, ms[0].start() - 100): ms[0].end() + 100] if ms else ""
            break
        except Exception as e:
            status = "err"; time.sleep(2)
    buf.append(dict(accession_number=r.accession_number, cik=r.cik, filing_date=r.filing_date, tickers=r.tickers, pdufa_dates=dates, snippet=snip, status=status))
    time.sleep(0.5)
    if (i + 1) % 100 == 0: flush(); print(i + 1, "of", len(todo))
flush()
d = pd.read_csv("pdufa_full.csv")
print(len(d), "filings checked;", (d.pdufa_dates.fillna("") != "").sum(), "with a PDUFA date;", d[d.pdufa_dates.fillna("") != ""].cik.nunique(), "companies;", d.status.value_counts().to_dict())
