"""Download and verify the already submitted OPRA OHLCV-1d batch when ready.

This watcher makes no new data purchase. It uses the saved job receipt and the
existing SHA-256-checking batch downloader.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import requests

from download_databento_options import _api_key, download_job


JOB_ID = "OPRA-20261003-3QFKGVKXNA"
POLL_SECONDS = 120
MAX_WAIT_SECONDS = 24 * 60 * 60
REQUIRED_COLUMNS = {
    "ts_event", "publisher_id", "instrument_id", "open", "high",
    "low", "close", "volume", "symbol",
}


def _write_json(path: Path, value: dict) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _verify_csv_headers(directory: Path) -> int:
    files = sorted(directory.glob("*.csv.zst"))
    if not files:
        raise RuntimeError("No compressed OHLCV CSV data files were downloaded")
    for path in files:
        with pa.input_stream(path) as stream:
            first_line = stream.read(4096).decode("utf-8").splitlines()[0]
        columns = set(next(csv.reader([first_line])))
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise RuntimeError(f"{path.name} is missing OHLCV fields: {sorted(missing)}")
    return len(files)


def _update_ledger(root: Path, actual_cost: float) -> float:
    path = root / "data/raw/databento/acquisition_ledger.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    matched = False
    for item in ledger["purchases"]:
        if item.get("job_id") == JOB_ID:
            item["actual_cost_usd"] = actual_cost
            item["status"] = "done"
            matched = True
    if not matched:
        raise RuntimeError("OHLCV job is missing from the acquisition ledger")
    ledger["actual_plus_quoted_usd"] = sum(
        item.get("actual_cost_usd", item.get("quoted_cost_usd", 0))
        for item in ledger["purchases"]
    )
    _write_json(path, ledger)
    return ledger["actual_plus_quoted_usd"]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    raw = root / "data/raw/databento"
    directory = raw / JOB_ID
    receipt = json.loads((directory / "submission_receipt.json").read_text(encoding="utf-8"))
    if receipt["job_id"] != JOB_ID or receipt["schema"] != "ohlcv-1d":
        raise RuntimeError("Submitted job receipt does not match this watcher")
    status_path = raw / "ohlcv1d_finalize_status.json"
    session = requests.Session()
    session.auth = (_api_key(root), "")
    began = time.monotonic()

    def status(stage: str, **values: object) -> None:
        record = {"job_id": JOB_ID, "stage": stage,
                  "checked_at_utc": datetime.now(timezone.utc).isoformat(), **values}
        _write_json(status_path, record)
        print(json.dumps(record), flush=True)

    while True:
        try:
            response = session.get(
                "https://hist.databento.com/v0/batch.get_job_details",
                params={"job_id": JOB_ID},
                timeout=60,
            )
            response.raise_for_status()
            job = response.json()
        except requests.RequestException as exc:
            status("poll_error", error=type(exc).__name__)
        else:
            state = job["state"]
            status("waiting" if state != "done" else "ready",
                   state=state, progress=job.get("progress"),
                   cost_usd=job.get("cost_usd"))
            if state == "done":
                break
            if state == "expired":
                raise RuntimeError("Databento OHLCV job expired before download")
        if time.monotonic() - began > MAX_WAIT_SECONDS:
            raise TimeoutError("Databento OHLCV job did not finish within 24 hours")
        time.sleep(POLL_SECONDS)

    status("downloading", cost_usd=job.get("cost_usd"))
    summary = download_job(root, JOB_ID)
    file_count = _verify_csv_headers(directory)
    if not isinstance(summary.get("record_count"), int) or summary["record_count"] <= 0:
        raise RuntimeError("Databento OHLCV job has no records")
    cost = summary.get("cost_usd")
    if not isinstance(cost, (int, float)) or cost < 0:
        raise RuntimeError("Databento did not report a valid actual cost")
    total = _update_ledger(root, float(cost))
    status("complete", cost_usd=cost, ledger_total_usd=total,
           record_count=summary["record_count"], csv_file_count=file_count,
           directory=str(directory))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        root = Path(__file__).resolve().parents[1]
        _write_json(root / "data/raw/databento/ohlcv1d_finalize_status.json", {
            "job_id": JOB_ID, "stage": "failed",
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "error": str(exc)[:300],
        })
        raise
