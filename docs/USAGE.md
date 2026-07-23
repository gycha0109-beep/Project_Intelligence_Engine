# Usage Guide — v0.1.1

## 1. Effective profile resolution

A project profile may inherit one or more stack fragments.

```yaml
inherits:
  - spring-postgres
```

Resolution order is left to right, followed by the project profile. Project command groups replace inherited command groups. Language, framework, and review-pack lists are unioned while preserving order.

Use `review.exclude_packs` to remove inherited packs. Project-local stacks are discovered from `<profile-directory>/stacks/` before packaged stacks.

```bash
urs resolve-profile .review/project.yml --output .review/project.resolved.yml
urs validate-profile .review/project.yml
```

## 2. Initialize a review run

```bash
urs init-run .review/project.yml \
  --mode change \
  --snapshot-protected \
  --output docs/reviews/runs/2026-07-19-change-review
```

The run stores both source and resolved profiles and locks every selected Pack version in `packs.lock.json`.

`initial-manifest.sha256` records the generated starting state. The final `manifest.sha256` is created only when archiving, because review artifacts are expected to change during the run.

## 3. Protected-baseline verification

Standalone commands:

```bash
urs snapshot-protected .review/project.yml --output protected-baseline.json
urs verify-protected protected-baseline.json
```

A snapshot records every protected file's relative path, size, and SHA-256. Verification reports added, deleted, and modified files.

## 4. Diff-based Pack routing

```bash
urs select-packs .review/project.yml --files changed-files.txt --json
```

Routing uses normalized path tokens and extensions. It intentionally avoids broad substring matching such as treating `capitalization.ts` as an API file. The result includes reasons for each selected Pack.

## 5. Finding validation

```bash
urs validate-findings findings.json
```

Semantic constraints include:

- `SUPPORTED` requires E2 or stronger evidence.
- `CONFIRMED` requires E3 or stronger evidence and reproduction.
- E3+ evidence requires a command or location and an explicit result.
- `FIXED` may remain `SUPPORTED` or `CONFIRMED` until verification completes.
- `RESOLVED` requires E5 and must be `FIXED` or `CLOSED`.
- `ACCEPTED` requires owner, reason, and review date.
- P0 findings cannot be accepted.
- P0/P1 findings require verification steps.

## 6. Merge independent review outputs

```bash
urs merge-findings explorer.json verifier.json \
  --output findings.json \
  --conflicts-output merge-conflicts.json
```

The primary output is a valid Finding array. Identity mismatches and rejected-versus-active disagreements are preserved in a separate conflict file rather than silently resolved.

## 7. Synchronize a run

```bash
urs sync-run docs/reviews/runs/...
```

This validates `findings.json`, copies it into `run.json`, and derives:

- open confirmed/supported counts by severity,
- fail-level and hold-level blockers from `gate.block_on`,
- fixed-but-unverified blockers,
- accepted residual-risk count.

`ACCEPTED` findings do not remain open blockers. They produce a conditional gate through the residual-risk metric.

## 8. Calculate a gate

Single run file:

```bash
urs calculate-gate run.json
```

Full run directory:

```bash
urs calculate-gate-dir docs/reviews/runs/...
```

Directory calculation synchronizes findings, verifies an available protected baseline, writes `gate-result.json`, and renders `final-gate.md`.

## 9. Validate and archive

```bash
urs validate-run-dir docs/reviews/runs/... --require-gate
urs archive-run docs/reviews/runs/... --output docs/reviews/archive/run.zip
urs verify-manifest docs/reviews/runs/...
```

Archiving is rejected when:

- required inputs or final Gate artifacts are missing,
- Finding validation fails,
- `run.json`, resolved profile, Pack lock, Gate result, or Gate policy are not synchronized,
- the requested ZIP path is inside the run directory.

## 10. Exit codes

- `0`: successful operation; Gate is PASS or CONDITIONAL_PASS.
- `2`: invalid input, schema failure, or command error.
- `3`: Gate is FAIL or HOLD.
- `4`: integrity verification failed.
