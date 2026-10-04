"""Central place for file locations. Scripts call P("name.csv") and get the right folder."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # biological_products/
REPO = os.path.dirname(ROOT)                                           # repo root (industries.csv lives here)
PROCESSED = {"news_scored.csv", "feature_matrix.csv", "feature_matrix_v2.csv", "feature_matrix_v3.csv", "feature_matrix_v4.csv"}
FINAL = {"feature_matrix_final.csv"}

def P(name):
    if name == "industries.csv":
        return os.path.join(REPO, name)
    sub = "final" if name in FINAL else "processed" if name in PROCESSED else "raw"
    d = os.path.join(ROOT, "data", sub)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)
