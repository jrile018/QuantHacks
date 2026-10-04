"""Snapshot verified biotech Greenhouse job boards once per Eastern date.

Usage: python 30_pull_greenhouse_jobs.py
       python 30_pull_greenhouse_jobs.py --board BEAM=beamtherapeutics
Each response is saved unchanged. Existing snapshots are never downloaded again.
This starts a prospective history; currently open jobs are not a past snapshot.
"""

import argparse
import json
import random
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


BOARDS = {"BEAM": "beamtherapeutics", "MAZE": "mazetherapeutics", "PRME": "primemedicine"}
BASE = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
UA = "Abhay (UF student) abhay.dronavalli@gmail.com"


def download(url):
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(5):
        response = session.get(url, timeout=45)
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 2 ** attempt + random.random()))
            continue
        response.raise_for_status()
        return response.content
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--board", action="append", help="Replace defaults with TICKER=board_token; repeatable")
    args = parser.parse_args()
    boards = BOARDS if not args.board else {}
    for value in args.board or []:
        if "=" not in value:
            parser.error("--board needs TICKER=board_token")
        ticker, token = value.split("=", 1)
        if not ticker or not token or not token.replace("-", "").isalnum():
            parser.error("Invalid ticker or board token")
        boards[ticker.upper()] = token
    date = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")
    folder = args.data / "raw" / "greenhouse_jobs" / date
    folder.mkdir(parents=True, exist_ok=True)
    lookup = args.data / "fds" / "fds_lookup_cik_ticker.csv"
    import pandas as pd
    known = set(pd.read_csv(lookup, usecols=["ticker"]).ticker.str.upper())
    for ticker, token in boards.items():
        if ticker not in known:
            print(f"SKIP {ticker}: ticker absent from lookup", flush=True)
            continue
        path = folder / f"{ticker}_{token}.json"
        if path.exists():
            body = path.read_bytes()
            state = "cached"
        else:
            try:
                body = download(BASE.format(board=token))
                payload = json.loads(body)
                if not isinstance(payload.get("jobs"), list):
                    raise ValueError("Response has no jobs array")
                with path.open("xb") as handle:
                    handle.write(body)
                state = "downloaded"
            except (requests.RequestException, ValueError) as exc:
                print(f"FAILED {ticker} {token}: {type(exc).__name__}: {exc}", flush=True)
                continue
        jobs = json.loads(body)["jobs"]
        commercial = sum(any(word in str(job.get("title", "")).lower() for word in
                             ("commercial", "market access", "field sales", "sales director")) for job in jobs)
        print(f"{ticker} {token}: {state}; jobs {len(jobs)}; commercial titles {commercial}; {path}", flush=True)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
