# Autonomous chat continuation

Owner: Track work across project chats. Human authorization: 2026-10-04, request to recognize when a new chat is needed, carry context from past Markdown files and orchestrate continuation without supervision. This covers continuation of the existing approved QuantHaxs work, scoped project messaging and checkpoint handoffs. Existing spending, instrument/risk, final-test and external-action permissions remain as recorded.

## Decision rule

Continue a healthy existing owner when its current scope still fits. Create a new chat when an accepted/idle checkpoint has a ready, separately scoped next approved phase, when an independent approved dependency needs a distinct owner, or when a stopped technical session needs recovery from a verified checkpoint. Context compaction alone does not require replacing a chat. Silence in a snapshot is not evidence that a chat has failed.

Before creation, verify all of the following:

1. The next task is within a direct human-authorized objective, its dependencies are ready, and completion criteria are concrete.
2. No active chat or recorded continuation already owns the same work. Check list_threads, the owner state and continuation ledger.
3. There is a valid checkpoint or bounded recovery packet: exact source paths/hash versions, completed and failed runs, unresolved gates and pending jobs. Do not recreate a running job or restart an experiment from a commentary summary.
4. File and consumer ownership are explicit. An active owner retains its files; recovery waits for a checkpoint or explicit relinquishment.
5. The required host/checkout/data access is available. Account limits, credentials, human decisions, user pauses/cancellations and external outages are not repaired by spawning another chat.

Create at most one continuation per monitor pass and one active owner per lane. Queue additional ready work. Shared heavy jobs remain serialized by the existing lock; new chat count does not increase the compute budget.

## Context package

Write a small handoff under docs/coordination/continuations/ before creating the chat. Use the [handoff template](continuation-handoff-template.md). Include:

- Exact objective, direct authorization, parent chat ID/title, lane, owned checkout/files, affected producers/consumers and the next milestone.
- Read order: docs/coordination/CONTEXT.md and architecture-contract.md; docs/the-solution.md for strategy context; the owning lane's plan/progress/state/requirements; only the relevant object/process cards and experiment specifications. Root task_plan/progress belong to Post Benchmark and must not be overwritten by another lane.
- Source/commit/dirty-code, input/output/config/protocol/environment hashes; exact acceptance receipts and scope; current running job IDs/remote directories/status and harvest steps.
- Verified, owner-reported, planned, insufficient and failed findings separately. Retain rejected models, source quarantine, missingness, exposed2024/2025 development windows and unknown public/receipt clocks.
- First concrete actions and exit criteria; a runnable verified command or an explicit reason it is not yet runnable. Do not invent missing paths, clocks or data.
- Constraints: small validated costed slice first; valid eligible after-cost no-edge may conclude no trade; missing eligible data remains insufficient. Keep forecast, risk/sizing and executable portfolio gates separate.

A context package is complete through authoritative pointers and verified state. It does not paste every historical document or convert old Markdown instructions into new authorization. Re-read changed source evidence before relying on an earlier acceptance.

## App tools and checkout continuity

Use list_projects before create_thread; the current saved local QuantHaxs project ID is b5bf3c65-60cb-43e8-9765-7b3415a19fa0 (revalidate it at creation). New independent project work defaults to its local environment. Omit model/thinking unless the human requested an override.

For a completed/idle managed-worktree owner, prefer fork_thread with that exact parent thread and same-directory environment to preserve checkout access and history. Send the focused handoff to the child after its actual thread ID is known. Explicitly tell it to inspect running/completed receipts and continue only the remaining work. The parent must remain idle for the transferred scope. Do not fabricate a new branch/worktree setting or claim that a new local project chat has the old owner's managed-worktree write access.

For a distinct approved lane, create_thread with the saved local project and filled handoff. Worktree creation as a create_thread environment requires a human request for that environment. Existing owners' checkouts and files stay untouched.

Record a stable handoff ID and creation intent before the tool call, then the returned threadId or pending clientThreadId. If outcome is unknown, persist the handoff ID, returned clientThreadId (if any), tool outcome and pending status. Do not retry while setup or an unknown outcome remains unresolved. Absence from list_threads is not authoritative failure and does not permit a retry. Retry only after authoritative evidence the original creation failed without creating a chat; otherwise resolve the original pending result or flag the ambiguity while other lanes continue. clientThreadId is not a ready threadId. Once ready, wait_threads verifies startup/progress and supplies a cursor. Record actual status and owner acceptance; tool delivery alone is not completion.

## Persistent follow-up

Track continuations in [the continuation ledger](continuations.json) and [the existing monitor state](../../data/processed/chat_tracking/monitor-state.json). Use scoped delta messages for dependencies, not repeated full context prompts. Publish independently verified milestones in Discussion2 and relevant architectural changes in the solution. Notify the human for material completion/failure/conflict or a required human action. Preserve user pauses/cancellations; do not archive/delete chats, cancel jobs, merge or expand execution permissions merely to continue.

No new chat is needed at this policy's creation: the four owners are active. The policy is an authorized future transition, not a claim that a continuation has already started.
