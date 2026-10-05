import pandas as pd, numpy as np
ev = pd.read_csv("events_8k.csv"); f = pd.read_csv("facts_long.csv"); tr = pd.read_csv("trials.csv")
ev["filing_date"] = pd.to_datetime(ev.filing_date)
ev["cik"] = pd.to_numeric(ev.cik, errors="coerce"); ev = ev.dropna(subset=["cik"]); ev["cik"] = ev.cik.astype("int64")
ev["ticker"] = ev.tickers.astype(str).str.extract(r"([A-Za-z]+)")[0].str.upper()
ev["ticker"] = ev.cik.map({1832038:"IVVD",1708527:"ELUT",1824893:"SRZN",1662774:"QNCX",1213809:"DYAI",1855644:"ZURA",1497253:"VIVS"}).fillna(ev.ticker)
ev = ev.sort_values("filing_date").reset_index(drop=True); ev["eid"] = ev.index
f["cik"] = f.cik.astype("int64"); f["filed"] = pd.to_datetime(f.filed); f["end"] = pd.to_datetime(f.end)

names = {"CashAndCashEquivalentsAtCarryingValue":"cash","Assets":"assets","Liabilities":"liabilities","StockholdersEquity":"equity",
         "ResearchAndDevelopmentExpense":"rd_annual","NetIncomeLoss":"netinc_annual","NetCashProvidedByUsedInOperatingActivities":"opcf_annual"}
flows = {"ResearchAndDevelopmentExpense","NetIncomeLoss","NetCashProvidedByUsedInOperatingActivities"}
for tag, nm in names.items():
    s = f[f.tag == tag]
    if tag in flows: s = s[(s.form == "10-K") & (s.fp == "FY")]
    s = s.sort_values(["cik","filed","end"]).groupby(["cik","filed"]).tail(1)
    s = s[["cik","filed","val"]].rename(columns={"val": nm, "filed": nm + "_filed"}).sort_values(nm + "_filed")
    ev = pd.merge_asof(ev.sort_values("filing_date"), s, left_on="filing_date", right_on=nm + "_filed", by="cik")
ev = ev.sort_values("eid").reset_index(drop=True)
ev["runway_years"] = np.where(ev.opcf_annual < 0, ev.cash / -ev.opcf_annual, np.nan)
ev["rd_to_assets"] = ev.rd_annual / ev.assets

for c in ["start","primary_completion"]: tr[c] = pd.to_datetime(tr[c], errors="coerce")
m = ev[["eid","ticker","filing_date"]].merge(tr, on="ticker", how="inner")
m = m[m.start <= m.filing_date]
m["open"] = m.status.isin(["RECRUITING","ACTIVE_NOT_RECRUITING","ENROLLING_BY_INVITATION","NOT_YET_RECRUITING"])
m["ph3_open"] = m.open & m.phase.fillna("").str.contains("PHASE3")
m["pc_next90"] = (m.primary_completion >= m.filing_date) & (m.primary_completion <= m.filing_date + pd.Timedelta(days=90))
m["pc_prev90"] = (m.primary_completion < m.filing_date) & (m.primary_completion >= m.filing_date - pd.Timedelta(days=90))
a = m.groupby("eid").agg(n_trials=("nct_id","count"), n_open=("open","sum"), n_ph3_open=("ph3_open","sum"),
                         n_pc_next90=("pc_next90","sum"), n_pc_prev90=("pc_prev90","sum")).reset_index()
ev = ev.merge(a, on="eid", how="left")
for c in ["n_trials","n_open","n_ph3_open","n_pc_next90","n_pc_prev90"]: ev[c] = ev[c].fillna(0)

keep = ["accession_number","filing_date","ticker","cik","primary_category","secondary_category","tertiary_category",
        "cash","assets","liabilities","equity","rd_annual","netinc_annual","opcf_annual","runway_years","rd_to_assets",
        "n_trials","n_open","n_ph3_open","n_pc_next90","n_pc_prev90"]
ev[keep].to_csv("feature_matrix.csv", index=False)
print(ev[keep].shape)
print(ev[keep].isna().mean().round(2))

