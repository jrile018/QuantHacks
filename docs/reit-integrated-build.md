# Offline integrated REIT build

## Latest retained continuation checkpoint

The original commands and source contracts below remain the technical build guide. The later [history preparation summary](../data/processed/reit_build/20261004-continuation/history-prepare-results/run_summary.json), [cache migration](../data/processed/reit_build/20261004-continuation/history-prepare-results/cache_migration.json), [metadata status](../data/processed/reit_build/20261004-continuation/history-prepare-results/metadata_status.json), [exit receipt](../data/processed/reit_build/20261004-continuation/history-prepare-results/exit-status.txt) and [test log](../data/processed/reit_build/20261004-continuation/history-prepare-results/tests.log) document a successful **offline preparation only** run: 363 tests passed, 115 code pins matched, and zero HTTP requests were made. It planned 81 issuers in nine groups. The migration verified 557 cached URL entries and recorded 43 unavailable entries individually; all 81 main submission metadata files are verified, while 49 referenced historical pages across 48 CIKs remain pending. No historical batch was executed; `history_complete` is false and the source broker database was unchanged. These prepared results do not change the publication, source-quality, or point-in-time gates below.

The [disk recovery receipt](../data/processed/reit_build/20261004-continuation/disk_recovery.json) records removal of a verified generated intermediate duplicate to recover local space. The prepared inputs have an unchanged remote restore copy at `home-pc:/tmp/quanthaxs-reit-20261003-v1/data/processed/reit_build/20261003/integrated/prepared/prepared_inputs.json` (SHA-256 `df099952f7520ef33c23a7b8eb46db2f99542cd75252f79f407042667d1eb08e`). Restore and verify that generated file before using a local publish-only path if it is absent; immutable snapshots and raw sources were not removed by that recovery.

`scripts/build_reit_snapshot.py` integrates the retained sources into the
immutable `src/reit_dataset.py` publisher. It makes no acquisition requests,
calls no models, and performs no OCR. CPU intensive preparation belongs on
`home-pc` in a detached tmux job. Small tests use the standard library:

```powershell
python -m unittest tests.test_reit_snapshot_runner -v
```

Inputs are project relative. Defaults are:

| Input | Purpose |
| --- | --- |
| `data/processed/reit_build/20261003/discovery_candidates.json` | Discovery assertions, including unresolved candidates |
| `data/processed/reit_build/20261003/collection/manifest.json` | Retained annual documents and collected history documents |
| `data/processed/reit_build/20261003/batches/*/batch_manifest.json` | Explicit historical batch coverage and omissions |
| `data/processed/reit_build/20261003/relationship_seed_assertions.json` | Original relationship assertions and review items |
| `data/processed/reit_financials/20261003-meaning-pilot` | Frozen four issuer analysis and original collection |
| `data/processed/reit_filing_pilot/realty_income_2025_meaning_v2` | Retained Realty Income PDF sample and frozen analysis |

The two retained pilots reuse their hash verified analysis outputs. Their original
collection manifest hashes, output hashes, analyzer revision, implementation hash,
and extraction hashes remain in provenance. With the default
`--financial-scope history_batches`, fresh financial parsing targets completed
historical batch documents and exhibits. Annual reports acquired solely for
discovery validation still receive quality and eligibility checks; their skipped
financial parsing appears explicitly in coverage. Completed URLs come from batch
manifest fields or read only completed task results with retained queue hashes.
`--financial-scope all` explicitly expands fresh financial parsing to every
retained document. Originals are never rewritten.
Missing or changed source bytes, extraction bindings, and declared analysis hashes
stop the build.

Distinct retained representations of the same filing remain separate documents.
A narrow comparison permits different hashes only for the exact same official SEC
archive URL, when removing one empty final `type="text/javascript"` tag whose `src`
matches the observed root relative pattern of six to twelve alphanumeric path
segments yields identical remaining bytes. External hosts, ordinary asset paths,
query strings, encoded slashes, and protocol relative paths do not qualify. This is
an inference about the observed SEC wrapper pattern, not general rendered
equivalence. Both raw hashes,
extraction chains, and the comparison evidence remain in provenance. The analysis
bound representation supplies existing financial observations; the auxiliary
representation is audited without duplicate financial parsing. Substantive content
conflicts quarantine both versions for financial and eligibility use and create
review items. Financial meaning metadata differences also remain review items.

Preparation recomputes annual HTML filing eligibility with the current discovery
implementation. It does not import `universe.json` or `universe_evidence.json`.
Complete qualification context and cover table evidence determine current candidate
eligibility. An older annual claim ends at the next retained annual report date;
this prevents older positive language from masking newer conditional language.
These intervals are observed filing context, without proven continuous membership.
PDF samples do not become HTML cover table proof.

