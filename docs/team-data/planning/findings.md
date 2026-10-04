# Onboarding findings

## Repository evidence

Origin: https://github.com/jrile018/QuantHacks.git. Current shared checkout: codex/options-export. Local origin/HEAD points to main. Cached refs observed: HEAD 3f76ce2, origin/main dc35076. No fetch was performed by the inventory agents; these are not current-server claims.

Much of the implemented document/industry pipeline is currently untracked here. Merely pushing this guide would not publish its dependencies. The starter package must include the actual batch/transcript/manifest modules, focused tests, contract docs and offline example.

data/raw/, data/processed/, .massive_cache/ and environments are ignored. artifacts/ contains large generated CSV/database/JSON/tar outputs and is not generally ignored. stat-arb/ has its own .git directory and is not a registered submodule. Never stage the whole checkout.

## Implemented contracts

- Generic batch: JSONL, unique nonempty document_id and source_path; optional source_sha256 verifies actual bytes. Relative paths resolve from the manifest directory. URLs require a separate acquisition step. CLI: scripts/run_document_batch.py --manifest PATH --output-dir DIR --engine native.
- Native TXT/HTML extraction is Python standard library only. A tiny synthetic TXT manifest exercises the actual pipeline without credentials, data downloads or OCR dependencies.
- Batch revision document_batch_v2; transcript revision document_transcript_v2; normalization document_text_v1. Hash-bound resume checks source, config and outputs.
- The richer SEC inventory contract has issuer/accession/publication/identity fields. It is not a universal schema for arbitrary providers. General sources must not fabricate SEC identifiers.
- Transcript/evidence contracts preserve source/text hashes, exact normalized text offsets, adapter/engine provenance, pages/tables and quality flags. Successful extraction does not establish historical trading readiness.

## Workstream boundaries

Benchmark produces financial/public-context facts. Industry (the nearest documented handoff for Benchmark pt. 2 industry spec) owns REIT acquisition/history/source quality. Post Benchmark owns canonical research/evaluation integration in its managed worktree. Coordination records contracts and receipts. Their handoffs are pointers to owner evidence, not proof that all feature/evaluation code is available in this Git checkout or on main.

## Sources read

- Existing docs/coordination/handoffs/, docs/8k-document-analysis.md, document design spec and relevant implemented Python modules.
- Public requested skill: https://github.com/lrstanley/skills/blob/master/grill-me/SKILL.md (read, not installed). It asks one recommended question at a time and resolves repository facts through inspection.
- Git procedures checked against https://git-scm.com/docs/git-rebase, https://git-scm.com/docs/git-push and https://docs.github.com/en/get-started/using-github/github-flow.

## Review interview: latest human decisions (2026-10-04)

The existing post-release wording-first equity objective remains settled. The human now delegates selection of one feasible existing event family, wording signal and holding period to Post Benchmark; Post must freeze the recipe before scoring and explain it in the report. The first account starts with hypothetical USD1,000,000.

The initial long-only answer was explicitly superseded: equity longs AND shorts are permitted. The updated sizing answer is up to 100% gross exposure, equally sized eligible positions. Gross means absolute long plus short notional divided by current account equity, not net exposure. Preserve the no-leverage constraint; share borrowing for short sales still requires evidenced availability, fees and collateral. Restricted short-sale proceeds are not an extra investment budget.

Direct human clarification: no passive background revenue to improve Sharpe. Idle cash yield is zero; no unrelated investments, lending income or other outside yield. Show trading P&L after costs and dividend/corporate-action attribution separately; mandatory short dividend/borrow/collateral expenses must not disappear. Match baseline capital, eligibility, exposure and costs. Define the reported Sharpe reference explicitly; zero-variance cash Sharpe is undefined. No strategy results or numerical optimality have been established.

The earlier sizing question (10% per issuer/50% total proposed) was rejected. Both the earlier and updated answers selected full unlevered budget/equal positions. These are simulated research permissions, not live capital authority or a new usefulness/drawdown promotion threshold.
