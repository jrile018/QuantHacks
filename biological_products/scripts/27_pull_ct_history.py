"""Download complete ClinicalTrials.gov record versions with restartable checkpoints.

Usage: python 27_pull_ct_history.py --limit 5
       python 27_pull_ct_history.py
The internal history API is undocumented. A 403 is reported and never treated
as an empty history. Version dates in the index are submission dates; event
builders must use each version's posted date instead.
"""

import argparse
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


BASE = "https://clinicaltrials.gov/api/int/studies"
UA = "Abhay (UF student) abhay.dronavalli@gmail.com"


def get_json(session, url, attempts=5):
    for attempt in range(attempts):
        response = session.get(url, timeout=45)
        if response.status_code in (429, 500, 502, 503, 504):
            delay = min(60, 2 ** attempt + random.random())
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response.json()
    response.raise_for_status()


def save_atomic(path, payload):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, path)


def posted_date(version):
    study = version.get("study", version)
    status = study.get("protocolSection", {}).get("statusModule", {})
    value = status.get("lastUpdatePostDateStruct") or status.get("studyFirstPostDateStruct") or {}
    return value.get("date", "")


def brief_changes(before, after):
    def fields(version):
        p = version.get("study", version).get("protocolSection", {})
        s, d = p.get("statusModule", {}), p.get("designModule", {})
        return {
            "status": s.get("overallStatus"),
            "primary completion": (s.get("primaryCompletionDateStruct") or {}).get("date"),
            "completion": (s.get("completionDateStruct") or {}).get("date"),
            "enrollment": (d.get("enrollmentInfo") or {}).get("count"),
            "results posted": (s.get("resultsFirstPostDateStruct") or {}).get("date"),
        }
    old, new = fields(before), fields(after)
    return "; ".join(f"{key}: {old[key]} -> {new[key]}" for key in new if old[key] != new[key]) or "other fields"


def pull_one(nct, ticker, folder):
    path = folder / f"{nct}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {"nct_id": nct, "ticker": ticker, "source": BASE, "history": None, "versions": {}}
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})
    try:
        if payload["history"] is None:
            payload["history"] = get_json(session, f"{BASE}/{nct}/history")
            save_atomic(path, payload)
        changes = payload["history"].get("changes", [])
        if not changes:
            raise ValueError("History response has no changes array")
        numbers = sorted({int(item["version"]) for item in changes})
        for number in numbers:
            key = str(number)
            if key in payload["versions"]:
                continue
            version = get_json(session, f"{BASE}/{nct}/history/{number}")
            if "protocolSection" not in version.get("study", version):
                raise ValueError(f"Version {number} has no protocolSection")
            if not posted_date(version):
                raise ValueError(f"Version {number} has no posted date")
            payload["versions"][key] = version
            save_atomic(path, payload)
            time.sleep(0.15)
        payload["completed_utc"] = datetime.now(timezone.utc).isoformat()
        save_atomic(path, payload)
        return nct, ticker, payload, None
    except Exception as exc:
        return nct, ticker, payload, f"{type(exc).__name__}: {exc}"
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--limit", type=int, default=0, help="First N studies; zero means all")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.workers <= 3:
        parser.error("--workers must be 1, 2, or 3")
    trials = pd.read_csv(args.data / "raw" / "trials.csv", usecols=["ticker", "nct_id"])
    trials = trials.drop_duplicates("nct_id")
    trials = trials[trials.nct_id.map(lambda x: bool(re.fullmatch(r"NCT\d{8}", str(x))))]
    if args.limit:
        trials = trials.head(args.limit)
    folder = args.data / "raw" / "ct_history"
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Studies selected: {len(trials)}; workers: {args.workers}; cache: {folder}", flush=True)
    started = time.monotonic()
    success = failure = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(pull_one, row.nct_id, row.ticker, folder): row.nct_id for row in trials.itertuples(index=False)}
        for future in as_completed(futures):
            nct, ticker, payload, error = future.result()
            success += error is None
            failure += error is not None
            if error:
                print(f"FAILED {ticker} {nct}: {error}", flush=True)
            elif args.limit:
                print(f"TIMELINE {ticker} {nct}: {len(payload['versions'])} versions", flush=True)
                prior = None
                for key in sorted(payload["versions"], key=int):
                    version = payload["versions"][key]
                    print(f"  v{int(key)+1} posted {posted_date(version)}: " + ("first posting" if prior is None else brief_changes(prior, version)), flush=True)
                    prior = version
            done = success + failure
            rate = done / max(time.monotonic() - started, 0.001)
            eta = (len(trials) - done) / max(rate, 0.001)
            print(f"Progress {done}/{len(trials)}; complete {success}; failed {failure}; ETA {eta/60:.1f} min", flush=True)
    print(f"Finished: complete {success}; failed {failure}", flush=True)
    if failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
