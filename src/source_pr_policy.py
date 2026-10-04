"""Fail-closed path gate for independently owned team-source pull requests.

This module checks the scope of a change. Source metadata and manifest
semantics are checked separately by ``src.source_validation``.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Iterable


SOURCE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MODULE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")
EXAMPLE_DIR = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_EXAMPLE_BYTES = 1024 * 1024
REQUIRED_FILES = ("source.json", "manifest.jsonl", "README.md")
BLOCKED_EXAMPLE_NAMES = frozenset({"raw", "processed", "cache", "caches", "credential",
                                   "credentials", "secret", "secrets", "password", "passwords",
                                   "token", "tokens", "key", "keys", "private-key", "artifact",
                                   "artifacts", "result", "results", "output", "outputs", "data"})


@dataclass(frozen=True)
class PolicyResult:
    eligible: bool
    source_id: str | None
    errors: list[str]

    def as_dict(self) -> dict:
        return {"eligible": self.eligible, "source_id": self.source_id,
                "errors": self.errors}


def _registered_sources(repo_root: Path) -> dict[str, str]:
    """Map Python adapter module names to source IDs in the checked-out tree."""
    registry = repo_root / "configs" / "sources"
    if ((repo_root / "configs").is_symlink() or not registry.is_dir()
            or registry.is_symlink()):
        return {}
    modules = {}
    for folder in registry.iterdir():
        if not folder.is_dir() or folder.is_symlink() or not SOURCE_ID.fullmatch(folder.name):
            continue
        if not (folder / "source.json").is_file():
            continue
        module = folder.name.replace("-", "_")
        if module in modules:
            modules[module] = ""  # ambiguous module names must never be granted
        else:
            modules[module] = folder.name
    return modules


def _parts(path: str) -> tuple[str, ...] | None:
    if not isinstance(path, str) or not path or "\\" in path or "\0" in path:
        return None
    if path.startswith("/") or re.match(r"[A-Za-z]:", path):
        return None
    parts = tuple(path.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        return None
    return parts


def _source_for_path(parts: tuple[str, ...], modules: dict[str, str]) -> str | None:
    if len(parts) == 4 and parts[:2] == ("configs", "sources"):
        source_id = parts[2]
        if SOURCE_ID.fullmatch(source_id) and parts[3] in REQUIRED_FILES:
            return source_id
    if len(parts) == 3 and parts[:2] == ("docs", "sources"):
        if parts[2].endswith(".md"):
            source_id = parts[2][:-3]
            if SOURCE_ID.fullmatch(source_id):
                return source_id
    if len(parts) >= 4 and parts[:2] == ("examples", "team_sources"):
        source_id = parts[2]
        children = parts[3:]
        if not SOURCE_ID.fullmatch(source_id):
            return None
        if any(not EXAMPLE_DIR.fullmatch(part) or part in BLOCKED_EXAMPLE_NAMES
               for part in children[:-1]):
            return None
        if len(children) == 1 and children[0] == "manifest.jsonl":
            return source_id
        if children[-1].endswith((".txt", ".html")) and children[-1] not in (".txt", ".html"):
            stem = children[-1].rsplit(".", 1)[0]
            if EXAMPLE_DIR.fullmatch(stem) and stem not in BLOCKED_EXAMPLE_NAMES:
                return source_id
    if len(parts) == 2 and parts[0] in ("src", "tests"):
        name = parts[1]
        if parts[0] == "src" and name.endswith("_adapter.py"):
            module = name[:-11]
        elif parts[0] == "tests" and name.startswith("test_") and name.endswith("_adapter.py"):
            module = name[5:-11]
        else:
            return None
        if MODULE.fullmatch(module):
            return modules.get(module) or None
    return None


def _check_on_disk(repo_root: Path, parts: tuple[str, ...], errors: list[str]) -> None:
    current = repo_root
    for part in parts:
        current = current / part
        if current.is_symlink():
            errors.append(f"symlink path is not allowed: {'/'.join(parts)}")
            return
    if current.exists():
        if not current.is_file():
            errors.append(f"changed path is not a regular file: {'/'.join(parts)}")
            return
        limit = MAX_EXAMPLE_BYTES if parts[:2] == ("examples", "team_sources") else MAX_FILE_BYTES
        try:
            size = current.stat().st_size
        except OSError as exc:
            errors.append(f"cannot stat {'/'.join(parts)}: {exc}")
            return
        if size > limit:
            errors.append(f"file exceeds {limit} byte limit: {'/'.join(parts)}")


def validate_changed_paths(paths: Iterable[str], repo_root: Path | str,
                           branch: str) -> PolicyResult:
    """Validate every affected old/new Git path against one registered source.

    Callers must supply both old and new names of a rename. A missing optional
    path is acceptable as a deletion; required source files must remain.
    """
    root = Path(repo_root)
    errors: list[str] = []
    if not root.is_dir() or root.is_symlink():
        return PolicyResult(False, None, ["repository root is not a regular directory"])
    modules = _registered_sources(root)
    registered = set(modules.values()) - {""}
    affected: set[str] = set()
    saw_path = False
    for path in paths:
        saw_path = True
        parts = _parts(path)
        if parts is None:
            errors.append(f"unsafe changed path: {path!r}")
            continue
        source_id = _source_for_path(parts, modules)
        if source_id is None:
            errors.append(f"path outside source-only allowance: {path}")
            continue
        affected.add(source_id)
        _check_on_disk(root, parts, errors)
    if not saw_path:
        errors.append("no changed paths")
    if len(affected) != 1:
        errors.append("exactly one source namespace must be affected")
    source_id = next(iter(affected)) if len(affected) == 1 else None
    if source_id is not None:
        if source_id not in registered:
            errors.append(f"source is not registered: {source_id}")
        branch_prefix = f"codex/source-{source_id}-"
        owner = branch[len(branch_prefix):] if branch.startswith(branch_prefix) else ""
        if not SOURCE_ID.fullmatch(owner):
            errors.append(f"branch does not exclusively name source {source_id}: {branch}")
        folder = root / "configs" / "sources" / source_id
        if (root / "configs").is_symlink() or (root / "configs" / "sources").is_symlink() or folder.is_symlink():
            errors.append(f"source directory has a symlink ancestor: {source_id}")
        for name in REQUIRED_FILES:
            file = folder / name
            if not file.is_file() or file.is_symlink():
                errors.append(f"required source file missing or unsafe: configs/sources/{source_id}/{name}")
        metadata = folder / "source.json"
        if metadata.is_file() and not metadata.is_symlink():
            try:
                value = json.loads(metadata.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or value.get("source_id") != source_id:
                    errors.append(f"source.json source_id must remain {source_id}")
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(f"cannot read source.json for {source_id}: {exc}")
        adapter = root / "src" / f"{source_id.replace('-', '_')}_adapter.py"
        if adapter.is_symlink():
            errors.append(f"source adapter is a symlink: src/{adapter.name}")
        if adapter.exists() and not adapter.is_symlink():
            test = root / "tests" / f"test_{source_id.replace('-', '_')}_adapter.py"
            if not test.is_file() or test.is_symlink():
                errors.append(f"adapter requires matching test: tests/{test.name}")
    return PolicyResult(not errors, source_id, errors)


def _git(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True,
                            check=False)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise ValueError(f"git {' '.join(args[:2])} failed: {message}")
    return result.stdout


def changed_paths_between(repo_root: Path | str, base: str, head: str) -> list[str]:
    """Return both path names for renames, using Git's NUL-delimited output."""
    root = Path(repo_root)
    if not root.is_dir():
        raise ValueError(f"repository root does not exist: {root}")
    commits = []
    for ref in (base, head):
        if not ref or "\0" in ref:
            raise ValueError("empty or malformed Git ref")
        raw = _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
        commits.append(raw.decode("ascii").strip())
    actual_head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if actual_head != commits[1]:
        raise ValueError("checked-out HEAD does not match --head")
    raw = _git(root, "diff", "--name-status", "-z", "-M", "--no-ext-diff",
               "--no-textconv", commits[0], commits[1], "--")
    tokens = raw.split(b"\0")
    if tokens[-1:] == [b""]:
        tokens.pop()
    paths = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii", "strict")
        index += 1
        count = 2 if status.startswith(("R", "C")) else 1
        if not status or status[0] not in "ACDMRTUXB" or index + count > len(tokens):
            raise ValueError("malformed Git diff name-status output")
        paths.extend(token.decode("utf-8", "surrogateescape") for token in tokens[index:index + count])
        index += count
    return paths
