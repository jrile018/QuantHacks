import os, requests, pandas as pd
UA = {"User-Agent": os.environ["SEC_UA"]}
inds = set(pd.read_csv("industries.csv").query("sic_code == 2836").ticker)
for cik in [1832038, 1708527, 1824893, 1662774, 1213809, 1855644, 1497253]:
    j = requests.get("https://data.sec.gov/submissions/CIK%010d.json" % cik, headers=UA, timeout=60).json()
    print(cik, j.get("name"), "| tickers:", j.get("tickers"), "| in your list:", [t for t in j.get("tickers", []) if t in inds])
