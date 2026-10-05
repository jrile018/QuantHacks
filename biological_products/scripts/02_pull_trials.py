import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
import re, time, requests, pandas as pd
SIC = 2836
inds = pd.read_csv(P("industries.csv"))
co = inds[inds.sic_code == SIC][["ticker", "name"]]

def clean(n):
    n = re.sub(r"\b(Class [A-Z]|Common Stock|Common shares|Ordinary Shares?|American Depositary (Shares?|Share)|Holdings?|Inc|Corp(oration)?|Ltd|plc|Limited|Company|Co)\b\.?", "", n, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", n)).strip()

FIELDS = "NCTId|BriefTitle|LeadSponsorName|OverallStatus|Phase|StartDate|PrimaryCompletionDate|CompletionDate|ResultsFirstPostDate|LastUpdatePostDate|EnrollmentCount"

def pull(sponsor):
    out, token = [], None
    while True:
        params = {"query.spons": sponsor, "fields": FIELDS, "pageSize": 1000, "format": "json"}
        if token: params["pageToken"] = token
        r = requests.get("https://clinicaltrials.gov/api/v2/studies", params=params, timeout=60)
        r.raise_for_status(); j = r.json()
        out += j.get("studies", [])
        token = j.get("nextPageToken")
        if not token: return out
        time.sleep(0.2)

def g(d, *ks):
    for k in ks:
        if not isinstance(d, dict): return None
        d = d.get(k)
    return d

rows = []
for tk, name in zip(co.ticker, co.name):
    c = clean(name); words = c.lower().split()
    key = " ".join(words[:2]) if len(words) > 1 else (words[0] if words else "")
    if not key: continue
    try: studies = pull(c)
    except Exception as e: print("fail", tk, e); continue
    for s in studies:
        p = s.get("protocolSection", {})
        sp = g(p, "sponsorCollaboratorsModule", "leadSponsor", "name") or ""
        if key not in re.sub(r"[^\w\s]", " ", sp).lower(): continue
        rows.append(dict(ticker=tk, nct_id=g(p, "identificationModule", "nctId"),
            title=g(p, "identificationModule", "briefTitle"), sponsor=sp,
            status=g(p, "statusModule", "overallStatus"),
            phase="|".join(g(p, "designModule", "phases") or []),
            start=g(p, "statusModule", "startDateStruct", "date"),
            primary_completion=g(p, "statusModule", "primaryCompletionDateStruct", "date"),
            primary_completion_type=g(p, "statusModule", "primaryCompletionDateStruct", "type"),
            completion=g(p, "statusModule", "completionDateStruct", "date"),
            results_first_posted=g(p, "statusModule", "resultsFirstPostDateStruct", "date"),
            last_update=g(p, "statusModule", "lastUpdatePostDateStruct", "date"),
            enrollment=g(p, "designModule", "enrollmentInfo", "count")))
    time.sleep(0.2)

df = pd.DataFrame(rows).drop_duplicates(["ticker", "nct_id"])
df["pulled_on"] = pd.Timestamp.today().date()
df.to_csv(P("trials.csv"), index=False)
print(len(df), "trials,", df.ticker.nunique(), "companies")
