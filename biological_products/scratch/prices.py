import os, time, requests, pandas as pd
H = {"Authorization": "Bearer " + os.environ["MASSIVE_API_KEY"]}
tks = pd.read_csv("industries.csv").query("sic_code == 2836").ticker.tolist() + ["XBI", "SPY"]
rows = []
for n, tk in enumerate(tks):
    try:
        r = requests.get("https://api.massive.com/v2/aggs/ticker/%s/range/1/day/2020-01-01/2026-10-03" % tk, headers=H,
                         params={"adjusted": "true", "sort": "asc", "limit": 50000}, timeout=60)
        r.raise_for_status()
        for b in r.json().get("results", []):
            rows.append(dict(ticker=tk, date=pd.to_datetime(b["t"], unit="ms").date(), open=b.get("o"), high=b.get("h"),
                             low=b.get("l"), close=b.get("c"), volume=b.get("v"), n_trades=b.get("n")))
    except Exception as e:
        print("fail", tk, e)
    time.sleep(0.1)
    if n % 25 == 0: print(n, "done,", len(rows), "rows")
df = pd.DataFrame(rows)
df.to_csv("prices.csv", index=False)
print(len(df), "rows,", df.ticker.nunique(), "tickers")
print(df.groupby("ticker").date.min().describe())
