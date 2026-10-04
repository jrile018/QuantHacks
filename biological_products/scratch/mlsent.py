import pandas as pd, numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import accuracy_score, f1_score
n = pd.read_csv("news_scored.csv"); n["text"] = n.title.fillna("") + ". " + n.description.fillna("")
tr = n[n.sentiment.isin(["positive", "negative", "neutral"])].copy()
pipe = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True, stop_words="english"),
                     LogisticRegression(max_iter=2000, class_weight="balanced"))
oof = cross_val_predict(pipe, tr.text, tr.sentiment, groups=tr.url, cv=GroupKFold(n_splits=5), method="predict_proba")
cls = np.array(["negative", "neutral", "positive"]); pred = cls[oof.argmax(1)]
print("out-of-fold accuracy:", round(accuracy_score(tr.sentiment, pred), 2), "| macro F1:", round(f1_score(tr.sentiment, pred, average="macro"), 2),
      "| guess-majority baseline:", round(tr.sentiment.value_counts(normalize=True).max(), 2))
print(pd.crosstab(tr.sentiment, pred))
pipe.fit(tr.text, tr.sentiment)
P = pipe.predict_proba(n.text)
n["ml_sent"] = P[:, 2] - P[:, 0]
n.loc[tr.index, "ml_sent"] = oof[:, 2] - oof[:, 0]
n.drop(columns="text").to_csv("news_scored.csv", index=False)

fm = pd.read_csv("feature_matrix.csv"); fm["filing_date"] = pd.to_datetime(fm.filing_date); fm["eid"] = fm.index
n["pub"] = pd.to_datetime(n.pub)
m = fm[["eid", "ticker", "filing_date"]].merge(n[["ticker", "pub", "ml_sent"]], on="ticker")
m = m[(m.pub < m.filing_date) & (m.pub >= m.filing_date - pd.Timedelta(days=30))]
m["d7"] = m.pub >= m.filing_date - pd.Timedelta(days=7)
a30 = m.groupby("eid").agg(news_n_30d=("ml_sent", "count"), news_sent_30d=("ml_sent", "mean"))
a7 = m[m.d7].groupby("eid").agg(news_n_7d=("ml_sent", "count"), news_sent_7d=("ml_sent", "mean"))
fm = fm.merge(a30, on="eid", how="left").merge(a7, on="eid", how="left")
cnt = ["news_n_7d", "news_n_30d"]; allc = cnt + ["news_sent_7d", "news_sent_30d"]
fm[cnt] = fm[cnt].fillna(0)
fm.loc[fm.filing_date < "2021-02-01", allc] = np.nan
fm.drop(columns="eid").to_csv("feature_matrix_v2.csv", index=False)
print(fm.shape)
