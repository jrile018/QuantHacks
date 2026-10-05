import pandas as pd
b = pd.read_csv("feature_matrix_v4.csv")
stray = ["ADGI", "AZYO", "CHFW", "CRTX", "DIL", "JATT", "ONVO"]
for t in stray:
    s = b[b.ticker == t]
    others = b[(b.cik.isin(s.cik)) & (b.ticker != t)].ticker.unique().tolist()
    print(t, "| rows", len(s), "| cik", s.cik.unique().tolist(), "| dates", s.filing_date.min()[:10], "to", s.filing_date.max()[:10], "| same cik other tickers:", others, "| price missing:", round(s.ret_20d.isna().mean(), 2), "| trials:", int(s.n_trials.max()))
