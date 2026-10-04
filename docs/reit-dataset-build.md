# Immutable REIT research snapshots

`src.reit_dataset.publish_snapshot(output_root, *, universe, inventory, quality,
histories, network, documents, provenance, source_root=None)` accepts JSON-compatible builder
outputs. `documents` is an array of retained document receipts, or an object with
a `documents` array. It returns the absolute `snapshot_dir`, `fingerprint`,
counts, hashes, coverage gaps, and readiness flags. It performs no network calls.

```python
from src.reit_dataset import publish_snapshot, verify_snapshot
from pathlib import Path

root = Path.cwd()  # Project root containing the retained source files.

snapshot = publish_snapshot(
    'data/processed/reit_build/20261003/snapshots',
    universe=universe, inventory=inventory, quality=quality,
    histories=histories, network=network, documents=documents,
    provenance={'scope': 'retained and acquired cohort', 'as_of': as_of},
    source_root=root,
)
assert verify_snapshot(snapshot['snapshot_dir'], source_root=root)['valid']
```

The publisher retains full input JSON and records every input fingerprint and the implementation
hashes of the publisher and upstream REIT builders. Source bytes are streamed
through SHA256; huge originals are referenced rather than copied. Extraction
JSON is independently hashed and must bind to the same raw hash. Its source URL,
accession, and source path must match whenever supplied; missing URL/accession
identity is reported as a gap. SEC archive URL accession/CIK conflicts fail.
Hash conflicts, invalid extraction JSON, malformed array types, and non-JSON
values fail publication. Missing retained sources remain explicit coverage gaps.

Supplying `source_root` enables portable publication: `source_path`, `text_path`,
and `text_artifact_path` anywhere in the input are stored as project-relative
POSIX paths in inputs, exports, and lineage. Relative caller paths resolve
against this root. Absolute caller paths must be inside it. References that
escape the root, including through symlinks, fail publication or verification.
The version 3 manifest declares `reference_mode: project_relative` without
recording the host's project root. Inputs use fixed LF newlines, so identical
source bytes, input data, and implementation bytes produce the same snapshot
fingerprint after relocation. Copy the snapshot and its referenced source tree
with bytes preserved; reopen with the destination `source_root` without
republishing. Portable publication rejects extraction JSON that embeds an
absolute `source_path`. Create host-neutral derived extraction JSON with that
field omitted or set to a project-relative path, and declare its digest before
publication; the publisher never rewrites retained extraction bytes.
Without `source_root`, publication preserves the original absolute-reference
behavior and declares `reference_mode: absolute`; existing version 2 snapshots
remain readable.

Every declared extraction digest alias (`extracted_text_sha256`,
`text_artifact_sha256`, and `text_sha256`) must match the retained extraction
bytes. Contradictory declarations fail. Missing original extraction digests, or
`original_extraction_digest_unanchored: true`, remain explicit
`extracted_digest_unanchored` gaps and keep `text_verified` false, even when the
current cache bytes can be hashed.

Publication writes a temporary directory under the destination, writes the
manifest commit marker last, verifies the stage, and renames it atomically to
`snapshot-<SHA256>`. The fingerprint binds manifest metadata and all artifact
hashes. Identical input and implementation produce the same version. An existing
version is reused only after verification; it is never overwritten. Failed
staging is removed. Concurrent identical publication verifies the winner.
External filesystem permissions still control whether users can edit published
files; immutability is enforced by no-overwrite publication and detection on
reopen, not by changing file permissions.

Each export is available as JSONL, CSV, and a SQLite table:

| Table | Source |
|---|---|
| `financial_histories` | Financial history builder observations |
| `instrument_financial_histories` | Relationship builder financial observations |
| `entities`, `company_entities`, `instruments`, `role_edges`, `intersections` | Relationship builder |
| `review` | Both builders, with `review_origin` |
| `issuers`, `securities` | Universe builder |
| `filings` | Inventory selected filings |
| `sources` | Source-quality audit results |
| `documents` | Retained document receipts |

SQLite `row_json` preserves each complete nested row, IDs, monetary units,
currency, stock/flow distinctions, aggregate granularity, planned/completed
status, and date strings. Indexed issuer/date columns support convenient
queries. CSV nested cells contain JSON. Observations are never summed or
reclassified. All original inputs, including upstream reconciliation and
coverage details, remain in `inputs.json`.

```powershell
python scripts/query_reit_dataset.py <snapshot_dir> --issuer-cik 1063761
python scripts/query_reit_dataset.py <snapshot_dir> --table role_edges --evidence doc1
python scripts/query_reit_dataset.py <snapshot_dir> --date 2024-12-31 --export results.jsonl
python scripts/query_reit_dataset.py <snapshot_dir> --source-root <local_project_root>
```

The query command verifies the snapshot and retained sources on every open,
opens SQLite in read-only/query-only mode, allows only known table names, and
parameterizes CIK, evidence substring, and exact effective-date filters. Export
files must be new files outside the snapshot. No arbitrary SQL is accepted.
`scripts.query_reit_dataset.query_snapshot` exposes the same API to Python.

`verify_snapshot(snapshot_dir, source_root=None)` returns `valid`, `fingerprint`, and `errors`.
Portable verification defaults to the repository root containing the verifier;
the query CLI uses the same default and accepts `--source-root`. The Python query
API accepts `source_root` too. Absolute-mode verification uses the stored paths.
It verifies manifest identity, artifact inventory/hashes, input hashes, original
raw/extracted references, SQLite integrity, and table counts. A changed original
source or extraction invalidates the existing snapshot. `valid` is an artifact
integrity result: source authority, observation accuracy, historical coverage,
and public availability remain independent. `source_integrity_verified` reports
whether all retained raw references were readable and hash verified at publish.
`historical_ready`, `trading_ready`, and `pipeline_complete` remain false. Quality
review/PIT statuses are preserved without promotion; no trading or performance
claim is made.
