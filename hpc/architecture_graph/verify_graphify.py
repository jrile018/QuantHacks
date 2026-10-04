"""Verify and publish a namespaced, source-hashed Graphify code graph."""

import hashlib
import json
import shutil
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(run_root: Path, project_root: Path) -> None:
    manifest_path = run_root / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    output = run_root / "remote-output"
    raw = output / "graph.json"
    graph = json.loads(raw.read_text(encoding="utf-8"))
    nodes = graph.get("nodes")
    edges = graph.get("edges", graph.get("links"))
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Graphify graph must contain nodes and edges or links arrays")
    if not nodes or not edges:
        raise ValueError("Graphify graph is empty")

    inputs = {row["snapshot_path"]: row for row in manifest["files"]}
    if len(inputs) != len(manifest["files"]):
        raise ValueError("Duplicate snapshot source path")
    for relative, row in inputs.items():
        snapshot = run_root / "source" / relative
        if digest(snapshot) != row["sha256"] or snapshot.stat().st_size != row["bytes"]:
            raise ValueError(f"Source mismatch: {relative}")
    checkout_roots = {row["namespace"]: Path(row["path"]) for row in manifest["checkouts"]}
    live_drift = []
    for row in manifest["files"]:
        live = checkout_roots[row["namespace"]] / row["relative_path"]
        if not live.is_file() or digest(live) != row["sha256"]:
            live_drift.append(row["snapshot_path"])
    if live_drift:
        raise ValueError(f"Source changed after snapshot: {live_drift[:10]}")

    ids = {node.get("id") for node in nodes}
    if None in ids or len(ids) != len(nodes):
        raise ValueError("Missing or duplicate Graphify node IDs")
    missing = [(edge.get("source"), edge.get("target")) for edge in edges
               if edge.get("source") not in ids or edge.get("target") not in ids]
    if missing:
        raise ValueError(f"Dangling Graphify edges: {missing[:5]}")

    source_map = {}
    unlocated = []
    for node in nodes:
        source = node.get("source_file")
        if not source:
            unlocated.append(node["id"])
            continue
        if source not in inputs:
            raise ValueError(f"Graph node has source outside whitelist: {source}")
        source_map.setdefault(source, []).append(node["id"])
    for value in source_map.values():
        value.sort()

    required = ("graph.json", "graph.html", "GRAPH_REPORT.md")
    for name in required:
        if not (output / name).is_file() or (output / name).stat().st_size == 0:
            raise ValueError(f"Missing or empty Graphify artifact: {name}")
    log = (output / "build.log").read_text(encoding="utf-8")
    if "EXIT_CODE:0" not in log.splitlines()[-1]:
        raise ValueError("Graphify build lacks a successful exit code")

    destination = project_root / ".planning" / "graphs"
    destination.mkdir(parents=True, exist_ok=True)
    previous_receipt = destination / "BUILD_RECEIPT.json"
    if previous_receipt.exists():
        previous = json.loads(previous_receipt.read_text(encoding="utf-8"))
        previous_run = previous.get("run_id")
        if not previous_run or previous_run == manifest["run_id"]:
            raise ValueError("Existing graph has no distinct archived run identity")
        archive = destination / "archive" / previous_run
        archive.mkdir(parents=True, exist_ok=True)
        for old_name in (*required, "SOURCE_MAP.json", "BUILD_RECEIPT.json"):
            old = destination / old_name
            if old.exists():
                saved = archive / old_name
                if saved.exists() and digest(saved) != digest(old):
                    raise ValueError(f"Conflicting graph archive: {saved}")
                if not saved.exists():
                    shutil.copy2(old, saved)
    for name in required:
        target = destination / name
        if target.exists() and not previous_receipt.exists():
            raise FileExistsError(f"Refusing to replace unmanaged graph: {target}")
        shutil.copy2(output / name, target)

    mapping = {
        "run_id": manifest["run_id"],
        "note": "Node source_file maps to a hashed snapshot input; imports across namespaces are not runtime-resolved.",
        "files": [dict(row, node_ids=source_map.get(row["snapshot_path"], []))
                  for row in manifest["files"]],
        "unlocated_node_ids": sorted(unlocated),
    }
    (destination / "SOURCE_MAP.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "run_id": manifest["run_id"],
        "state": "VALIDATED_GRAPHIFY_BUILD",
        "tool": "graphifyy==0.9.75",
        "commands": ["graphify update . --no-cluster", "graphify cluster-only . --no-label"],
        "remote_host_alias": "home-pc",
        "source_files": len(inputs),
        "source_bytes": sum(row["bytes"] for row in inputs.values()),
        "source_manifest_sha256": digest(manifest_path),
        "graph_sha256": digest(raw),
        "graph_html_sha256": digest(output / "graph.html"),
        "graph_report_sha256": digest(output / "GRAPH_REPORT.md"),
        "build_log_sha256": digest(output / "build.log"),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "hyperedge_count": len(graph.get("hyperedges", [])),
        "community_count": len({node.get("community") for node in nodes if node.get("community") is not None}),
        "located_node_count": len(nodes) - len(unlocated),
        "limitations": [
            "Graphify emits links rather than edges in its native NetworkX JSON; the GSD reader supports either.",
            "AST relations are code structure, not runtime or architecture contract proof.",
            "Cross-checkout imports are unresolved unless independently verified.",
        ],
    }
    text = json.dumps(receipt, indent=2) + "\n"
    (destination / "BUILD_RECEIPT.json").write_text(text, encoding="utf-8")
    (run_root / "receipt.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_graphify.py RUN_ROOT PROJECT_ROOT")
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
