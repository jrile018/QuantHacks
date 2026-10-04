# Repository instructions for agents

Read [the team data guide](docs/team-data/README.md) and [the source contract](docs/team-data/source-contract.md) before adding a source.

- Use your own clean checkout and an exclusively owned `codex/source-<source-id>-<owner>` branch from current main. IDs use lowercase letters/numbers separated by hyphens. Each PR owns exactly one registered source.
- Register `configs/sources/<source-id>/{source.json,manifest.jsonl,README.md}`. Add only that source's adapter, matching tests, small synthetic examples and optional source documentation. Shared schema, pipeline, workflow and validator changes require a separate maintainer-reviewed PR.
- Reuse the implemented batch/transcript/evidence contracts. Preserve document identities, hashes, definitions, clock evidence and adapter versions. Keep unsupported identity/time/value fields unknown. A URL is metadata; the batch runner needs downloaded local bytes.
- Commit manifests, URLs, adapters, tests and synthetic examples. Originals belong in ignored `data/raw/team_sources/<source-id>/`; outputs belong in ignored `data/processed/team_sources/<source-id>/`. Full-data storage remains undecided.
- Run `python scripts/validate_team_sources.py --repo-root .`, the native smoke and relevant core/source tests. Before publishing, run `scripts/check_source_pr.py` against current main and HEAD as shown in the guide. CI must pass `source-configuration` and `Source adapter tests` on the exact PR head.
- The human authorizes teammate agents to merge passing **source-only** PRs. Follow the guide's scope check, exact-head checks and merge command; never bypass required checks, use admin merge, approve your own shared-schema change or force-push main. Shared changes remain maintainer-reviewed.
- Rebase only your exclusively owned branch. Capture its published remote SHA before rebasing and use the explicit lease shown in the guide. Shared branches merge main. Preserve others' work, stage explicit paths and resolve conflicts deliberately.
- Report base/head commits, commands/results, provenance, source coverage and unknown fields in the PR. A discovery registration does not claim extraction readiness. OCR success does not establish accepted benchmark features or financial/backtest readiness.

Existing Benchmark, industry and Post Benchmark owners retain their producer/consumer responsibilities. Consult published owner handoffs before changing shared components.
