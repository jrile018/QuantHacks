import re, time, requests, pandas as pd
inds = pd.read_csv("industries.csv")
co = inds[inds.sic_code == 2836][["ticker", "name"]]

def clean(n):
    n = re.sub(r"\b(Class [A-Z]|Common Stock|Common shares|Ordinary Shares?|American Depositary (Shares?|Share)|Holdings?|Inc|Corp(oration)?|Ltd|plc|Limited|Company|Co)\b\.?", "", n, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", n)).strip()

rows = []
for tk, name in zip(co.ticker, co.name):
    c = clean(name); w = c.lower().split()
    if not w: continue
    key = " ".join(w[:2]) if len(w) > 1 else w[0]
    skip = 0
    while True:
        r = requests.get("https://api.fda.gov/drug/drugsfda.json",
                         params={"search": "sponsor_name:" + w[0].upper(), "limit": 1000, "skip": skip}, timeout=60)
        if r.status_code == 404: break
        if r.status_code != 200: print("fail", tk, r.status_code); break
        res = r.json().get("results", [])
        for a in res:
            sp = a.get("sponsor_name", "") or ""
            if key not in re.sub(r"[^\w\s]", " ", sp).lower(): continue
            for s in a.get("submissions", []) or []:
                rows.append(dict(ticker=tk, application_number=a.get("application_number"), sponsor=sp,
                    submission_type=s.get("submission_type"), submission_number=s.get("submission_number"),
                    status=s.get("submission_status"), status_date=s.get("submission_status_date"),
                    review_priority=s.get("review_priority"), class_code=s.get("submission_class_code")))
        if len(res) < 1000: break
        skip += 1000
        time.sleep(0.3)
    time.sleep(0.3)

df = pd.DataFrame(rows).drop_duplicates()
df["status_date"] = pd.to_datetime(df.status_date, format="%Y%m%d", errors="coerce")
df["pulled_on"] = pd.Timestamp.today().date()
df.to_csv("fda_actions.csv", index=False)
print(len(df), "actions,", df.ticker.nunique(), "companies")
print(df.status.value_counts().head(8))


