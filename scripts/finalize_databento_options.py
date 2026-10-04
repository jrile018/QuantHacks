"""Finish the already purchased 654-contract Databento backfill when ready.

This script makes no new data purchases. It polls the existing batch job,
downloads and verifies its files, builds daily quotes, and runs the Lattice
option ingest/study stages. Designed for a detached local process.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from build_databento_daily_quotes import build
from download_databento_options import _api_key, download_job


JOB_ID = "OPRA-20261003-4APD3MDYPJ"
MAX_WAIT_SECONDS = 8 * 60 * 60
POLL_SECONDS = 90


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    raw_dir = project / "data" / "raw" / "databento"
    status_path = raw_dir / "finalize_status.json"
    key = _api_key(project)
    started = time.monotonic()

    def status(stage: str, **details: object) -> None:
        payload = {"job_id": JOB_ID, "stage": stage,
                   "checked_at_utc": datetime.now(timezone.utc).isoformat(), **details}
        status_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload), flush=True)

    while True:
        try:
            response = requests.get(
                "https://hist.databento.com/v0/batch.get_job_details",
                auth=(key, ""), params={"job_id": JOB_ID}, timeout=60,
            )
            response.raise_for_status()
            job = response.json()
        except requests.RequestException as exc:
            status("poll_error", error=str(exc)[:200])
        else:
            status("waiting" if job["state"] != "done" else "ready",
                   state=job["state"], progress=job.get("progress"),
                   cost_usd=job.get("cost_usd"))
            if job["state"] == "done":
                break
            if job["state"] == "expired":
                raise RuntimeError("Purchased Databento job expired before download")
        if time.monotonic() - started > MAX_WAIT_SECONDS:
            raise TimeoutError("Databento job did not finish within eight hours")
        time.sleep(POLL_SECONDS)

    ledger_path = raw_dir / "acquisition_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    for item in ledger["purchases"]:
        if item.get("job_id") == JOB_ID:
            item["actual_cost_usd"] = job["cost_usd"]
            item["status"] = "done"
    ledger["actual_plus_quoted_usd"] = sum(
        item.get("actual_cost_usd", item.get("quoted_cost_usd", 0))
        for item in ledger["purchases"]
    )
    if ledger["actual_plus_quoted_usd"] >= ledger["budget_ceiling_usd"]:
        raise RuntimeError("Databento actual cost exceeds authorized budget")
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")

    status("downloading", cost_usd=job["cost_usd"])
    download_job(project, JOB_ID)
    status("normalizing")
    summary = build(project, JOB_ID)
    print("QUOTE_SUMMARY", json.dumps(summary), flush=True)

    source = project / "data" / "processed" / "cfo-2024-2025-massive"
    quotes = Path(summary["output"])
    run = project / "data" / "processed" / "lattice-databento-full"
    script = project / "stat-arb" / "tools" / "options_native.py"
    status("lattice_ingest")
    subprocess.run([
        sys.executable, str(script), "ingest", "--study-dir", str(source),
        "--quotes", str(quotes), "--output-dir", str(run / "gm-options-ingest"),
        "--run-id", "databento-full",
    ], cwd=project, check=True)
    status("lattice_study")
    subprocess.run([
        sys.executable, str(script), "study", "--ingest-dir", str(run / "gm-options-ingest"),
        "--output-dir", str(run / "gm-options-study"), "--run-id", "databento-full",
    ], cwd=project, check=True)
    status("complete", cost_usd=job["cost_usd"], quote_marks=summary["daily_quote_marks"],
           selection_contract_dates_covered=summary["selection_contract_dates_covered"],
           selection_contract_dates=summary["selection_contract_dates"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        root = Path(__file__).resolve().parents[1] / "data" / "raw" / "databento"
        (root / "finalize_status.json").write_text(json.dumps({
            "job_id": JOB_ID, "stage": "failed", "error": str(exc),
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n", encoding="utf-8")
        raise
