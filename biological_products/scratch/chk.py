import pandas as pd
b = pd.read_csv("feature_matrix_v3.csv")
t = b.groupby("tertiary_category").y_abs_d1.agg(["count", "median", "mean"]).query("count >= 40").sort_values("median", ascending=False)
print(t.head(8).round(3))
print(b.sort_values("y_abs_d1", ascending=False)[["ticker", "filing_date", "tertiary_category", "prev_close", "y_ret_d0", "y_ret_d1"]].head(12).to_string())
