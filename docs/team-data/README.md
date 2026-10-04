# Add a source to QuantHacks

Teammates use branches in the same [QuantHacks repository](https://github.com/jrile018/QuantHacks). Commit manifests, URLs, source adapters, tests and synthetic examples. Download originals and write results locally; full-data storage remains undecided.

Read [AGENTS.md](../../AGENTS.md) and [the source contract](source-contract.md). The human authorizes teammate agents to merge passing source-only PRs using the checks below. Shared schema, pipeline and workflow changes go in a separate maintainer-reviewed PR.

## Task prompt for a teammate agent

~~~text
Read AGENTS.md, docs/team-data/README.md and source-contract.md. Add my source on an exclusive codex/source-<source-id>-<owner> branch from current main. Register source.json, manifest.jsonl and acquisition README. Reuse existing document schemas; keep unsupported clocks/identities unknown. Commit URLs first, originals/results only in ignored local folders. Add source-specific adapters with matching tests and small synthetic fixtures as needed. Run the configuration validator, smoke, relevant tests and source-only Git diff gate. Rebase/sync safely, open the source PR with provenance/results, verify both required CI checks on its exact head, and merge using --match-head-commit. Keep shared changes in a separate maintainer-reviewed PR. Report the merged commit and remaining data/OCR readiness limitations.
~~~

## 1. Start from current main

Use your own clean clone.

~~~powershell
git clone https://github.com/jrile018/QuantHacks.git
cd QuantHacks
git fetch origin
git switch main
git pull --ff-only origin main
git rev-parse HEAD
git status --short
$sourceId = "county-records"
$ownerId = "alex"
$branch = "codex/source-$sourceId-$ownerId"
git switch -c $branch origin/main
~~~

Replace the two example IDs. Each is lowercase letters/numbers separated by hyphens. One source and one owner per branch. Verify that the batch runner, source validator, source PR gate and templates exist; if the baseline is missing, report it and continue discovery rather than inventing a pipeline.

Python 3.10+ is required. A virtual environment is optional for the native TXT smoke, which needs only the standard library.

~~~powershell
python scripts/run_document_batch.py --manifest examples/team_data/manifest.jsonl --output-dir data/processed/team_sources/onboarding-smoke --engine native
~~~

Verify one completed document, zero failures and transcript hashes in the output journal. Repeating the same command should skip the verified checkpoint. This checks native text intake, not scanned-page recognition.

## 2. Register your source before bulk work

Create `configs/sources/<source-id>/` containing:

| File | Required content |
| --- | --- |
| source.json | Copy [source.template.json](../../templates/team-data/source.template.json); replace placeholders. Use schema_version 1.0, the folder's source_id, nonempty owner, stage discovery or extracted, and engine native, tesseract or glm. |
| manifest.jsonl | Copy [manifest.template.jsonl](../../templates/team-data/manifest.template.jsonl). Every row has a unique source-ID-prefixed document_id, canonical HTTP(S) source_url and a local relative source_path. |
| README.md | Publisher, owner, URLs/coverage, download/API commands, credential environment-variable names, usage restrictions, publication/identity evidence and unknown fields. |

Use document IDs such as `county-records:original-identifier-v1`; a ticker alone is insufficient. Paths from this manifest begin `../../../data/raw/team_sources/<source-id>/`. Optional source_sha256 is the real lowercase SHA-256 of downloaded bytes; never invent hashes or clocks. Known fields ending in `_at_utc` must be aware UTC ISO timestamps, or null when unknown. URLs must not contain embedded credentials.

Stage `discovery` allows absent local originals and registers how to acquire them. It does not claim a runnable manifest. Set `extracted` only after a documented local pilot succeeds and add the synthetic fixture below. The source.json engine describes the intended extraction configuration; pass matching flags explicitly to the batch command. GLM additionally requires a pinned model_revision and a repo-relative model_cache under ignored `data/raw/team_sources/<source-id>/`; GPU code/dependencies must be available in the separately reviewed optional package before use.

~~~powershell
python scripts/validate_team_sources.py --repo-root . --source-dir "configs/sources/$sourceId"
~~~

The validator prints JSON and exits zero only when configuration is valid. It checks all registered sources even with --source-dir so duplicate identities cannot hide elsewhere. It checks metadata, real URLs, namespaces, paths, hashes when supplied, UTC fields and unresolved placeholders. It never fetches URLs or requires ignored originals in CI.

## 3. Extract a local pilot and reuse the schema

Download originals into `data/raw/team_sources/<source-id>/`. Record hashes, source versions and acquisition receipts. Results stay in `data/processed/team_sources/<source-id>/`.

~~~powershell
python scripts/run_document_batch.py --manifest "configs/sources/$sourceId/manifest.jsonl" --output-dir "data/processed/team_sources/$sourceId/native-pilot" --engine native
~~~

TXT/HTML use native extraction. PDF/image OCR requires `requirements-ocr.txt` and a separately installed Tesseract executable. Use --engine tesseract; add --force-ocr to recognize all PDF pages. Actual OCR/backend readiness requires that local pilot and its recorded engine/version evidence; offline configuration checks cannot prove recognition quality or model availability.

Source adapters use `src/<source_id_with_underscores>_adapter.py` and matching `tests/test_<source_id_with_underscores>_adapter.py`. Preserve the common transcript/evidence schema and source fields. Optional source documentation is `docs/sources/<source-id>.md`. Shared contract changes require a separate PR.

For stage extracted, commit a small **synthetic** UTF-8 TXT/HTML fixture under `examples/team_sources/<source-id>/` and its own manifest.jsonl. Fixture IDs must also be unique; use a synthetic suffix. This recipe creates an example and hashes its actual bytes:

~~~powershell
@'
import hashlib, json, sys
from pathlib import Path
source_id = sys.argv[1]
folder = Path("examples/team_sources") / source_id
folder.mkdir(parents=True, exist_ok=True)
content = b"Synthetic source fixture. No financial facts.\n"
(folder / "sample.txt").write_bytes(content)
record = {"document_id": source_id + ":synthetic-v1", "source_path": "sample.txt",
          "source_sha256": hashlib.sha256(content).hexdigest()}
(folder / "manifest.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
'@ | python - "$sourceId"
~~~

Git preserves these fixture files with LF line endings on every platform so committed hashes remain stable. Hash actual UTF-8 bytes after edits.

The trusted validator extracts each fixture using the existing native pipeline, verifies transcript hashes and exact evidence slices, and rejects empty text, missing bytes or hash mismatches. Fixtures have a 256000-byte per-file limit. Keep fixtures synthetic and distinct from original-data rows.

## 4. Validate and commit explicit paths

~~~powershell
python scripts/validate_team_sources.py --repo-root .
python -m unittest tests.test_source_validation tests.test_source_pr_policy tests.test_shared_review tests.test_document_manifest tests.test_document_transcript tests.test_document_evidence tests.test_document_language tests.test_document_report tests.test_analyze_8k_documents
~~~

Run your own source adapter tests too. Expanded OCR/GPU tests need their documented optional dependencies. CI runs the published offline suite and native smoke; report the exact local checks instead of claiming a full suite from this focused command.

~~~powershell
git status --short
git add -- "configs/sources/$sourceId/source.json" "configs/sources/$sourceId/manifest.jsonl" "configs/sources/$sourceId/README.md"
git diff --cached --stat
git diff --cached
git commit -m "Add $sourceId source registration and acquisition guide"
~~~

Stage adapter/test/fixture paths explicitly in separate commands when present. Never blanket-stage the shared workspace, raw/processed data, artifacts, caches, weights, credentials or the independent stat-arb repository.

## 5. Sync safely and check the PR scope

Commit your changes and ensure your checkout is clean. If unrelated work remains, preserve it and use a clean checkout.

~~~powershell
git fetch origin
git branch --show-current
git status --short
~~~

On an **already-published exclusive branch**, capture its remote SHA **before** rebasing:

~~~powershell
$remoteBeforeRebase = git rev-parse "refs/remotes/origin/$branch"
~~~

Then rebase and retest:

~~~powershell
git rebase origin/main
python scripts/validate_team_sources.py --repo-root .
python scripts/check_source_pr.py --repo-root . --base origin/main --head HEAD --branch $branch
~~~

Rerun the smoke and source tests. The PR gate permits exactly one registered source's configuration, adapter and matching tests, synthetic TXT/HTML examples and optional source doc. It rejects shared changes, unsafe paths, symlinks, missing required source files, multiple sources and oversized files. Each file is at most 5 MiB; example files are also restricted by the fixture validator's smaller limit.

Resolve source conflicts by preserving genuine versions and deliberately fixing their mapping. Shared-schema conflicts need the affected owner and separate contract PR. Stage only resolved files and use git rebase --continue; git rebase --abort retains the original branch. Never select ours/theirs wholesale.

First push:

~~~powershell
git push -u origin $branch
~~~

Updating a previously published exclusive branch after the rebase:

~~~powershell
git push "--force-with-lease=refs/heads/${branch}:$remoteBeforeRebase" origin "HEAD:refs/heads/$branch"
~~~

A failed lease means someone changed the branch: fetch and reconcile; do not overwrite the expectation to force the push. Shared branches use git merge origin/main, retest, and normal push; never force-push main or shared branches. See [Git rebase](https://git-scm.com/docs/git-rebase) and [Git push](https://git-scm.com/docs/git-push).

## Research readiness

Keep these claims separate in each source PR: discovery records acquisition instructions and URLs; extracted records a successful local pilot and reproducible intake checks; consumer accepted requires the owning producer/consumer's receipt. Passing source CI does not establish alpha or production readiness.

For the first research pilot, use the smallest source subset supporting one predeclared, falsifiable mechanism, a matched simple baseline and feasible costs. Preserve negative and missing-data results. Record stop, expand or inconclusive decisions through the research owners; source registration does not freeze a trading policy. Bulk acquisition, GPU/model training, additional sources and shared feature/evaluator expansion can wait for that separate acceptance decision.

## 6. Merge only the verified source PR

Use [the source PR template](../../.github/PULL_REQUEST_TEMPLATE/data-source.md), including base/head commits, provenance, pilot results and unknown fields. Both required GitHub checks must pass:

| Required check | What it proves |
| --- | --- |
| source-configuration | Trusted code from the base checks candidate registration, synthetic extraction/evidence and the source-only diff; publishes a status on the exact head SHA. Candidate adapters are never executed in this job. |
| Source adapter tests | Candidate tests/adapters run without write credentials or secrets, alongside the published offline suite and native smoke. |

Recheck the scope against current main, then use GitHub CLI from the source branch:

~~~powershell
$pr = gh pr view --json number --jq .number
$head = git rev-parse HEAD
$remoteHead = gh pr view $pr --json headRefOid --jq .headRefOid
if ($head -ne $remoteHead) { throw "PR head changed; fetch, reconcile and rerun validation." }
gh pr checks $pr --required
if ($LASTEXITCODE -ne 0) { throw "Required checks must pass before merging." }
gh pr merge $pr --squash --auto --match-head-commit $head
~~~

Only use this command after both required checks pass and the source-only gate says eligible. --match-head-commit prevents merging a different PR version; --auto lets GitHub wait for any remaining branch requirements. Main requires up-to-date passing checks. Never add --admin or bypass failures. If main moves, sync and rerun checks as needed. A shared/schema PR belongs to maintainer review even when its tests pass.

Non-source PRs require the repository owner's GitHub approval of the exact head commit before the trusted check can pass. GitHub disallows self-reviews, so for a PR they authored the owner can post the exact comment `approve-shared-change: FULL_HEAD_SHA` instead. After reviewing or posting that explicit approval, the owner applies or reapplies a label such as run-source-checks to trigger the check again. After requesting changes, the owner also reapplies the label to rerun the gate; a later changes-requested review then rejects earlier approval; pushing a new head requires a new approval. Teammate agents must not issue this shared-change approval on the owner's behalf without explicit human authorization. This keeps shared/schema updates reviewable without granting source-only merge authorization to another branch name.

After merge:

~~~powershell
git switch main
git pull --ff-only origin main
git rev-parse HEAD
~~~

Start each new contribution from updated main. Existing unmerged branches sync using the same procedure. This brings shared code and everyone else's manifests into each clone while keeping local data separate.

Benchmark owns financial producer contracts; industry owns industry/history evidence; Post Benchmark owns canonical integration and consumer acceptance. Unknown usable clocks stay unknown; OCR success does not establish source acceptance, financial feature correctness or backtest readiness. Owner coordination guides, when published by that workstream, are docs/coordination/architecture-contract.md and docs/coordination/feature-matrix-integration.md.
