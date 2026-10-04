# Team source validation and merging plan

Date: 2026-10-04. Continue one planning-with-files workflow in this owner-specific directory.

## Accepted decisions

Same QuantHacks repository and source branches; manifests/URLs first with full-data storage deferred; source adapters/tests allowed, shared-schema changes in separate PRs. The human authorizes merging passing source-only PRs and requested configuration tests and README instructions.

## Completed endpoint

1. Offline metadata/manifest/fixture validator and meaningful negative tests implemented.
2. Source-only Git diff/branch gate and exact-head shared-owner approval gate implemented and reviewed.
3. README, AGENTS, source contract, templates, agent prompt, safe sync/merge instructions and two CI workflows published. Fixture LF rules preserve cross-platform hashes.
4. Explicit 43-path closure staged as 41 changed paths in a clean publishing checkout; 108 tests passed remotely under shared flock, two threads/4 GiB, plus native smoke and resume. No raw/results/weights/cache/nested repository staged.
5. [PR #4](https://github.com/jrile018/QuantHacks/pull/4) merged at main fa30fcb955d5ac984f360db6456d4edc8c39a312. PR CI and both main workflows passed. Main protection readback requires up-to-date source-configuration and Source adapter tests from GitHub Actions app15368, including administrators; force-pushes disabled. Auto-merge enabled.

## Boundaries and remaining work

Original dirty shared checkout and owner workstreams preserved. Publication README started from current main plus only this lane's section. This is a source-intake baseline; actual source acquisition, OCR recognition, consumer acceptance and alpha results are outside its completed claim.

Local C: disk-full error112 interrupted work. Only this chat's old test exports were removed; receipts retained. Later ~194MB reserve allowed bounded files, while the full suite stayed remote. This lane's completed tmux session was cleaned; other remote jobs untouched.

The new wording-only-first planning request is recorded in pilot-handoff.md without new publication, acquisition, engine or financial-feature implementation. Canonical Post Benchmark owns acceptance and the account replay. Existing bounded commitments precede optional expansion.

## Project-wide review requested 2026-10-04

Continue this existing owner-specific planning workflow. The completed source-intake release above remains complete. This review refers to the coordinator decision register and Post Benchmark's canonical plan; it does not replace either owner's plan.

1. Restore current plans, live chat inventory and human choices; distinguish older broad scope from the wording-first priority. DONE.
2. Independently review canonical acceptance, producer/industry packets, and numerical/inference/hardware receipts. IN PROGRESS; three read-only helpers, no new jobs.
3. Reconcile local implementation, delivered packets, accepted consumer results and merged GitHub state; identify concrete missing gates. IN PROGRESS.
4. Grill only unsettled decisions, preserving existing answers. Human settled: Post chooses/freezes the feasible recipe; equity longs and shorts, equal positions, maximum100% gross exposure with no leverage; idle cash/outside yield0%. Financial/market qualification and short accounting remain canonical gates.
5. Save one bounded audit and ordered owner actions, then deliver a scoped handoff through the existing coordinator where human authorization supports it. PENDING.

Sources: docs/coordination/first-pilot-decision-register.md; docs/coordination/architecture-contract.md; docs/research/2026-10-04-alpha-pilot-and-lean-review.md; canonical managed checkout and exact acceptance receipts. Sharpe is already preparing the human-requested gap chat; do not create a competing gap owner here.

Resource checkpoint: C: free 76,746,752 bytes in this review. Bulk artifacts stay remote; preserve other owners' files and active jobs.
