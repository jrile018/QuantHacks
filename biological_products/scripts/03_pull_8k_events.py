import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
import os, time, requests, pandas as pd
H = {"Authorization": "Bearer " + os.environ["MASSIVE_API_KEY"]}
tks = pd.read_csv(P("industries.csv")).query("sic_code == 2836").ticker.tolist()
rows = []
for tk in tks:
    url = "https://api.massive.com/stocks/filings/8-K/vX/disclosures"
    params = {"tickers": tk, "limit": 1000}
    while url:
        try:
            r = requests.get(url, headers=H, params=params, timeout=60)
            r.raise_for_status(); j = r.json()
        except Exception as e:
            print("fail", tk, e); break
        rows += j.get("results", [])
        url = j.get("next_url"); params = None
        time.sleep(0.1)
df = pd.DataFrame(rows)
df.to_csv(P("events_8k.csv"), index=False)
print(len(df), "rows")
print(df.tertiary_category.value_counts().head(15))
