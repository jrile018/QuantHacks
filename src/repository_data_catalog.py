"""Read-only metadata inventory and sealed CSV export audit for notebooks.

Inventory never opens dataset files. An audit opens only its manifest and CSVs
explicitly named there; manifest row counts are historical claims, not recounts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path


_AREAS = (
    ("raw", "data/raw"),
    ("processed", "data/processed"),
    ("artifacts", "artifacts"),
    ("examples", "examples"),
    ("references", "references"),
    ("configs", "configs"),
    ("api_cache", ".massive_cache"),
)
_SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints"}
_SUPPORT_EXACT = {"industries.csv", "massive_categories.json"}
_TABLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


def _file_row(root: Path, path: Path, area: str) -> dict:
    try:
        size = path.stat().st_size
        status = "present"
        note = "Metadata only; contents not inspected."
    except OSError:
        size = None
        status = "unreadable"
        note = "File metadata could not be read."
    return {
        "area": area,
        "path": path.relative_to(root).as_posix(),
        "extension": path.suffix.lower(),
        "bytes": size,
        "status": status,
        "note": note,
    }


def _is_support_name(name: str) -> bool:
    return (
        name in _SUPPORT_EXACT
        or (name.startswith("all_risk_types") and name.endswith(".json"))
        or (name.startswith("tickers_8k") and name.endswith(".json"))
    )


def _stays_at_lexical_path(root: Path, path: Path) -> bool:
    """Reject links and reparse points in any component below the root."""
    try:
        relative = path.relative_to(root)
        expected = root.resolve() / relative
        return path.resolve() == expected
    except (OSError, ValueError, RuntimeError):
        return False


def inventory_data_files(root: Path) -> list[dict]:
    """List selected repository files using path and stat metadata only.

    Symlink entries, including directory symlinks, are skipped rather than
    followed. Missing directories simply contribute no file rows.
    """
    root = Path(root)
    rows: list[dict] = []
    for area, relative in _AREAS:
        base = root / relative
        if not _stays_at_lexical_path(root, base) or not base.is_dir():
            continue
        def on_error(error: OSError) -> None:
            failed = Path(error.filename) if error.filename else base
            try:
                relative_failed = failed.relative_to(root).as_posix()
                if not (relative_failed == relative or relative_failed.startswith(relative + "/")):
                    relative_failed = relative
            except ValueError:
                relative_failed = relative
            rows.append({
                "area": area,
                "path": relative_failed,
                "extension": "",
                "bytes": None,
                "status": "unreadable",
                "note": "Directory could not be enumerated; inventory is partial.",
                "type": "directory",
            })

        for directory, dirs, files in os.walk(base, topdown=True, followlinks=False, onerror=on_error):
            current = Path(directory)
            dirs[:] = sorted(
                name for name in dirs
                if name not in _SKIP_DIRS and _stays_at_lexical_path(root, current / name)
            )
            for name in sorted(files):
                if name in _SKIP_DIRS:
                    continue
                path = current / name
                if _stays_at_lexical_path(root, path):
                    rows.append(_file_row(root, path, area))
    if root.is_dir() and not root.is_symlink():
        try:
            children = sorted(root.iterdir(), key=lambda path: path.name)
        except OSError:
            children = []
        for path in children:
            if _is_support_name(path.name) and _stays_at_lexical_path(root, path) and path.is_file():
                rows.append(_file_row(root, path, "supporting"))
    return sorted(rows, key=lambda row: row["path"])


def data_area_summary(root: Path, files: list[dict] | None = None) -> list[dict]:
    """Summarize selected areas, including absent and empty directories."""
    root = Path(root)
    files = inventory_data_files(root) if files is None else files
    summary = []
    for area, relative in (*_AREAS, ("supporting", "repository root metadata")):
        selected = [row for row in files if row.get("area") == area]
        file_rows = [row for row in selected if row.get("type") != "directory"]
        if area == "supporting":
            present = bool(selected)
        else:
            target = root / relative
            present = _stays_at_lexical_path(root, target) and target.is_dir()
        status = "partial" if present and any(row.get("status") == "unreadable" for row in selected) else ("present" if present else "missing")
        summary.append({
            "area": area,
            "path": relative,
            "status": status,
            "files": len(file_rows),
            "bytes": sum(row["bytes"] for row in file_rows if isinstance(row.get("bytes"), int)),
        })
    return summary


def _audit_row(table, path, status, expected_rows=None, expected_sha256=None, observed_sha256=None) -> dict:
    return {
        "table": table,
        "expected_rows": expected_rows,
        "expected_sha256": expected_sha256,
        "observed_sha256": observed_sha256,
        "status": status,
        "path": path,
    }


def audit_exported_run(run_dir: Path) -> list[dict]:
    """Verify only CSV exports sealed in ``manifest.json`` by streaming hashes.

    ``expected_rows`` is copied from the manifest and never presented as an
    observed row count. No CSV parsing or inferred export discovery occurs.
    """
    run_dir = Path(run_dir)
    if run_dir.is_symlink():
        return [_audit_row(None, "manifest.json", "invalid_manifest")]
    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_symlink():
        return [_audit_row(None, "manifest.json", "invalid_manifest")]
    if not manifest_path.is_file():
        return [_audit_row(None, "manifest.json", "missing")]
    try:
        with manifest_path.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [_audit_row(None, "manifest.json", "invalid_manifest")]
    if not isinstance(manifest, dict):
        return [_audit_row(None, "manifest.json", "invalid_manifest")]
    if "exported_tables" not in manifest:
        return [_audit_row(None, "manifest.json", "unsealed")]
    tables = manifest["exported_tables"]
    if not isinstance(tables, dict) or not tables:
        return [_audit_row(None, "manifest.json", "invalid_manifest")]

    rows = []
    for key, details in sorted(tables.items(), key=lambda item: str(item[0])):
        raw_name = key if isinstance(key, str) else str(key)
        name = raw_name[:-4] if raw_name.endswith(".csv") else raw_name
        safe = bool(_TABLE_NAME.fullmatch(name))
        filename = name + ".csv" if safe else raw_name
        valid_details = (
            isinstance(details, dict)
            and isinstance(details.get("rows"), int)
            and not isinstance(details.get("rows"), bool)
            and details["rows"] >= 0
            and isinstance(details.get("sha256"), str)
            and bool(_SHA256.fullmatch(details["sha256"]))
        )
        expected_rows = details.get("rows") if isinstance(details, dict) else None
        expected_sha = details.get("sha256") if isinstance(details, dict) else None
        if not safe or not valid_details:
            rows.append(_audit_row(raw_name, filename, "invalid_manifest", expected_rows, expected_sha))
            continue
        csv_path = run_dir / filename
        if csv_path.is_symlink():
            rows.append(_audit_row(name, filename, "invalid_manifest", expected_rows, expected_sha))
            continue
        if not csv_path.is_file():
            rows.append(_audit_row(name, filename, "missing", expected_rows, expected_sha))
            continue
        try:
            with csv_path.open("rb") as stream:
                prefix = stream.read(200)
                if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
                    rows.append(_audit_row(name, filename, "lfs_pointer", expected_rows, expected_sha))
                    continue
                digest = hashlib.sha256()
                digest.update(prefix)
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                observed = digest.hexdigest()
        except OSError:
            rows.append(_audit_row(name, filename, "missing", expected_rows, expected_sha))
            continue
        status = "verified" if observed.lower() == expected_sha.lower() else "hash_mismatch"
        rows.append(_audit_row(name, filename, status, expected_rows, expected_sha, observed))
    return rows
