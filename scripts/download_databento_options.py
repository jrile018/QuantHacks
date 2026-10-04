"""Download purchased Databento batch files with size and SHA-256 checks.

Usage: .venv/Scripts/python scripts/download_databento_options.py JOB_ID
The API key is read from the gitignored project .env file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

import requests


API = "https://hist.databento.com/v0/"
RESERVE_BYTES = 1_000_000_000


def _api_key(project: Path) -> str:
    for line in (project / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABENTO_API_KEY="):
            return line.partition("=")[2].strip().strip("\"'")
    raise RuntimeError("DATABENTO_API_KEY is missing from .env")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_job(project: Path, job_id: str, name_contains: str | None = None) -> dict:
    key = _api_key(project)
    target = project / "data" / "raw" / "databento" / job_id
    target.mkdir(parents=True, exist_ok=True)
    auth = (key, "")
    details_response = requests.get(
        API + "batch.get_job_details", auth=auth, params={"job_id": job_id}, timeout=60
    )
    details_response.raise_for_status()
    details = details_response.json()
    if details.get("state") != "done":
        raise RuntimeError(f"Job {job_id} is {details.get('state')}, not done")
    files_response = requests.get(
        API + "batch.list_files", auth=auth, params={"job_id": job_id}, timeout=60
    )
    files_response.raise_for_status()
    available_files = files_response.json()
    files = [item for item in available_files
             if name_contains is None or name_contains in item["filename"]
             or item["filename"] in {"metadata.json", "symbology.json"}]
    if not files:
        raise RuntimeError(f"No files matched {name_contains!r} for {job_id}")
    pending = []
    for item in files:
        name = item["filename"]
        if Path(name).name != name:
            raise ValueError(f"Invalid filename from Databento: {name!r}")
        url = item["urls"]["https"]
        if urlparse(url).scheme != "https" or urlparse(url).hostname != "api.databento.com":
            raise ValueError(f"Unexpected download host for {name}")
        expected_hash = item["hash"].removeprefix("sha256:")
        path = target / name
        if path.exists() and path.stat().st_size == item["size"] and _sha256(path) == expected_hash:
            print("VERIFIED_EXISTING", name)
            continue
        pending.append((item, path, expected_hash, url))
    required = sum(item["size"] for item, _, _, _ in pending)
    free = shutil.disk_usage(target).free
    if required + RESERVE_BYTES > free:
        raise RuntimeError(
            f"Insufficient disk space: need {required:,} bytes plus {RESERVE_BYTES:,} reserve; "
            f"free {free:,} bytes"
        )
    with requests.Session() as session:
        session.auth = auth
        for item, path, expected_hash, url in pending:
            temp = path.with_name(path.name + ".part")
            if temp.exists():
                temp.unlink()
            with session.get(url, stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                with temp.open("wb") as stream:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            stream.write(chunk)
            if temp.stat().st_size != item["size"] or _sha256(temp) != expected_hash:
                raise RuntimeError(f"Size or SHA-256 mismatch for {item['filename']}")
            temp.replace(path)
            print("DOWNLOADED_VERIFIED", item["filename"], item["size"])
    summary = {
        "job_id": job_id,
        "state": details["state"],
        "cost_usd": details.get("cost_usd"),
        "record_count": details.get("record_count"),
        "actual_size": details.get("actual_size"),
        "available_file_count": len(available_files),
        "selection": name_contains,
        "files": [{"name": item["filename"], "size": item["size"], "sha256": item["hash"]} for item in files],
    }
    (target / "download_manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    parser.add_argument("--name-contains", help="Download only files whose name contains this text, plus metadata")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    result = download_job(project_root, args.job_id, args.name_contains)
    print("JOB_VERIFIED", result["job_id"], len(result["files"]), "files", result["record_count"], "records")