Quality axes are audited independently, reading one raw document at a time to
bound memory. Native agreement passages additionally enter relationship review as
candidates; they do not become adjudicated role edges. The financial
history builder checks exact raw bytes, native quotes, locators, issuer context,
financial meaning, and recorded availability. Relationship assertions undergo
whitespace normalization against exact native spans; original and normalized
evidence both remain in provenance. Unknown party identifiers and candidate roles
remain review items. Seed availability cannot precede a later retained source
acceptance timestamp; a seed clock with no retained source clock becomes unknown.

## Remote preparation and local publication

Copy the project code and the input `data/` subtrees, including the broker's
`data/raw/reit_broker/objects` metadata sources, into the remote project directory.
Use the passwordless `home-pc` alias and detached tmux. A preparation command is:

```bash
python scripts/build_reit_snapshot.py \
  --project-root /tmp/quanthaxs-reit-20261003-v1 \
  --build-root data/processed/reit_build/20261003 \
  --prepare-inputs \
  --as-of 2026-10-04T03:00:00+00:00
```

Choose the actual aware knowledge cutoff for the run; candidate proof retrieved
later than that cutoff will remain unverified at the cutoff. The command writes
`integrated/prepared/prepared_inputs.json`, `coverage.json`, and content addressed
native extraction copies under the build root. Original extraction JSON has its
host specific `source_path` removed in a derived copy. Its original byte hash and
the derived byte hash are both retained. Raw SHA256, URL, and accession bindings
remain exact. The publisher can therefore verify derived JSON on either host.
Legacy caches without a preexisting declared extraction digest have an explicit
`original_extraction_digest_unanchored` gap. Computing a new derivative hash does
not establish independent integrity or fidelity of those original native pages.

`universe_current.json` contains freshly validated current claims with source
evidence and half open intervals. `history_batch_plan.json` lists every validated
issuer CIK exactly once in sorted batches of at most ten. Unresolved candidates,
evidence errors, quarantined sources, and incomplete historical scope remain in
coverage. Generating this plan starts no acquisition jobs.

Copy the entire `integrated/prepared/` directory back into the same project
relative location. Publish locally without repeating financial preparation:

```powershell
python scripts/build_reit_snapshot.py --publish-only data/processed/reit_build/20261003/integrated/prepared/prepared_inputs.json
```

Publication rechecks the original input artifacts and all publisher source
references. It writes under `integrated/snapshots/snapshot-<fingerprint>/`.
An existing snapshot is verified and reused; immutable exports are not overwritten.
The runner supplies the project source root to the publisher. Snapshot source
references are project relative, preserving identity when the corpus moves between
hosts. Pass the destination project root as `source_root` when verifying with the
Python API, or `--source-root` with the query CLI. Verification requires the retained
raw and extraction corpus; copying export files alone does not supply missing
evidence.

The optional repeatable `--retained-root` flag replaces the default pilot list.
`--output-root` changes the project relative build output. Omitting
`--prepare-inputs` performs preparation followed by publication in one command.
`--max-candidates` controls the review candidate limit per newly analyzed document.

## Dependencies and limits

The runner and retained source integration need Python 3.10 or later and standard
library imports. Cached PDF text is mandatory; no native PDF library is imported
by the runner or financial builders. Acquisition or extraction of new PDF text is
a separate collector responsibility, using its existing native PDF prerequisites.
The Realty Income collection is a sample of retained native PDF pages, not a full
report extraction or an OCR fidelity audit.

The exported source, issuer, security, financial history, entity, instrument,
role edge, intersection, and review tables remain observations within retained
scope. Source quality coverage, batch limits, parsing omissions, normalization
changes, and incomplete universe coverage remain in prepared provenance and the
publisher's upstream coverage gaps. Separate company entity export depends on the
publisher's `company_entities` table support.

Collection completeness, historical universe completeness, point in time readiness,
and trading readiness are all false. Retrieval timestamps are never converted to
first publication timestamps. SEC acceptance fields describe recorded filing
availability; they do not prove exact first public availability or executable
trading time. Financial observations remain nonadditive; facilities, authorization,
debt principal, agent roles, and planned use of proceeds do not become realized
cash transfers or a verified lending network.

## Implementation and verification

The assigned implementation is confined to the runner, this guide, and
`tests/test_reit_snapshot_runner.py`. Fixture checks cover source relocation,
publication verification, conditional REIT claims, preservation of original
extractions and reused analysis, corrupted raw sources, moving prepared inputs
between project roots, supersession of older annual claims, script-only source
variants, retained duplicate chains, and substantive source conflicts.
