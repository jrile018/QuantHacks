import pandas as pd, numpy as np
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
n = pd.read_csv("news.csv").drop_duplicates(["ticker", "url"])
sia = SentimentIntensityAnalyzer()
txt = (n.title.fillna("") + ". " + n.description.fillna("")).tolist()
n["vader"] = [sia.polarity_scores(t)["compound"] for t in txt]
n["pub"] = pd.to_datetime(n.published_utc.str[:10])
n.to_csv("news_scored.csv", index=False)

t = n[n.sentiment.isin(["positive", "negative", "neutral"])].copy()
t["pred"] = np.where(t.vader > 0.05, "positive", np.where(t.vader < -0.05, "negative", "neutral"))
print("agreement with Massive tags:", round((t.pred == t.sentiment).mean(), 2), "on", len(t), "articles")
print(pd.crosstab(t.sentiment, t.pred))

fm = pd.read_csv("feature_matrix.csv"); fm["filing_date"] = pd.to_datetime(fm.filing_date); fm["eid"] = fm.index
m = fm[["eid", "ticker", "filing_date"]].merge(n[["ticker", "pub", "vader"]], on="ticker")
m = m[(m.pub < m.filing_date) & (m.pub >= m.filing_date - pd.Timedelta(days=30))]
m["d7"] = m.pub >= m.filing_date - pd.Timedelta(days=7)
a30 = m.groupby("eid").agg(news_n_30d=("vader", "count"), news_sent_30d=("vader", "mean"))
a7 = m[m.d7].groupby("eid").agg(news_n_7d=("vader", "count"), news_sent_7d=("vader", "mean"))
fm = fm.merge(a30, on="eid", how="left").merge(a7, on="eid", how="left")
cnt = ["news_n_7d", "news_n_30d"]; allc = cnt + ["news_sent_7d", "news_sent_30d"]
fm[cnt] = fm[cnt].fillna(0)
fm.loc[fm.filing_date < "2021-02-01", allc] = np.nan
fm.drop(columns="eid").to_csv("feature_matrix_v2.csv", index=False)
print(fm.shape)
print(fm[allc].describe().round(2))
