"""Cache the latest openFDA label response for original NDA and BLA approvals.

The label is current as downloaded, so NCT citations are retrospective links.
Do not backdate a citation to the product's original approval day.
"""

import argparse
import json
import random
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


UA = "Abhay (UF student) abhay.dronavalli@gmail.com"
URL = "https://api.fda.gov/drug/label.json"


def applications(data):
    path = data / "raw" / "research_cache" / "drug-drugsfda-0001-of-0001.json.zip"
    with zipfile.ZipFile(path) as archive:
        payload = json.loads(archive.read(archive.namelist()[0]))
    found = []
    for item in payload["results"]:
        app = item.get("application_number", "")
        if not app.startswith(("NDA", "BLA")):
            continue
        if any(s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP" and
               "20180101" <= s.get("submission_status_date", "") <= "20261004"
               for s in item.get("submissions", [])):
            found.append(app)
    return sorted(set(found))


def one(app, folder):
    path = folder / f"{app}.json"
    if path.exists():
        body = path.read_bytes()
        status = 200 if "results" in json.loads(body) else 404
        return app, status, "cached"
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})
    params = {"search": f'openfda.application_number:"{app}"', "limit": 1,
              "sort": "effective_time:desc"}
    for attempt in range(5):
        response = session.get(URL, params=params, timeout=60)
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 2 ** attempt + random.random()))
            continue
        if response.status_code not in (200, 404):
            response.raise_for_status()
        with path.open("xb") as handle:
            handle.write(response.content)
        return app, response.status_code, "downloaded"
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    apps = applications(args.data)
    if args.limit:
        apps = apps[:args.limit]
    folder = args.data / "raw" / "research_cache" / "fda_labels"
    folder.mkdir(parents=True, exist_ok=True)
    print(f"FDA label applications selected: {len(apps)}", flush=True)
    counts = {200: 0, 404: 0}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, future in enumerate(as_completed([pool.submit(one, app, folder) for app in apps]), start=1):
            app, status, state = future.result()
            counts[status] = counts.get(status, 0) + 1
            if i % 100 == 0 or i == len(apps):
                print(f"Labels {i}/{len(apps)}; found {counts[200]}; absent {counts[404]}; latest {app} {state}", flush=True)
    print(f"Finished labels: found {counts[200]}; absent {counts[404]}", flush=True)


if __name__ == "__main__":
    main()
