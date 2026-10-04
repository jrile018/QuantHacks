import csv, re, pandas as pd
fn = "purplebook-search-August-data-download.csv"
rows = list(csv.reader(open(fn, encoding="latin-1", newline="")))
hdr = [i for i, r in enumerate(rows) if "Applicant" in r and "BLA Number" in r]
print("header rows at", hdr)
parts = []
for k, i in enumerate(hdr):
    end = hdr[k+1] if k + 1 < len(hdr) else len(rows)
    cols = rows[i]
    data = [(r + [""] * len(cols))[:len(cols)] for r in rows[i+1:end]]
    d = pd.DataFrame(data, columns=cols); d["section"] = k
    parts.append(d)
df = pd.concat(parts, ignore_index=True)
df = df[df["BLA Number"].str.strip().str.isdigit()].copy()
df["approval_date"] = pd.to_datetime(df["Approval Date"], format="%d-%b-%y", errors="coerce")
df["first_licensure"] = pd.to_datetime(df["Date of First Licensure"], format="%d-%b-%y", errors="coerce")

def clean(n):
    n = re.sub(r"\b(Class [A-Z]|Common Stock|Common shares|Ordinary Shares?|American Depositary (Shares?|Share)|Holdings?|Inc|Corp(oration)?|Ltd|plc|Limited|Company|Co)\b\.?", "", n, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", n)).strip()

inds = pd.read_csv("industries.csv")
co = inds[inds.sic_code == 2836][["ticker", "name"]]
out = []
for tk, name in zip(co.ticker, co.name):
    w = clean(name).lower().split()
    if not w: continue
    key = " ".join(w[:2]) if len(w) > 1 else w[0]
    m = df[df.Applicant.str.replace(r"[^\w\s]", " ", regex=True).str.lower().str.contains(key, regex=False)].copy()
    m["ticker"] = tk
    out.append(m)
res = pd.concat(out, ignore_index=True)
res = res.drop_duplicates(["ticker", "BLA Number", "Supplement Number", "Product Number", "Submission Type"])
res.to_csv("purplebook_actions.csv", index=False)
print(len(df), "total rows in file;", len(res), "rows matched;", res.ticker.nunique(), "companies")
print(res.groupby("ticker").size().sort_values(ascending=False).head(10))
print(res["Submission Type"].value_counts())
