# Source onboarding scope and handoff

Owner: Organize Benchmark Data Push. Date: 2026-10-04. This packet is saved for the coordinator and producer/consumer owners to read; no cross-chat message or merge is implied.

## Agreed human scope

Same QuantHacks repository, separate source branches. Commit manifests/URLs first; defer full-data storage. Allow source-specific adapters/tests. Propose shared-schema changes separately for maintainer review. The human has authorized agents to merge passing source-only PRs after `source-configuration` and `Source adapter tests` both pass on the exact PR head. Shared changes and the starter release PR remain maintainer-reviewed.

## Starter release candidate

The publication allowlist covers the onboarding instructions, companion source and manifest templates, small synthetic fixture, source configuration validator and source-only diff gate with focused tests, both source CI workflows, the source PR template, and the root README onboarding section. A clean, isolated `codex/team-source-checks` publishing branch was prepared from the latest fetched main. Its exact base SHA and final frozen paths still need recording before publication. Existing owner code, tests, datasets and coordination files remain under their respective owners.

## Contracts reused and companion fields

The guide reuses run_document_batch's local-file JSONL envelope, the implemented transcript/evidence contracts and the SEC-specific inventory when appropriate. `source.json` is companion registration metadata; `source_url` in the source template is input metadata already retained by the batch journal. Neither is a new verified clock or canonical financial feature field. Source READMEs carry discovery/acquisition/coverage status without introducing a competing market schema.

Benchmark retains financial producer contracts in its point-in-time-feature-matrix checkout; industry retains original/history evidence and quarantine; Post Benchmark retains canonical decisions, FeaturePanel/registry/evaluator and consumer acceptance. Unknown usable clocks remain unknown. Inspected 2024/2025 data remains development data. OCR success alone cannot clear source quarantine.

## Starter publication and actions

The exact candidate closure is release-allowlist.txt. Exclude raw/processed datasets, artifacts/ bulk payloads, caches, weights, credentials, machine config and the nested stat-arb repository. Optional GPU/export/training test closure is explicitly separate.

Publisher action: owner-review and freeze the candidate code/doc versions in the isolated branch, confirm the validator/template/workflow/root README closure, publish a scoped starter PR for maintainer review, run the clean-checkout commands, and record the actual merged baseline. Later source-only PRs require the trusted `source-configuration` and untrusted `Source adapter tests` checks to pass on the same exact head before an agent merge; shared changes require a separate maintainer-reviewed PR. No owner is asked to change their producer/consumer contract for this documentation. Review identified a generic batch saved-OCR-JSON hash mismatch; that route is excluded from advertised starter capabilities. The OCR owner should assess it in a separate implementation/test change before claiming support. A teammate's later source adapter reaching a shared boundary needs an affected-owner contract proposal and consumer acceptance; direct transcript or matrix presence is insufficient.

## Current evidence

Publication verified: PR #4 merged at main fa30fcb955d5ac984f360db6456d4edc8c39a312. PR and main checks passed; strict required checks and auto-merge were enabled and read back. This local update is a coordination receipt; the GitHub release snapshot predates this completion note. Smoke/review receipts are recorded in planning/progress.md when available. This packet separates local guide readiness from merged availability.
