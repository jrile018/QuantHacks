import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
import pandas as pd, numpy as np
p = pd.read_csv(P("prices.csv")); p["date"] = pd.to_datetime(p.date)
p = p.sort_values(["ticker", "date"]).reset_index(drop=True)
g = p.groupby("ticker")
p["ret1"] = g.close.pct_change()
for k in (5, 20, 60): p["ret_%dd" % k] = g.close.pct_change(k)
p["vol_20d"] = g.ret1.transform(lambda s: s.rolling(20).std())
p["adv_20d"] = (p.close * p.volume).groupby(p.ticker).transform(lambda s: s.rolling(20).mean())
p["off_52w_high"] = p.close / g.close.transform(lambda s: s.rolling(252, min_periods=60).max()) - 1
p["vol_spike"] = g.volume.transform(lambda s: s.rolling(5).mean()) / g.volume.transform(lambda s: s.rolling(60).mean())
p["close_next"] = g.close.shift(-1)
xbi = p[p.ticker == "XBI"][["date", "ret_20d"]].rename(columns={"ret_20d": "xbi_ret_20d"})
p = p.merge(xbi, on="date", how="left")
p["excess_20d"] = p.ret_20d - p.xbi_ret_20d

fm = pd.read_csv(P("feature_matrix_v2.csv")); fm["filing_date"] = pd.to_datetime(fm.filing_date)
fm["eid"] = range(len(fm)); fm = fm.sort_values("filing_date")
feats = ["ret_5d", "ret_20d", "ret_60d", "excess_20d", "vol_20d", "adv_20d", "off_52w_high", "vol_spike"]
pr = p.sort_values("date")
a = pd.merge_asof(fm, pr[["ticker", "date", "close"] + feats].rename(columns={"date": "price_asof", "close": "prev_close"}),
                  left_on="filing_date", right_on="price_asof", by="ticker", allow_exact_matches=False)
b = pd.merge_asof(a.sort_values("filing_date"), pr[["ticker", "date", "close", "close_next"]].rename(columns={"date": "d0_date", "close": "close_d0"}),
                  left_on="filing_date", right_on="d0_date", by="ticker", direction="forward")
b["y_ret_d0"] = b.close_d0 / b.prev_close - 1
b["y_ret_d1"] = b.close_next / b.prev_close - 1
b["y_abs_d1"] = b.y_ret_d1.abs()
b = b.sort_values("eid").drop(columns=["eid", "close_d0", "close_next"])
b.to_csv(P("feature_matrix_v3.csv"), index=False)
print(b.shape)
print(b[feats + ["y_ret_d0", "y_ret_d1"]].isna().mean().round(2))
t = b.groupby("tertiary_category").y_abs_d1.agg(["count", "mean"]).query("count >= 40").sort_values("mean", ascending=False)
print(t.head(10).round(3))
