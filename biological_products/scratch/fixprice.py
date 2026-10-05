import pandas as pd, numpy as np
b = pd.read_csv("feature_matrix_v3.csv", parse_dates=["filing_date", "price_asof", "d0_date"])
bad = ((b.filing_date - b.price_asof).dt.days > 5) | ((b.d0_date - b.filing_date).dt.days > 5)
print(bad.sum(), "rows with stale prices;", b[bad].ticker.value_counts().head(8).to_dict())
cols = ["prev_close", "ret_5d", "ret_20d", "ret_60d", "excess_20d", "vol_20d", "adv_20d", "off_52w_high", "vol_spike", "y_ret_d0", "y_ret_d1", "y_abs_d1"]
b.loc[bad, cols] = np.nan
b.to_csv("feature_matrix_v3.csv", index=False)
print(b.sort_values("y_abs_d1", ascending=False)[["ticker", "filing_date", "tertiary_category", "y_ret_d1"]].head(5).to_string())
