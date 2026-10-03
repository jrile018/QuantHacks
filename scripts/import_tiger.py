"""Copy local Massive cache and study outputs into a Tiger PostgreSQL service.

Uses the authenticated Tiger CLI, so no database password is read or saved here.
Source files stay on disk after a verified import.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SourceFile:
    path: str
    kind: str
    sha256: str
    body: bytes


@dataclass(frozen=True)
class StudyRun:
    run_id: str
    path: str
    manifest: dict


@dataclass(frozen=True)
class StudyRow:
    run_id: str
    table_name: str
    row_number: int
    data: dict


def collect_data(root: Path) -> tuple[list[SourceFile], list[StudyRun], list[StudyRow]]:
    """Inventory every cached response and every manifested study CSV."""
    files: list[SourceFile] = []
    runs: list[StudyRun] = []
    rows: list[StudyRow] = []

    def add_file(path: Path, kind: str) -> bytes:
        body = path.read_bytes()
        files.append(SourceFile(path.relative_to(root).as_posix(), kind,
                                hashlib.sha256(body).hexdigest(), body))
        return body

    for path in sorted((root / ".massive_cache").glob("*.json")):
        body = add_file(path, "api_response")
        json.loads(body)

    for manifest_path in sorted((root / "data" / "processed").glob("**/manifest.json")):
        body = add_file(manifest_path, "study_manifest")
        run_path = manifest_path.parent.relative_to(root).as_posix()
        run_id = hashlib.sha256(run_path.encode("utf-8") + b"\0" + body).hexdigest()
        manifest = json.loads(body)
        runs.append(StudyRun(run_id, run_path, manifest))
        for csv_path in sorted(manifest_path.parent.glob("*.csv")):
            add_file(csv_path, "study_csv")
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for number, row in enumerate(csv.DictReader(handle), start=1):
                    rows.append(StudyRow(run_id, csv_path.stem, number, row))

    return files, runs, rows


def quote(value: str) -> str:
    """Quote a text literal for the SQL file; binary content uses base64."""
    return "'" + value.replace("'", "''") + "'"


def render_sql(files: list[SourceFile], runs: list[StudyRun], rows: list[StudyRow]) -> str:
    """Generate an idempotent, single-transaction import."""
    statements = [
        "CREATE SCHEMA IF NOT EXISTS quant_hacks;",
        """CREATE TABLE IF NOT EXISTS quant_hacks.source_files (
            relative_path text PRIMARY KEY,
            kind text NOT NULL,
            sha256 text NOT NULL,
            body bytea NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT now()
        );""",
        """CREATE TABLE IF NOT EXISTS quant_hacks.study_runs (
            run_id text PRIMARY KEY,
            source_path text NOT NULL,
            manifest jsonb NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT now()
        );""",
        """CREATE TABLE IF NOT EXISTS quant_hacks.study_rows (
            run_id text NOT NULL REFERENCES quant_hacks.study_runs(run_id),
            table_name text NOT NULL,
            row_number integer NOT NULL,
            row_data jsonb NOT NULL,
            PRIMARY KEY (run_id, table_name, row_number)
        );""",
        "CREATE INDEX IF NOT EXISTS study_rows_by_table ON quant_hacks.study_rows (table_name);",
        """CREATE OR REPLACE VIEW quant_hacks.api_responses AS
            SELECT relative_path, sha256, convert_from(body, 'UTF8')::jsonb AS payload
            FROM quant_hacks.source_files WHERE kind = 'api_response';""",
    ]

    if files:
        values = []
        for source in files:
            encoded = base64.b64encode(source.body).decode("ascii")
            values.append(f"({quote(source.path)}, {quote(source.kind)}, {quote(source.sha256)}, "
                          f"decode({quote(encoded)}, 'base64'))")
        statements.append("INSERT INTO quant_hacks.source_files "
                          "(relative_path, kind, sha256, body) VALUES\n" + ",\n".join(values) +
                          " ON CONFLICT (relative_path) DO UPDATE SET "
                          "kind = EXCLUDED.kind, sha256 = EXCLUDED.sha256, "
                          "body = EXCLUDED.body, imported_at = now();")

    if runs:
        values = [f"({quote(run.run_id)}, {quote(run.path)}, "
                  f"{quote(json.dumps(run.manifest, ensure_ascii=True))}::jsonb)" for run in runs]
        statements.append("INSERT INTO quant_hacks.study_runs "
                          "(run_id, source_path, manifest) VALUES\n" + ",\n".join(values) +
                          " ON CONFLICT (run_id) DO UPDATE SET "
                          "source_path = EXCLUDED.source_path, manifest = EXCLUDED.manifest;")
        run_ids = ", ".join(quote(run.run_id) for run in runs)
        statements.append(f"DELETE FROM quant_hacks.study_rows WHERE run_id IN ({run_ids});")

    if rows:
        values = [f"({quote(row.run_id)}, {quote(row.table_name)}, {row.row_number}, "
                  f"{quote(json.dumps(row.data, ensure_ascii=True))}::jsonb)" for row in rows]
        statements.append("INSERT INTO quant_hacks.study_rows "
                          "(run_id, table_name, row_number, row_data) VALUES\n" + ",\n".join(values) + ";")

    return "\n\n".join(statements) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import local Massive study files into Tiger")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--service-id", help="Tiger service ID (for example, jy5bbko5ff)")
    parser.add_argument("--tiger-exe", default="tiger", help="Tiger CLI executable")
    parser.add_argument("--dry-run", action="store_true", help="inventory without database writes")
    args = parser.parse_args()

    files, runs, rows = collect_data(args.root.resolve())
    if not files:
        parser.error("no cached API responses or manifested study output found")
    print(f"Found {len(files)} source files, {len(runs)} study runs, and {len(rows)} study rows")
    if args.dry_run:
        return 0
    if not args.service_id:
        parser.error("--service-id is required for an import")

    sql = render_sql(files, runs, rows)
    temp_parent = args.root.resolve() / "data" / "processed"
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tiger-import-", dir=temp_parent) as directory:
        sql_path = Path(directory) / "import.sql"
        sql_path.write_text(sql, encoding="utf-8")
        command = [args.tiger_exe, "db", "query", args.service_id, "--file", str(sql_path)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Tiger import failed: {result.stderr.strip() or result.stdout.strip()}")
    print(f"Imported into Tiger service {args.service_id}, schema quant_hacks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
