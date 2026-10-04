"""Cache current v2 records for Group A in batches of 50 NCT ids.

These are current records, not version histories. The history cache is not
downloaded or changed. Existing batch responses are reused on later runs.
"""

import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests


UA = "Abhay (UF student) abhay.dronavalli@gmail.com"
URL = "https://clinicaltrials.gov/api/v2/studies"


def one(batch, ids, folder):
    path = folder / f"batch_{batch:04d}.json"
    if path.exists():
        body = path.read_bytes()
        state = "cached"
    else:
        session = requests.Session()
        session.headers.update({"User-Agent": UA, "Accept": "application/json"})
        params = {"filter.ids": ",".join(ids), "pageSize": len(ids)}
        for attempt in range(5):
            response = session.get(URL, params=params, timeout=60)
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 2 ** attempt + random.random()))
                continue
            response.raise_for_status()
            body = response.content
            break
        else:
            response.raise_for_status()
        payload = json.loads(body)
        got = {x["protocolSection"]["identificationModule"]["nctId"] for x in payload.get("studies", [])}
        if not got.issubset(set(ids)):
            raise ValueError(f"Unexpected NCT id in batch {batch}")
        folder.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(body)
        state = "downloaded"
    count = len(json.loads(body).get("studies", []))
    return batch, len(ids), count, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--limit", type=int, default=0, help="Number of batches; zero means all")
    args = parser.parse_args()
    ids = pd.read_csv(args.data / "raw" / "trials.csv", usecols=["nct_id"]).nct_id.drop_duplicates().tolist()
    batches = [(i, ids[i * 50:(i + 1) * 50]) for i in range((len(ids) + 49) // 50)]
    if args.limit:
        batches = batches[:args.limit]
    folder = args.data / "raw" / "research_cache" / "ct_v2_group_a"
    print(f"Group A batches: {len(batches)}; trials requested: {sum(len(x) for _, x in batches)}", flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(one, number, batch, folder) for number, batch in batches]
        for future in as_completed(futures):
            number, requested, received, state = future.result()
            print(f"Batch {number}: requested {requested}; received {received}; {state}", flush=True)


if __name__ == "__main__":
    main()
