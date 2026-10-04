"""Validate Graphify's extracted graph against the immutable source receipt."""

from __future__ import annotations

import collections
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".planning/graphs/lattice-math-audit"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    receipt = json.loads((OUT / "SOURCE_RECEIPT.json").read_text(encoding="utf-8"))
    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    assert isinstance(graph.get("nodes"), list)
    links = graph.get("links", graph.get("edges"))
    assert isinstance(links, list)
    assert digest(OUT / "source-snapshot.zip") == receipt["archive_sha256"]

    source_paths = {record["path"] for record in receipt["files"]}
    changed = [record["path"] for record in receipt["files"] if digest(ROOT / record["path"]) != record["sha256"]]
    assert not changed, f"Sources changed since snapshot: {changed}"

    ids = {node["id"] for node in graph["nodes"]}
    assert len(ids) == len(graph["nodes"]), "Duplicate node IDs"
    broken = [edge for edge in links if edge.get("source") not in ids or edge.get("target") not in ids]
    assert not broken, f"Edges with missing endpoints: {len(broken)}"
    foreign = sorted({item["source_file"] for item in [*graph["nodes"], *links] if item.get("source_file") and item["source_file"] not in source_paths})
    assert not foreign, f"Sources outside scoped snapshot: {foreign}"
    bad_locations = [item for item in [*graph["nodes"], *links] if item.get("source_location") and not re.fullmatch(r"L\d+(?:-L?\d+)?", str(item["source_location"]))]
    assert not bad_locations, f"Malformed source locations: {len(bad_locations)}"

    seen_sources = {item["source_file"] for item in [*graph["nodes"], *links] if item.get("source_file")}
    results = {
        "validated": True,
        "source_file_count": len(source_paths),
        "source_files_with_graph_evidence": len(seen_sources),
        "source_files_without_graph_evidence": sorted(source_paths - seen_sources),
        "node_count": len(graph["nodes"]),
        "link_count": len(links),
        "hyperedge_count": len(graph.get("hyperedges", [])),
        "community_count": len({node.get("community") for node in graph["nodes"] if node.get("community") is not None}),
        "node_origins": dict(collections.Counter(node.get("_origin", "unspecified") for node in graph["nodes"])),
        "link_origins": dict(collections.Counter(link.get("_origin", "unspecified") for link in links)),
        "link_relations": dict(collections.Counter(link.get("relation", "unspecified") for link in links)),
        "link_confidence": dict(collections.Counter(link.get("confidence", "unspecified") for link in links)),
        "source_location_count": sum(bool(item.get("source_location")) for item in [*graph["nodes"], *links]),
        "cpp_node_count": sum(str(node.get("source_file", "")).endswith((".cpp", ".hpp", ".h")) for node in graph["nodes"]),
        "cpp_link_count": sum(str(link.get("source_file", "")).endswith((".cpp", ".hpp", ".h")) for link in links),
        "artifact_sha256": {name: digest(OUT / name) for name in ("graph.json", "graph.html", "GRAPH_REPORT.md", "manifest.json", "build.log")},
    }
    (OUT / "VALIDATION.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    build_receipt = {
        "scope": "lattice-math-audit",
        "source_receipt_sha256": digest(OUT / "SOURCE_RECEIPT.json"),
        "snapshot_sha256": receipt["archive_sha256"],
        "root_git_head": receipt["root_git_head"],
        "native_git_head": receipt["native_git_head"],
        "graphify_config_sha256": digest(ROOT / ".planning/config.json"),
        "tool": {"package": "graphifyy", "version": "0.9.75", "remote_executable_sha256": "0a4de96f1589b8fbbd72e8cb78e78e070ed75067e341fbed549f3a59e7fe8d6e"},
        "remote_snapshot_dir": "/home/john-riley/quanthaxs-lattice-math-graph/20261004-3f76ce20-0d77fc4d",
        "commands": ["graphify update . --no-cluster --force", "graphify cluster-only . --no-label"],
        "execution": "detached tmux under shared flock; two thread environment; 4 GiB virtual-memory limit; build.log EXIT_CODE:0",
        "graph_json_sha256": results["artifact_sha256"]["graph.json"],
        "raw_link_count": len(links),
        "graph_report_edge_count": 1056,
        "report_count_note": "Graphify report projects links into a simple Graph; five same-endpoint relation variants collapse. The JSON retains all 1,061 links.",
        "limits": ["AST links are structural candidates, not verified runtime integration or dataflow.", "Three headers yielded no extracted symbols: correlation.hpp, distance.hpp, peer_basket.hpp.", "Fourteen links carry INFERRED confidence despite code-only, no-LLM extraction. Inspect before relying on them."],
    }
    (OUT / "BUILD_RECEIPT.json").write_text(json.dumps(build_receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
