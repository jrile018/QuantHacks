"""Offline validation of independently owned team-source contributions.

This gate checks registration and a small synthetic smoke fixture. It never
downloads originals or infers that a discovered source is available locally.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from src.document_transcript import extract_path
from src.document_evidence import build_evidence


SOURCE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_METADATA_BYTES = 1_000_000
MAX_FIXTURE_BYTES = 256_000


def _has_symlink(path: Path) -> bool:
    path = path.absolute()
    return any(part.is_symlink() for part in (path, *path.parents))


def _read_text_limited(path: Path, errors: list[str]) -> str | None:
    if _has_symlink(path):
        errors.append(f"{path}: symlink path is not allowed")
        return None
    try:
        if path.stat().st_size > MAX_METADATA_BYTES:
            errors.append(f"{path}: size exceeds {MAX_METADATA_BYTES} bytes")
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path}: missing or unreadable UTF-8 file: {exc}")
        return None


def _read_json(path: Path, errors: list[str]):
    data = _read_text_limited(path, errors)
    if data is None:
        return None
    try:
        value = json.loads(data)
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{path}: expected a JSON object")
        return None
    return value


def _read_jsonl(path: Path, errors: list[str]) -> list[tuple[int, dict]]:
    data = _read_text_limited(path, errors)
    if data is None:
        return []
    lines = data.lstrip("\ufeff").splitlines()
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(row, dict):
            errors.append(f"{path}:{number}: expected a JSON object")
            continue
        rows.append((number, row))
    if not rows:
        errors.append(f"{path}: manifest.jsonl must contain at least one record")
    return rows


def _placeholders(value) -> bool:
    if isinstance(value, str):
        return "REPLACE_" in value
    if isinstance(value, dict):
        return any(_placeholders(item) for item in value.values())
    if isinstance(value, list):
        return any(_placeholders(item) for item in value)
    return False


def _relative_child(base: Path, value: str, expected: Path) -> bool:
    if not value or "\\" in value or Path(value).is_absolute():
        return False
    if _has_symlink(expected) or _has_symlink(base / value):
        return False
    try:
        (base / value).resolve(strict=False).relative_to(expected.resolve(strict=False))
    except ValueError:
        return False
    return True


def _url_ok(value) -> bool:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and parsed.fragment == "" and parsed.port in (None, 80, 443))
    except ValueError:
        return False


def _utc_ok(value) -> bool:
    if not isinstance(value, str) or not value or not (value.endswith("Z") or value.endswith("+00:00")):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.utcoffset() == timedelta(0)
    except ValueError:
        return False


def _row_identity(row: dict, label: str, source_id: str, seen: dict[str, str], errors: list[str]):
    document_id = row.get("document_id")
    if not isinstance(document_id, str) or not document_id.startswith(source_id + ":") or not document_id[len(source_id) + 1:].strip() or document_id != document_id.strip():
        errors.append(f"{label}: document_id must be namespaced as {source_id}:<stable-id>")
    if isinstance(document_id, str) and document_id in seen:
        errors.append(f"{label}: duplicate document_id {document_id!r}; first at {seen[document_id]}")
    elif isinstance(document_id, str):
        seen[document_id] = label


def _validate_row(row: dict, label: str, source_id: str, manifest: Path,
                  raw_root: Path, seen: dict[str, str], errors: list[str]):
    _row_identity(row, label, source_id, seen, errors)
    value = row.get("source_path")
    prefix = f"../../../data/raw/team_sources/{source_id}/"
    if not isinstance(value, str) or not value.startswith(prefix) or not _relative_child(manifest.parent, value, raw_root):
        errors.append(f"{label}: source_path must be a relative path inside data/raw/team_sources/{source_id}/")
    if not _url_ok(row.get("source_url")):
        errors.append(f"{label}: source_url must be a canonical http(s) URL")
    digest = row.get("source_sha256")
    if digest is not None and (not isinstance(digest, str) or not SHA256.fullmatch(digest)):
        errors.append(f"{label}: source_sha256 must be 64 lowercase hex characters when supplied")
    for key, timestamp in row.items():
        if key.endswith("_at_utc") and timestamp is not None and not _utc_ok(timestamp):
            errors.append(f"{label}: {key} must be an aware UTC timestamp or null")
    if _placeholders(row):
        errors.append(f"{label}: unresolved REPLACE_ placeholder")


def _validate_fixture(root: Path, source_id: str, seen: dict[str, str], errors: list[str]):
    fixture_dir = root / "examples" / "team_sources" / source_id
    manifest = fixture_dir / "manifest.jsonl"
    rows = _read_jsonl(manifest, errors)
    for number, row in rows:
        label = f"{manifest}:{number}"
        _row_identity(row, label, source_id, seen, errors)
        value = row.get("source_path")
        digest = row.get("source_sha256")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            errors.append(f"{label}: source_sha256 is required as 64 lowercase hex characters")
        if isinstance(value, str) and _has_symlink(fixture_dir / value):
            errors.append(f"{label}: symlink fixture source_path is not allowed")
            continue
        if not isinstance(value, str) or not _relative_child(fixture_dir, value, fixture_dir):
            errors.append(f"{label}: source_path must stay inside the source fixture folder")
            continue
        path = (fixture_dir / value).resolve()
        if path.suffix.lower() not in {".txt", ".htm", ".html"}:
            errors.append(f"{label}: native smoke fixture must be TXT or HTML")
        try:
            if path.stat().st_size > MAX_FIXTURE_BYTES:
                errors.append(f"{label}: smoke fixture size exceeds {MAX_FIXTURE_BYTES} bytes")
                continue
            content = path.read_bytes()
            content.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{label}: fixture source_path is missing or not UTF-8: {exc}")
            continue
        if isinstance(digest, str) and SHA256.fullmatch(digest) and hashlib.sha256(content).hexdigest() != digest:
            errors.append(f"{label}: source_sha256 does not match fixture bytes")
            continue
        if path.suffix.lower() in {".txt", ".htm", ".html"}:
            try:
                transcript = extract_path(path, row.get("document_id", ""), digest)
                normalized_text = transcript["normalized_text"]
                if not normalized_text.strip() or "incomplete_text" in transcript["quality_flags"]:
                    raise ValueError("transcript is empty or incomplete")
                if hashlib.sha256(normalized_text.encode("utf-8")).hexdigest() != transcript["text_sha256"]:
                    raise ValueError("transcript text hash mismatch")
                for evidence in build_evidence(transcript):
                    if (evidence["quoted_text"] != normalized_text[evidence["char_start"]:evidence["char_end"]]
                            or evidence["text_sha256"] != transcript["text_sha256"]):
                        raise ValueError("evidence does not match transcript slice")
            except (ValueError, KeyError, TypeError) as exc:
                errors.append(f"{label}: transcript/evidence smoke failed: {exc}")
        if _placeholders(row):
            errors.append(f"{label}: unresolved REPLACE_ placeholder")


def _validate_source(root: Path, folder: Path, seen: dict[str, str], errors: list[str]) -> int:
    if _has_symlink(folder):
        errors.append(f"{folder}: symlink source directory is not allowed")
        return 0
    source_id = folder.name
    if not SOURCE_ID.fullmatch(source_id):
        errors.append(f"{folder}: source directory name must be a lowercase hyphen slug")
    metadata = _read_json(folder / "source.json", errors)
    readme = folder / "README.md"
    readme_text = _read_text_limited(readme, errors)
    if readme_text is not None and not readme_text.strip():
        errors.append(f"{folder}: README.md is required and must be nonempty UTF-8")
    elif readme_text is not None and _placeholders(readme_text):
        errors.append(f"{readme}: unresolved REPLACE_ placeholder")
    if metadata is not None:
        if _placeholders(metadata):
            errors.append(f"{folder / 'source.json'}: unresolved REPLACE_ placeholder")
        for key, timestamp in metadata.items():
            if key.endswith("_at_utc") and timestamp is not None and not _utc_ok(timestamp):
                errors.append(f"{folder / 'source.json'}: {key} must be an aware UTC timestamp or null")
        if metadata.get("schema_version") != "1.0":
            errors.append(f"{folder / 'source.json'}: schema_version must be 1.0")
        if metadata.get("source_id") != source_id or not SOURCE_ID.fullmatch(str(metadata.get("source_id", ""))):
            errors.append(f"{folder / 'source.json'}: source_id must match lowercase source directory slug")
        if not isinstance(metadata.get("owner"), str) or not metadata["owner"].strip():
            errors.append(f"{folder / 'source.json'}: owner is required")
        if not isinstance(metadata.get("stage"), str) or metadata["stage"] not in {"discovery", "extracted"}:
            errors.append(f"{folder / 'source.json'}: stage must be discovery or extracted")
        if not isinstance(metadata.get("engine"), str) or metadata["engine"] not in {"native", "tesseract", "glm"}:
            errors.append(f"{folder / 'source.json'}: engine must be native, tesseract or glm")
        if metadata.get("engine") == "glm":
            if not isinstance(metadata.get("model_revision"), str) or not metadata["model_revision"].strip():
                errors.append(f"{folder / 'source.json'}: model_revision is required for glm")
            cache = metadata.get("model_cache")
            intended = root / "data" / "raw" / "team_sources" / source_id
            if not isinstance(cache, str) or not cache.startswith(f"data/raw/team_sources/{source_id}/") or not _relative_child(root, cache, intended):
                errors.append(f"{folder / 'source.json'}: model_cache must be relative inside ignored data/raw/team_sources/{source_id}/")
    manifest = folder / "manifest.jsonl"
    rows = _read_jsonl(manifest, errors)
    raw_root = root / "data" / "raw" / "team_sources" / source_id
    for number, row in rows:
        _validate_row(row, f"{manifest}:{number}", source_id, manifest, raw_root, seen, errors)
    if metadata is not None and metadata.get("stage") == "extracted":
        _validate_fixture(root, source_id, seen, errors)
    return len(rows)


def validate_sources(repo_root: str | Path, source_dir: str | Path | None = None) -> dict:
    """Return deterministic JSON-ready gate results; never fetch source URLs."""
    root = Path(repo_root).resolve()
    sources_root = root / "configs" / "sources"
    errors: list[str] = []
    if _has_symlink(sources_root):
        errors.append(f"{sources_root}: symlink registry is not allowed")
        return {"ok": False, "sources": 0, "documents": 0, "errors": errors}
    if sources_root.exists() and not sources_root.is_dir():
        errors.append(f"{sources_root}: configs/sources must be a directory")
        return {"ok": False, "sources": 0, "documents": 0, "errors": errors}
    folders = sorted(path for path in sources_root.iterdir() if path.is_dir()) if sources_root.is_dir() else []
    if source_dir is not None:
        selected = Path(source_dir)
        selected = (root / selected).resolve() if not selected.is_absolute() else selected.resolve()
        if selected.parent != sources_root.resolve() or selected not in folders:
            errors.append(f"{source_dir}: --source-dir must identify an existing configs/sources/<source-id> folder")
            return {"ok": False, "sources": 0, "documents": 0, "errors": errors}
    seen: dict[str, str] = {}
    documents = sum(_validate_source(root, folder, seen, errors) for folder in folders)
    return {"ok": not errors, "sources": len(folders), "documents": documents, "errors": errors}
