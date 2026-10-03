import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
import os, re, time, requests, pandas as pd
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
UA = {"User-Agent": os.environ["SEC_UA"]}
e = pd.read_csv(P("edgar_filings.csv")); e = e[e.form == "4"]
done = set()
if os.path.exists(P("form4_tx.csv")): done = set(pd.read_csv(P("form4_tx.csv"), usecols=["accession"]).accession)
todo = e[~e.accession.isin(done)]
print(len(todo), "Form 4 filings to fetch")

def tx(el, path):
    x = el.find(path)
    return x.text if x is not None else None

def fetch(row):
    cik, acc, fd = row
    url = "https://www.sec.gov/Archives/edgar/data/%d/%s.txt" % (cik, acc)
    out = []
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code in (403, 429): time.sleep(15); continue
            if r.status_code != 200: out = [dict(cik=cik, accession=acc, filing_date=fd, code="ERR")]; break
            m = re.search(r"<ownershipDocument>.*?</ownershipDocument>", r.text, re.S)
            if m:
                root = ET.fromstring(m.group(0))
                rel = root.find("reportingOwner/reportingOwnerRelationship")
                off = tx(rel, "isOfficer") if rel is not None else None
                dire = tx(rel, "isDirector") if rel is not None else None
                title = tx(rel, "officerTitle") if rel is not None else None
                for t in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
                    code = tx(t, "transactionCoding/transactionCode")
                    if code in ("P", "S"):
                        out.append(dict(cik=cik, accession=acc, filing_date=fd, code=code,
                                        shares=tx(t, "transactionAmounts/transactionShares/value"),
                                        price=tx(t, "transactionAmounts/transactionPricePerShare/value"),
                                        is_officer=off, is_director=dire, title=title))
            if not out: out = [dict(cik=cik, accession=acc, filing_date=fd, code="NONE")]
            break
        except Exception:
            out = [dict(cik=cik, accession=acc, filing_date=fd, code="ERR")]
            time.sleep(1)
    time.sleep(0.35)
    return out

rows = list(zip(todo.cik.astype("int64"), todo.accession, todo.filing_date))
with ThreadPoolExecutor(4) as pool:
    for i in range(0, len(rows), 400):
        res = [x for chunk in pool.map(fetch, rows[i:i+400]) for x in chunk]
        pd.DataFrame(res).to_csv(P("form4_tx.csv"), mode="a", header=not os.path.exists(P("form4_tx.csv")), index=False)
        print(min(i + 400, len(rows)), "of", len(rows), "done")
d = pd.read_csv(P("form4_tx.csv"))
print(d.code.value_counts())
