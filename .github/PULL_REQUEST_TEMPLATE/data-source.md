## Source and scope

Source ID and owner:
Stage in source.json: discovery / extracted:
Base main commit and current branch commit:

- [ ] Exactly one registered source on codex/source-<source-id>-<owner>.
- [ ] No shared schema, pipeline, workflow or gate changes; link a separate PR if needed.
- [ ] No originals, generated results, credentials, model weights or nested repository.

## Contract and provenance

- source.json, manifest and acquisition README paths:
- Stable document IDs, canonical source URLs and coverage:
- Batch/transcript schema and adapter revisions:
- Documents discovered / downloaded / extracted / failed:
- Source-byte hashes and publication/receipt evidence:
- Unknown identity, clock, definition or quality fields:
- Synthetic fixture manifest and adapter test module (if applicable):

## Validation and merge

Exact commands, exit codes and results:
- [ ] Source configuration validator.
- [ ] Native smoke and relevant existing/source adapter tests.
- [ ] Source-only change gate against current main and HEAD.
- [ ] Required CI: source-configuration and Source adapter tests, matching current PR head.
- [ ] Rebased exclusive branch or merged current main into shared branch; conflicts resolved and retested.
- [ ] Agent merge uses --match-head-commit; no admin bypass.

## Integration

Affected Benchmark / industry / Post Benchmark owner:
Research readiness: discovery / extracted / consumer accepted (with owner receipt):
Remaining blockers and next action:
