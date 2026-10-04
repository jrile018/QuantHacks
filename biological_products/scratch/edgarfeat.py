import pandas as pd, numpy as np
e = pd.read_csv("edgar_filings.csv"); e["fd"] = pd.to_datetime(e.filing_date)
def cat(f):
    f = str(f)
    if f in ("S-3", "S-3ASR", "S-3/A", "S-1", "S-1/A", "F-3"): return "shelf"
    if f.startswith("424B"): return "p424b"
    if f == "4": return "form4"
    if f == "144": return "form144"
    if f.startswith(("SC 13D", "SCHEDULE 13D")): return "act13d"
    if f.startswith("NT "): return "late"
    if f == "8-K": return "k8"
    return None
e["cat"] = e.form.map(cat); e = e.dropna(subset=["cat"])

fm = pd.read_csv("feature_matrix_v3.csv", parse_dates=["filing_date"]); fm["eid"] = range(len(fm))
inds = set(pd.read_csv("industries.csv").query("sic_code == 2836").ticker)
print("tickers not in your list:", sorted(set(fm.ticker) - inds))
fm["cik"] = fm.cik.astype("int64")
m = fm[["eid", "cik", "filing_date"]].merge(e[["cik", "fd", "cat"]], on="cik")
m["d"] = (m.filing_date - m.fd).dt.days
m = m[m.d > 0]
last = m.groupby(["eid", "cat"]).d.min().unstack()[["shelf", "p424b", "k8"]]
last.columns = ["days_since_" + c for c in last.columns]
out = last
for c, w in [("p424b", 90), ("form4", 30), ("form144", 90), ("act13d", 180), ("late", 365), ("k8", 30)]:
    out = out.join(m[(m.cat == c) & (m.d <= w)].groupby("eid").size().rename("n_%s_%dd" % (c, w)), how="outer")
fm = fm.merge(out, left_on="eid", right_index=True, how="left")
cnt = [c for c in fm.columns if c.startswith("n_") and c.endswith("d") and c not in ("n_trials",) and c.split("_")[-1][:-1].isdigit()]
fm[cnt] = fm[cnt].fillna(0)
fm.loc[fm.filing_date < "2020-06-01", "n_late_365d"] = np.nan
fm.drop(columns="eid").to_csv("feature_matrix_v4.csv", index=False)
print(fm.shape)
print(fm[[c for c in fm.columns if c.startswith("days_since") or c in cnt]].describe().round(1).T[["count", "mean", "50%", "max"]])
