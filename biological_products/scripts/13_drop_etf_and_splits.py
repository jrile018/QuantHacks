import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
import pandas as pd, numpy as np
b = pd.read_csv(P("feature_matrix_v3.csv"))
b = b[b.ticker != "PRTO"].copy()
split = b.y_ret_d1.abs() > 10
print(split.sum(), "rows with >1000% moves (likely unadjusted splits):", b[split].ticker.unique().tolist())
b.loc[split, ["y_ret_d0", "y_ret_d1", "y_abs_d1"]] = np.nan
b.to_csv(P("feature_matrix_v3.csv"), index=False)
print(b.shape, "rows,", b.ticker.nunique(), "tickers")
