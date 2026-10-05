import os, requests, collections
H = {"Authorization": "Bearer " + os.environ["MASSIVE_API_KEY"]}
r = requests.get("https://api.massive.com/v2/reference/news", headers=H, params={"ticker": "BIIB", "limit": 1000, "order": "desc"})
res = r.json().get("results", [])
print(r.status_code, len(res), "articles; newest", res[0]["published_utc"][:10], "oldest in batch", res[-1]["published_utc"][:10])
print("with insights:", sum(1 for a in res if a.get("insights")))
print(collections.Counter(a["published_utc"][:4] for a in res))
for a in res[:5]:
    print(a["published_utc"][:10], "|", a["title"], "|", a.get("insights"))
