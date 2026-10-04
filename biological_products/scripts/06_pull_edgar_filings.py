import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
import os, time, requests, pandas as pd
UA = {"User-Agent": os.environ["SEC_UA"]}
ciks = sorted(pd.read_csv(P("events_8k.csv")).cik.dropna().astype("int64").unique())
rows = []
def add(b, cik):
    items = b.get("items", [""] * len(b["form"]))
    for i in range(len(b["form"])):
        if b["filingDate"][i] >= "2019-06-01":
            rows.append(dict(cik=cik, form=b["form"][i], filing_date=b["filingDate"][i], accession=b["accessionNumber"][i], items=items[i]))
for n, cik in enumerate(ciks):
    try:
        r = requests.get("https://data.sec.gov/submissions/CIK%010d.json" % cik, headers=UA, timeout=60); r.raise_for_status()
        j = r.json(); add(j["filings"]["recent"], cik)
        for f in j["filings"].get("files", []):
            if f.get("filingTo", "9999") >= "2019-06-01":
                time.sleep(0.15)
                rr = requests.get("https://data.sec.gov/submissions/" + f["name"], headers=UA, timeout=60); rr.raise_for_status()
                add(rr.json(), cik)
    except Exception as e:
        print("fail", cik, e)
    time.sleep(0.15)
    if n % 25 == 0: print(n, "done,", len(rows), "rows")
df = pd.DataFrame(rows)
df.to_csv(P("edgar_filings.csv"), index=False)
print(len(df), "filings,", df.cik.nunique(), "companies")
print(df.form.value_counts().head(15))
