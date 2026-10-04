"""Flag Graphify edges whose endpoints come from separate checkouts."""

import json
import sys
from pathlib import Path


def main(graphs: Path) -> None:
    graph = json.loads((graphs / "graph.json").read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph["nodes"]}
    flagged = []
    for edge in graph.get("edges", graph.get("links", [])):
        source_file = nodes[edge["source"]].get("source_file") or ""
        target_file = nodes[edge["target"]].get("source_file") or ""
        if not source_file or not target_file:
            continue
        source_checkout = source_file.split("/", 1)[0]
        target_checkout = target_file.split("/", 1)[0]
        if source_checkout == target_checkout:
            continue
        flagged.append({
            "source_id": edge["source"], "target_id": edge["target"],
            "source_file": source_file, "target_file": target_file,
            "relation": edge.get("relation"), "confidence": edge.get("confidence"),
            "source_location": edge.get("source_location"),
        })
    result = {
        "note": "These Graphify links cross independent checkout namespaces. Treat each as an unresolved candidate, not verified runtime wiring.",
        "count": len(flagged), "edges": flagged,
    }
    (graphs / "CROSS_CHECKOUT_EDGE_AUDIT.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cross_checkout_edges": len(flagged)}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_cross_checkout.py .planning/graphs")
    main(Path(sys.argv[1]))
