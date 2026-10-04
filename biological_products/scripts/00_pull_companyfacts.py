import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from bp_paths import P
# Downloads SEC XBRL "companyfacts" (financial statements) for every SIC 2836 ticker.
# Needs env var SEC_UA, for example "Your Name your@email.com". Skips files that already exist.
# NOTE: this replaces a one-off PowerShell command and has been checked only for syntax. Run it once to confirm.
import json, time, requests, pandas as pd
UA = {"User-Agent": os.environ["SEC_UA"]}
tks = pd.read_csv(P("industries.csv")).query("sic_code == 2836").ticker.tolist()
m = requests.get("https://www.sec.gov/files/company_tickers.json", headers=UA, timeout=60).json()
cik_of = {v["ticker"].upper(): int(v["cik_str"]) for v in m.values()}
out = P("companyfacts")
os.makedirs(out, exist_ok=True)
saved = skipped = missing = 0
for tk in tks:
    path = os.path.join(out, tk + ".json")
    if os.path.exists(path): skipped += 1; continue
    cik = cik_of.get(tk.upper())
    if cik is None: print("no CIK for", tk); missing += 1; continue
    r = requests.get("https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json" % cik, headers=UA, timeout=90)
    if r.status_code == 200:
        open(path, "w", encoding="utf-8").write(r.text); saved += 1
    else:
        print("fail", tk, r.status_code); missing += 1
    time.sleep(0.15)
print(saved, "saved,", skipped, "already there,", missing, "missing")
