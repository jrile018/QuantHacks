import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
import json, glob, os, pandas as pd
TAGS = ["CashAndCashEquivalentsAtCarryingValue","ResearchAndDevelopmentExpense","NetIncomeLoss","NetCashProvidedByUsedInOperatingActivities","Assets","Liabilities","StockholdersEquity"]
inds = pd.read_csv(P("industries.csv"))
rows = []
for f in glob.glob(os.path.join(P("companyfacts"), "*.json")):
    base = os.path.basename(f)
    j = json.load(open(f, encoding="utf-8"))
    gaap = j.get("facts", {}).get("us-gaap", {})
    tk = None
    for t in TAGS:
        for u in gaap.get(t, {}).get("units", {}).get("USD", []):
            rows.append(dict(file=base, entity=j.get("entityName"), cik=j.get("cik"), tag=t,
                start=u.get("start"), end=u.get("end"), val=u.get("val"),
                form=u.get("form"), fp=u.get("fp"), filed=u.get("filed")))
df = pd.DataFrame(rows)
df.to_csv(P("facts_long.csv"), index=False)
print(len(df), "rows,", df.cik.nunique(), "companies")
print(df.groupby("tag").cik.nunique())
