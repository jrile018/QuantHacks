# Installed skill and active-chat audit

Owner: Track work across project chats. Date: 2026-10-04 UTC. Human scope: inventory all discovered installed/cached skills; apply guidance to active QuantHaxs chats only.

## Verdict

The useful improvement is task-specific skill selection, compatible tool calls, clear ownership and short handoffs. Loading every skill into every chat would add conflicting instructions and irrelevant work. Six other active project chats already own the current critical path; [capacity review](chat-capacity.md) recommends no additional chat for the first costed milestone now.

The [operating guide](../skills-usage.md) gives each lane a profile. Delivery, acknowledgement, observed use and validated output are separate states; this audit cannot guarantee future optimal behaviour or measure savings from skill descriptions.

## What was inspected

- **444 SKILL.md files**, **298 distinct names**, **403 distinct content hashes**, **121 same-name groups**, 2,773,063 bytes. The inventory includes the Codex user/system skill root, .agents skills, the complete Codex plugin cache, Claude skills and the complete Claude plugin cache. A fresh rg enumeration matched all 444 paths: no omitted or unexpected path in those five roots.
- Every discovered definition was read by an automated full-body inventory, hashed, categorized and scanned for portability/trigger/reference candidates. Manual semantic review concentrated on routing, planning, process, memory and project architecture/evidence families used by this project. This is not a manual certification of every connector or third-party instruction.
- [Catalog](catalog.md): one row per file, exact path/hash/category/flags. Machine receipts: `data/processed/chat_tracking/skill-audit-20261004/inventory.json` and `summary.json`.
- Six active QuantHaxs chats were inspected using bounded recent turns. Skill references and declarations were observed; a path string alone does not establish a successful skill read. Unobserved usage in a short window is not a violation. The observation receipt records this limit.
- Safe configuration inspection found 13 enabled plugin entries and a configured default of gpt-6.1-sol with ultra effort. These are configuration defaults, not measured per-chat runtime settings, costs or latency. No global setting, plugin, skill or model was changed.

Versions, translations and cached copies explain many same-name groups. They do not establish 444 simultaneously active skills or 121 enabled conflicts. Current session exposure and callable tools remain authoritative.

## Highest-impact findings and resolution

| Finding | Evidence | Consequence | Applied guidance |
|---|---|---|---|
| Legacy agent/model syntax | model-router lines 41–60; lean-router 78–83; claude-router 74–84; harness-optimizer 56–64 | Claude Agent()/haiku/sonnet/opus examples do not describe the live collaboration API | Keep the cost-tier intent; use supported model names and actual tool schema |
| Incorrect full-history override instructions | superpowers using-superpowers/references/codex-tools.md 17–23, 62–68 | Full-history forks reject model/effort overrides in this session | Fresh/focused forks may carry an explicit supported model; full-history forks inherit settings |
| Shared planning-file collision | cached planning-with-files 35–37, 59–76, 132–136 | Default root writes would collide with Post Benchmark's owned task_plan.md/progress.md | Use one current workflow in each lane's owned files; coordinator uses docs/coordination |
| Repeated planning/approval and excessive verification | writing-plans 169–186; dispatching-parallel-agents 68–85, 161–167 | Replanning, extra approval loops or broad test runs can delay already authorized work | Continue approved scope; test concrete risks and required gates; optional work does not block first costed replay |
| Unmeasured cost/latency claims and foreign configuration | harness-optimizer 3, 16–50, 79–100; lean-router 72–75, 93–108; claude-router 3, 111–121 | Percent savings, prices, MAX_THINKING_TOKENS and /route are not validated native capabilities | No savings percentage or global configuration change; use focused cheaper helpers and compact evidence |
| Graph tool/path portability | gsd-graphify 14, 126–190 | Documented local CLI/path was absent; graph presence does not imply runtime wiring | Reuse the verified remote Graphify runtime and pinned receipts; refresh changed boundaries only |
| Missing named local definitions | Complete path inventory | remote-compute and grill-me were not installed as local SKILL.md definitions | Human remote-compute policy still applies; prior public grill source is a documented fallback, not an installation |
| Cache presence confused with exposure | planning-with-files, frontend/UI and Obsidian families exist in Claude cache | File availability is not proof a Codex chat has the skill/tool exposed | Resolve an exact readable path if relevant; check actual tools; do not load irrelevant families |
| File-only heuristic research skills | quant-research 9–16, 20–23; project-architecture 8–14 | Universal sample/Sharpe/permutation rules or blanket refactors do not fit every event universe | Use effective independent events, registered comparisons, causal clocks and existing architecture; no automatic universal gate |

The local system and third-party `skill-creator` definitions share a name: use an exact namespace/path. Two relative-link candidates in the native skill-creator file appear inside an illustrative example; they are not certified missing runtime dependencies.

Automated flags are screening candidates: 16 legacy-model, 32 broad-mandatory-trigger, 182 external-command/dependency, 127 legacy-agent-API and 55 percentage mentions. A percentage mention can be a legitimate technical parameter; these counts are not defect counts.

## Task families

