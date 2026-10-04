"""Record current read-set drift without changing Graphify's native outputs."""

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(run_root: Path, graphs: Path) -> None:
    manifest = json.loads((run_root / "source-manifest.json").read_text(encoding="utf-8-sig"))
    roots = {row["namespace"]: Path(row["path"]) for row in manifest["checkouts"]}
    drift = []
    for row in manifest["files"]:
        path = roots[row["namespace"]] / row["relative_path"]
        actual = digest(path) if path.is_file() else None
        if actual != row["sha256"]:
            drift.append({
                "snapshot_path": row["snapshot_path"],
                "snapshot_sha256": row["sha256"],
                "live_sha256": actual,
            })
    record = {
        "run_id": manifest["run_id"],
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_source_files": len(manifest["files"]),
        "live_drift_count": len(drift),
        "live_drift": drift,
        "meaning": "Graph was valid for the archived source snapshot. Changed live files may have outdated nodes or edges.",
    }
    (graphs / "FRESHNESS.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Graphify source snapshot freshness", "",
        f"Run: `{manifest['run_id']}`", "",
        f"Verified snapshot: {len(manifest['files'])} hashed Python files.",
        f"Live source drift at {record['checked_utc']}: **{len(drift)} files**.", "",
        "Graphify's native report and graph describe the archived snapshot."
        " Cross-checkout inferred links and current runtime wiring need separate verification.", "",
    ]
    for row in drift:
        lines.extend([
            f"- `{row['snapshot_path']}`",
            f"  - Snapshot SHA256: `{row['snapshot_sha256']}`",
            f"  - Live SHA256: `{row['live_sha256']}`",
        ])
    (graphs / "FRESHNESS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    receipt_path = graphs / "BUILD_RECEIPT.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["run_id"] != manifest["run_id"]:
        raise ValueError("Graph receipt and source manifest run IDs differ")
    receipt["live_source_drift_count"] = len(drift)
    receipt["live_source_drift"] = drift
    receipt["snapshot_current_at_check"] = not drift
    receipt["state"] = "VALIDATED_GRAPHIFY_SNAPSHOT_WITH_LIVE_DRIFT" if drift else "VALIDATED_GRAPHIFY_CURRENT_SNAPSHOT"
    receipt["freshness_checked_utc"] = record["checked_utc"]
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    archive = graphs / "archive" / manifest["run_id"]
    archive.mkdir(parents=True, exist_ok=True)
    for name in (
        "graph.json", "graph.html", "GRAPH_REPORT.md", "SOURCE_MAP.json",
        "BUILD_RECEIPT.json", "FRESHNESS.json", "FRESHNESS.md",
        "CROSS_CHECKOUT_EDGE_AUDIT.json",
    ):
        shutil.copy2(graphs / name, archive / name)
    for source, name in (
        (run_root / "source-manifest.json", "source-manifest.json"),
        (run_root / "remote-output" / "build.log", "build.log"),
        (run_root / "remote-output" / "package.txt", "package.txt"),
    ):
        shutil.copy2(source, archive / name)
    print(json.dumps({"run_id": manifest["run_id"], "live_drift_count": len(drift), "archive": str(archive)}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: mark_snapshot_freshness.py RUN_ROOT GRAPHS_DIR")
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
