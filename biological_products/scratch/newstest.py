import os, requests, json
H = {"Authorization": "Bearer " + os.environ["MASSIVE_API_KEY"]}
r = requests.get("https://api.massive.com/v2/reference/news", headers=H, params={"ticker": "AMGN", "limit": 3, "order": "asc", "published_utc.gte": "2020-01-01"})
print(r.status_code)
j = r.json()
for a in j.get("results", []):
    print(a.get("published_utc"), "|", a.get("title"))
    print("  insights:", a.get("insights"))
print(list(j.get("results", [{}])[0].keys()) if j.get("results") else j)
