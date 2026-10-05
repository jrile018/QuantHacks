import os, time, requests, pandas as pd
H = {"Authorization": "Bearer " + os.environ["MASSIVE_API_KEY"]}
tks = pd.read_csv("industries.csv").query("sic_code == 2836").ticker.tolist()
rows = []
for n, tk in enumerate(tks):
    url = "https://api.massive.com/v2/reference/news"
    params = {"ticker": tk, "limit": 1000, "order": "asc", "published_utc.gte": "2020-01-01"}
    while url:
        try:
            r = requests.get(url, headers=H, params=params, timeout=60)
            r.raise_for_status(); j = r.json()
        except Exception as e:
            print("fail", tk, e); break
        for a in j.get("results", []):
            ins = next((i for i in (a.get("insights") or []) if i.get("ticker") == tk), {})
            rows.append(dict(ticker=tk, published_utc=a.get("published_utc"), title=a.get("title"),
                publisher=(a.get("publisher") or {}).get("name"), url=a.get("article_url"),
                description=a.get("description"), n_tickers=len(a.get("tickers") or []),
                sentiment=ins.get("sentiment"), reasoning=ins.get("sentiment_reasoning")))
        url = j.get("next_url"); params = None
        time.sleep(0.1)
    if n % 20 == 0: print(n, "tickers done,", len(rows), "rows")
df = pd.DataFrame(rows)
df.to_csv("news.csv", index=False)
df["year"] = df.published_utc.str[:4]
print(len(df), "rows,", df.ticker.nunique(), "tickers")
print(df.groupby("year").agg(articles=("title", "count"), tagged=("sentiment", lambda s: s.notna().sum())))
print(df.sentiment.value_counts())
