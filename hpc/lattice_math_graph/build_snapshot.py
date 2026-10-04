"""Package the audited source scope for an isolated remote Graphify run."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".planning/graphs/lattice-math-audit"
ARCHIVE = OUT / "source-snapshot.zip"


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def source_files() -> list[Path]:
    paths: set[Path] = set()
    for folder in (
        "src/lattice_strategies",
        "src/contextual_lattice",
        "src/multi_market",
        "scripts/lattice_strategies",
    ):
        paths.update((ROOT / folder).glob("*.py"))
    paths.update((ROOT / "stat-arb/libs/gm-geometry/src").glob("*.cpp"))
    for stem in ("peer_basket", "ou_fit", "excursion"):
        paths.add(ROOT / f"stat-arb/libs/gm-signals/src/{stem}.cpp")
    for stem in ("mahalanobis", "kde", "fastmcd"):
        paths.add(ROOT / f"stat-arb/libs/gm-boundaries/src/{stem}.cpp")
    for app in ("gm-geometry", "gm-signals", "gm-boundaries"):
        paths.add(ROOT / f"stat-arb/apps/{app}/main.cpp")
    for stem in ("options_native", "options_bridge"):
        paths.add(ROOT / f"stat-arb/tools/{stem}.py")
    # Match declaration headers to implementation files in scope.
    paths.update((ROOT / "stat-arb/libs/gm-geometry/include/gm-geometry").glob("*.hpp"))
    for stem in ("peer_basket", "ou_fit", "excursion"):
        paths.add(ROOT / f"stat-arb/libs/gm-signals/include/gm-signals/{stem}.hpp")
    for stem in ("mahalanobis", "kde", "fastmcd"):
        paths.add(ROOT / f"stat-arb/libs/gm-boundaries/include/gm-boundaries/{stem}.hpp")
    paths.add(ROOT / "stat-arb/libs/gm-boundaries/src/fastmcd_detail.hpp")
    missing = sorted(str(path.relative_to(ROOT)) for path in paths if not path.is_file())
    if missing:
        raise FileNotFoundError(f"Missing scoped source files: {missing}")
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = source_files()
    records = []
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(rel, data)
            records.append({"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    receipt = {
        "scope": "lattice-math-audit",
        "root_git_head": git_head(ROOT),
        "native_git_head": git_head(ROOT / "stat-arb"),
        "files": records,
        "archive_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
    }
    (OUT / "SOURCE_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(files), "bytes": sum(r["size"] for r in records), "archive_bytes": ARCHIVE.stat().st_size, "root_git_head": receipt["root_git_head"], "native_git_head": receipt["native_git_head"]}))


if __name__ == "__main__":
    main()
