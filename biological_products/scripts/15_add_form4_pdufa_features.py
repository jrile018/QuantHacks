import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
import pandas as pd, numpy as np

fm = pd.read_csv(P("feature_matrix_v4.csv"), parse_dates=["filing_date"])
fm["eid"] = range(len(fm)); fm["cik"] = fm.cik.astype("int64")

# ---------- Insider open-market trades (Form 4, codes P = buy, S = sell) ----------
t = pd.read_csv(P("form4_tx.csv")); t = t[t.code.isin(["P", "S"])].copy()
t["fd"] = pd.to_datetime(t.filing_date)
sh = pd.to_numeric(t.shares, errors="coerce"); pr = pd.to_numeric(t.price, errors="coerce")
t["usd"] = (sh * pr).where((pr > 0) & (pr < 5000)).clip(upper=25_000_000)   # drop bad prices, cap mega-deals
t["officer"] = t.is_officer.astype(str).str.lower().isin(["1", "true"])
m = fm[["eid", "cik", "filing_date"]].merge(t[["cik", "fd", "code", "usd", "officer"]], on="cik")
m["d"] = (m.filing_date - m.fd).dt.days
m = m[(m.d > 0) & (m.d <= 90)]
b, s = m[m.code == "P"], m[m.code == "S"]
f = pd.DataFrame(index=fm.eid)
f["n_insider_buys_30d"] = b[b.d <= 30].groupby("eid").size()
f["n_insider_buys_90d"] = b.groupby("eid").size()
f["n_insider_sells_90d"] = s.groupby("eid").size()
f["n_officer_buys_90d"] = b[b.officer].groupby("eid").size()
f["insider_buy_usd_90d"] = b.groupby("eid").usd.sum()
f["insider_sell_usd_90d"] = s.groupby("eid").usd.sum()
f = f.fillna(0); f["insider_net_usd_90d"] = f.insider_buy_usd_90d - f.insider_sell_usd_90d
fm = fm.merge(f, left_on="eid", right_index=True, how="left")

# ---------- PDUFA dates announced in earlier 8-Ks (point in time) ----------
rows = []
for fn in ("pdufa_full.csv", "pdufa_mentions.csv"):
    d = pd.read_csv(P(fn)); d = d[d.pdufa_dates.fillna("") != ""]
    for r in d.itertuples():
        for x in str(r.pdufa_dates).split("|"):
            rows.append((int(r.cik), pd.to_datetime(r.filing_date), pd.to_datetime(x, errors="coerce")))
pd_ = pd.DataFrame(rows, columns=["cik", "announced", "pdufa"]).dropna().drop_duplicates()
pd_ = pd_[(pd_.pdufa >= pd_.announced - pd.Timedelta(days=5)) & (pd_.pdufa <= pd_.announced + pd.Timedelta(days=800))]
m = fm[["eid", "cik", "filing_date"]].merge(pd_, on="cik")
m = m[m.announced < m.filing_date]                       # only dates already public before this 8-K
nxt = m[m.pdufa >= m.filing_date].groupby("eid").pdufa.min()
prv = m[m.pdufa < m.filing_date].groupby("eid").pdufa.max()
fm["days_to_next_pdufa"] = (nxt - fm.set_index("eid").filing_date.reindex(nxt.index)).dt.days.reindex(fm.eid).values
fm["days_since_last_pdufa"] = (fm.set_index("eid").filing_date.reindex(prv.index) - prv).dt.days.reindex(fm.eid).values
fm.loc[fm.days_to_next_pdufa > 365, "days_to_next_pdufa"] = np.nan
fm.loc[fm.days_since_last_pdufa > 120, "days_since_last_pdufa"] = np.nan

fm.drop(columns="eid").to_csv(P("feature_matrix_final.csv"), index=False)
print(fm.shape)
print(fm[[c for c in fm.columns if "insider" in c or "pdufa" in c]].describe().round(1).T[["count", "mean", "50%", "max"]])
r = fm[fm.tertiary_category == "regulatory_decision"]
print("regulatory_decision events:", len(r), "| with a known upcoming PDUFA:", int(r.days_to_next_pdufa.notna().sum()))
