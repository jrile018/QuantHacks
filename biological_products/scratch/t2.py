import requests, pandas as pd
r = requests.get("https://api.fda.gov/drug/drugsfda.json", params={"search": "sponsor_name:gilead", "limit": 1000, "skip": 0})
print(r.status_code, len(r.json().get("results", [])))
print([a.get("sponsor_name") for a in r.json().get("results", [])][:5])
inds = pd.read_csv("industries.csv")
print(inds[inds.ticker == "GILD"].to_string())