| Family | Inventory files | Selection rule |
|---|---:|---|
| GSD workflow | 162 | Use the selected phase workflow and current lane state; do not start a second planner |
| Connector/platform | 68 | Use only for an actual requested app/platform task and available capability |
| Specialized/on demand | 65 | Match the actual task, not a keyword |
| Process | 44 | Design, debug, implement, review and verify at the relevant stage |
| Memory/handoff | 31 | Prior context uses search → timeline → filtered details; current state comes from current files/receipts |
| Visual/design | 23 | Use when a visual or interface helps the user's task |
| Routing/context | 19 | Preserve semantic evidence while narrowing context and delegating focused work |
| Planning/communication | 18 | One owned workflow; scoped producer/consumer messages |
| Document/artifact | 7 | Use for an actual document, sheet, deck, PDF or template deliverable |
| Project architecture/evidence | 7 | ICM routes, exact source/receipt checks, state separation and changed-boundary freshness |

Marketing, resumes, raffles, unrelated brands, pets and deployment tools have no current quantitative-pipeline requirement. Leaving them inactive is appropriate. Skill instructions do not create spending, publication, instrument, live-capital or final-test permission.

## Active-chat profiles and status

The full profiles are in [skills-usage.md](../skills-usage.md). All six are active in the exact workspace at the inventory checkpoint. Scope excludes other projects and dormant OCR/HiPerGator chats.

| Exact chat title | Main application | Current ownership/gate |
|---|---|---|
| Benchmark | Focused source exploration; one implementation plan; debugging, meaningful tests and verified handoff | Native financial/matrix producer in its managed checkout; settled local producer commit/documents checked; full canonical acceptance pending |
| Benchmark pt. 2 industry spec | Source truth, dated clocks/identity, quarantine, targeted tests and paid/compute reconciliation | Industry producer and shared source/spending guard; usable data and canonical joins are not inferred from samples |
| Post Benchmark | Architecture/evidence checks, boundary debugging, consumer acceptance, costed replay | Sole canonical registry/FeaturePanel/evaluator and integrated costed capsule owner |
| Assess Lattice repo fit | Bounded Graphify/ICM, numerical debug/test/review, registered diagnostic comparisons | Numerical producer; archived graph and diagnostics do not certify economic value |
| Organize Benchmark Data Push | Owned documentation plan, project truth, isolated package verification and review | Publication/source contribution guide; preserve source owners, rights and maintainer merge decision |
| Research Sharpe confidence intervals | Primary research, owned plan, inference/counterexample review and reproducible simulation design | Conditional Sharpe uncertainty on an accepted economic ledger; no invented returns or forced final-test access |

Recent observed references are retained in `chat-observations.json`. Peer delivery and acknowledgements are recorded separately in `dispatch.json`; guidance delivery alone is not skill-use validation. Complete job/test/consumer evidence remains with the existing owners.

## Related verified research handoff

Post Benchmark's English-feature packet was independently hash checked: seven supplied hashes match. It defines **50 proposed disabled features, zero computed features**, train-only fitting and separate anticipation/reaction views. Full native mapping/generated registry hash is pending. This is cleared document research, not a trained model, implemented matrix extension or economic result.

The prior Post continuation-v1 capsule records 659 tests, 187 frozen files, six equity diagnostic fits, 752 paired rows across 188 dates and zero qualified costed targets. It is **not Benchmark's native V7 packet**. Its economic state remains insufficient.

## Follow-through

1. Deliver tailored guidance once to each active participant without stopping its current jobs.
2. Ask for a compact checkpoint acknowledgement: chosen owned workflow/skills, capability gaps, existing helper scopes and any ready unowned task. Preserve reported versus independently verified findings.
3. Reference the guide in continuation handoffs and the existing quiet monitor. Recheck a profile when scope or relevant skill/tool availability changes; do not reload/re-audit all 444 files on every heartbeat.
4. Add a chat only when its scoped task is ready, approved and unowned, with exact handoff/completion criteria. At this checkpoint no new chat is recommended for the first costed milestone.

Checkpoint: guide delivered to six participants; five acknowledged the profile/workflow or were observed declaring its adoption, and one acknowledgement remains pending. This is not proof of optimal future use. A disk-full error interrupted command startup; only the redundant35,672-byte audit path list was removed after verifying its444 entries remain in the inventory/catalog. Other owners reported their own hash-verified remote-backed cleanup; their actions are not attributed to this audit.

Global edits, installs, new user-owned chats, jobs, purchases, broad refactors and model changes were not performed by this audit. These findings have been addressed through project-local routing and owner guidance; global source defects remain documented.

## Newly active hardware participant

A final inventory found the human-created **Check remote desktop GPU access** chat in this workspace. Its direct user requests concern remote GPU access and suitable math optimization. Hardware-stack guidance and the shared compute/source ownership context were delivered; its profile is in the guide and it is watched. Seven project peers now have guidance; five original participants acknowledged/declared adoption, and the publication-guide/GPU natural checkpoints remain pending. The original six-chat observation sample is retained as dated evidence; no orchestrator chat was created.
