# Portable frozen REIT history resume

`scripts/resume_reit_history_remote.py` prepares a separate derived run. Its default is offline preparation. `--execute` explicitly enables missing official metadata and historical document acquisition; `--resume` is required for an existing checkpoint. Preparation verifies and copies retained objects, so run it remotely for the actual large cache. No real acquisition has been performed as part of implementing this helper.

## Frozen cohort and inputs

The only approved cohort is 81 issuer CIKs in nine explicit groups: eight groups of ten and one group of one. The helper verifies both file SHA256s before loading the collection script or creating a broker:

| Input | Required SHA256 |
| --- | --- |
| `universe_current.json` | `078576300fc1ef4b3b94373bb30241d80aefc5c700dd64ef8bc164875e8513b1` |
| `history_batch_plan.json` | `862a3ba11251b8c98012635acd1e52f67b7ac6069a1510f91b13c529343b8dc3` |

The earlier 125 issuer `universe.json` cannot replace this universe. Dates are fixed at January 1, 2024 through October 3, 2026. The inventory retains opening context, including available 2022/2023 reports. Its existing opening rule selects the latest pre-2024 annual report, which can be older if newer context is absent. The helper records and fetches every referenced submissions metadata page before allowing history inventory to proceed. Missing issuer metadata, missing historical pages, malformed metadata and filing conflicts prevent history from starting.

The original metadata file and original broker snapshot are hashed into the checkpoint on preparation. Contact, rate, source roots, output root, task/exhibit bounds, frozen batches and implementation hashes are also immutable on resume. An optional `--metadata-sha256` verifies a previously recorded metadata hash on the first preparation.

## Copy and evidence rules

Provide both the original project root encoded in retained Windows paths and the remote project root holding their copied originals. Only `data/raw/reit_broker/` and `data/processed/reit_build/20261003/` paths can map. Outside roots, traversal, escaping symlinks and unknown path prefixes fail. Each official metadata source is checked against its SHA256 and its retained JSON payload; original metadata remains untouched. The sole permitted payload normalization is the top-level submissions CIK expressed as an integer versus its equivalent digit string, bound to the selected issuer and recorded in `source_json_normalizations`. Other JSON differences fail.

`--source-broker` names the parent of the copied `objects/` directory. `--source-database` can separately name the verified SQLite backup. The copied backup recorded for this continuation has SHA256 `4f9f24ebca2fd0d27542787265a9d83756c360c0c3857fa31f2e59560e1d04cc`. A database with pending WAL changes is rejected; take a SQLite backup rather than copying an active database alone.

Migration reads the original database without mutation, verifies every available cache candidate, copies verified bytes to the derived broker, and preserves the exact original cache receipt, receipt ID, source SHA256 and retrieval time. HTTP receipts retain their original identity; migration does not claim a fresh retrieval. Missing objects are excluded from the derived cache and listed as unavailable in `cache_migration.json`. Changed objects fail preparation. Existing acquisition blocks are preserved. The source cache and original receipts remain unchanged.

Earlier Windows queues are not migrated or rewritten. Each explicit group receives a new output under `history/batch-01/` through `history/batch-09/`, with new document, index and exhibit queues. URLs with verified cache objects reuse those bytes through the single derived broker. Resume verifies completed batch manifest hashes and retained raw/text hashes before skipping them.

Each completed batch also pins its collection manifest SHA256 and the completed URL/CIK/source SHA256 identity set. Removing or replacing collection records prevents resume from skipping the batch. Prepared resume requires the existing derived broker, retained cache/receipt identities and unchanged migration manifest. It does not rebuild a missing broker from an older source snapshot, which could discard later rate or HTTP block state. An interrupted preparation without complete recorded migration state requires a new empty output directory. Full history execution is deferred; this helper is prepared and reviewed offline.

## Preparation command

Run from the checkout containing this helper, using the remote Python environment. Supply the actual locations of the two frozen prepared JSON files. This example performs offline preparation only:

```sh
/home/john-riley/QuantHacks/.venv/bin/python scripts/resume_reit_history_remote.py \
  --old-project-root 'C:\Users\johnp\OneDrive\Documents\ChatGPT\QuantHaxs' \
  --new-project-root /tmp/quanthaxs-reit-20261003-v1 \
  --source-broker /tmp/quanthaxs-reit-20261003-v1/data/raw/reit_broker \
  --source-database /tmp/quanthaxs-reit-continuation-20261004/broker_cache_backup.sqlite \
  --metadata /tmp/quanthaxs-reit-20261003-v1/data/processed/reit_build/20261003/metadata.json \
  --universe /path/to/frozen/universe_current.json \
  --plan /path/to/frozen/history_batch_plan.json \
  --output /tmp/quanthaxs-reit-continuation-20261004/history-resume \
  --contact john.p.riley00@gmail.com --rate 2 --max-exhibits 10000
```

After reviewing preparation, execute with the identical arguments plus `--resume --execute`. Actual bulk preparation/collection belongs in a detached remote `tmux` session with a log. This implementation task does not launch that job.

`max_exhibits=10000` selects all relevant exhibits returned by the existing enumerator, which itself has a 10,000 exhibit bound per filing index. A smaller explicit cap records each omitted enumerated exhibit in the batch manifest. The checkpoint reports the enumerator bound and omission counts. Task bounds can leave a batch partial; resume continues that batch before later groups. Neither a completed selected queue nor successful extraction asserts exhaustive history, historical membership, undisclosed transfers, complete loan lineage, financial readiness or backtest readiness. `history_complete` remains false.

## Artifacts and verification

The derived output contains `checkpoint.json`, `cache_migration.json`, `metadata_status.json`, derived `metadata.json`, `metadata_inventory_preflight.json`, per-group queue/collection artifacts and `run_summary.json`. Originals are inputs only. The checkpoint distinguishes completed selected batches from full historical coverage.

Focused offline tests use tiny synthetic broker objects and official metadata arrays:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_reit_history_remote.py -v
.venv/Scripts/python.exe scripts/resume_reit_history_remote.py --help
```

Tests cover path escapes, changed and missing bytes, frozen 81 issuer selection, explicit groups, original receipt/database preservation, immutable resume settings, untouched prior queues, metadata fetch-before-history, completed batch skipping, separate backup locations and inherited HTTP blocks. Synthetic transports make no external requests.
