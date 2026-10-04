# Publish the teammate starter baseline

Release scope: same-repository source branches, manifests/URLs first and source adapters/tests using the shared intake contracts. Agents may merge passing source-only PRs after the exact-head CI gates; shared changes require maintainer review. Use the release PR and live main commit/checks as publication evidence.

## Why the release needs an explicit file list

The shared checkout contains active Benchmark, industry, Post Benchmark and Lattice work. Large areas of implementation are untracked, artifacts/ contains generated datasets, and stat-arb/ is a separate Git repository. Pushing that checkout wholesale or staging the whole folder would mix unrelated work. A clean, isolated `codex/team-source-checks` release branch has been prepared from the latest fetched main; its base commit must be recorded in full before publication.

Use [release-allowlist.txt](release-allowlist.txt) as the candidate starter closure. It includes the actual runnable document modules, focused tests, synthetic examples and self-contained starter documentation. Existing coordination/research guides remain with their separately published workstreams; this starter does not pull their recursive documentation dependencies onto main. Review owner changes before copying them. A listed file is a publication candidate, not proof of consumer acceptance.

## Release procedure

1. Confirm the isolated `codex/team-source-checks` publishing checkout is based on the latest fetched main and record its full base commit. Preserve the dirty shared checkout; do not move unrelated files into the release branch.
2. Freeze an owner-reviewed snapshot of the allowlisted files and record their hashes. Copy only that snapshot into the publishing checkout. Confirm that tracked OCR edits are the intended owner version. Do not copy credentials, full configs, caches or result folders.
3. Confirm every allowlisted path exists in that checkout. Include both source templates, the source configuration validator and CLI, the source-only Git diff gate and CLI, their focused tests, the two source CI workflows, the source PR template, the root README's onboarding section, and the small synthetic fixture. The code needed to run documented commands must be in this branch; documents pointing at another worktree do not publish that worktree's implementation. Include source URL inventories only after their owner supplies exact paths and status; root source registries remain a separate producer-owned addition.
4. Run the root README native smoke and the documented focused core, source-validation and policy tests from that checkout. Run `test_document_ocr` only with its `requirements-ocr.txt` dependency closure. Record the exact commands, exit codes and any optional PDFium skips. Check staged content, imports, relative links, file sizes and excluded paths. A local pass does not establish that required GitHub checks have run.
5. Review the trusted `source-configuration` workflow and untrusted `Source adapter tests` workflow as part of the starter PR. The trusted check must evaluate the exact candidate head with base-branch code before any candidate adapter runs; the adapter check runs without write credentials or secrets. Both checks must report success on the same exact head before a later source-only PR can use agent merge authority.
6. Push this scoped branch and open a starter PR against main for maintainer review. Its description must list the base commit, frozen paths/hashes, tests, exclusions and available capabilities. Attach the created PR to the Codex chat when tooling is available. Follow [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow).
7. After maintainer acceptance/merge, check a fresh clone of main with the same smoke and tests. Record the actual merge commit in this guide and announce that specific baseline. Only then tell teammates to sync and run its pipeline.

## Intentional exclusions and optional follow-ups

Keep data/raw/, data/processed/, .massive_cache/, artifacts/ result matrices/database/tar payloads, environments, credentials, model weights, machine-specific config and stat-arb/ out of this PR. Full-data storage is deferred. This is an OCR/source-intake baseline, not publication of every research worktree.

The local batch engine needs no training/HPC helpers for native text. The existing tests/test_document_batch.py also tests GPU/export/LoRA helpers. Publishing that entire test module requires scripts/export_ocr_training_pairs.py, hpc/submit_document_job.py, hpc/prepare_lora_config.py, hpc/document_lora.sbatch and src/glm_document_ocr.py, plus their reviewed closure. Keep that expanded optional gate together in a later scoped addition, rather than leaving a test with missing imports on main.

GLM can be added as a reviewed optional package using src/glm_document_ocr.py and requirements-gpu-ocr.txt, with pinned model instructions. Adding those files does not install model weights or launch jobs. Canonical financial/FeaturePanel/evaluation implementation from other managed worktrees requires its existing owner/consumer handoff and a separate merge.

## Completion evidence

Record the starter PR URL, actual merge commit, required-check conclusions on the exact head, clean-clone smoke command/exit and focused test results here when they exist. Until then this is a prepared candidate, and teammates can contribute discovery manifests while awaiting the merged implementation. Source registration metadata is a companion intake contract, not a canonical financial schema or evidence of consumer acceptance.
