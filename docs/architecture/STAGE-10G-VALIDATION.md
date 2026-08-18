# Stage 10G Validation

## 1. Validation target

Stage 10G must prove two independent properties:

1. the evidence-run implementation is correct and fail-closed;
2. implementation success does not misrepresent the current committed repository as pilot-eligible when no committed R0 evidence package exists.

## 2. Baseline authority

Stage branch base:

```text
agent/stage-10d-operating-observation-threshold-policy
35697b32c1bc751b4831ea92756db44495e6c792
```

Post-Stage-10F merge CI on that base:

```text
CI #847
run 32098825273
SUCCESS
```

## 3. Repository evidence inventory

The exact base tree was inspected before Stage 10G implementation.

Observed:

- Trust implementation/schema/test assets exist.
- `examples/trust-observation-policy.sample.json` exists and is explicitly a sample by path/name.
- no committed canonical `.pie/r0-pilot-evidence/` package exists.
- no committed top-level set of the five Stage 10G authority inputs exists as a real pilot evidence package.
- `.pie/` and `.review-runs/` are gitignored.

Therefore the committed-repository evidence conclusion is:

```text
NOT_ELIGIBLE
PROVIDE_COMPLETE_R0_EVIDENCE_PACKAGE
```

with scope limited to the committed repository snapshot.

## 4. Focused test coverage

### 4.1 Missing evidence

Validates:

- nonexistent evidence root produces a valid report
- all five required sources are missing blockers
- Stage 10E is not invoked
- status is `NOT_ELIGIBLE`
- CLI exit is zero for a valid not-eligible result
- authorization flags stay false

### 4.2 Partial package

Validates:

- one or more existing top-level files cannot trigger source replay early
- missing evidence remains explicit

### 4.3 Complete eligible projection

Uses a mocked Stage 10E return only to test Stage 10G composition semantics.

Validates:

- complete package hashes are captured
- Stage 10E invocation is attempted
- exact replay result is required
- the strongest status is only `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW`
- `pilot_authorized=false`
- `automation_authorized=false`

This is a unit test of composition, not operational eligibility evidence.

### 4.4 Stage 10E blocker preservation

Validates:

- Stage 10E `NOT_ELIGIBLE` is not rewritten
- Stage 10E blockers and next-step semantics are preserved

### 4.5 Source-replay failure

Validates:

- reconciliation or observation replay failure blocks eligibility
- Stage 10G adds `SOURCE_REPLAY_FAILED`
- next step becomes `REPAIR_AND_REPLAY_SOURCE_EVIDENCE`

### 4.6 Malformed complete package

Validates that five present files are not sufficient by themselves.

A complete but invalid authority package must yield:

```text
package_complete=true
source_replay.attempted=true
source_replay.verified=false
status=NOT_ELIGIBLE
```

rather than crashing or becoming eligible.

### 4.7 Top-level source mutation

Validates that changing a required file after report generation changes the inventory hash and fails exact report replay.

### 4.8 Nested source mutation

Covered by the inherited Stage 10C/10E replay suites, including Trust source mutation and Stage 10F audit authority mutation/revocation semantics.

### 4.9 Symlink safety

Validates:

- evidence-root symlink is rejected
- a symlinked required file is not accepted as usable evidence
- output symlink is rejected without target mutation

### 4.10 Atomic write

Validates existing output bytes survive `os.replace` failure.

### 4.11 Semantic rehash

Validates:

- changing only status/blockers/next-step and refreshing hashes cannot escalate an incomplete package
- `pilot_authorized=true` remains invalid even after rehash

### 4.12 Generated time

Validates:

- changing only `generated_at` preserves evidence snapshot identity and `run_id`
- outer report hash changes

### 4.13 Eligible verification authority

Validates:

- an eligible report cannot be accepted through the CLI without `--evidence-root`
- eligible verification therefore requires current exact source replay

### 4.14 CLI delegation

Validates both:

```text
pie-trust-pilot-evidence
pie-trust run-r0-pilot-evidence
```

## 5. Regression evidence during implementation

Initial Draft PR CI:

```text
CI #857
run 32100850034
Python 3.11 SUCCESS
Python 3.13 SUCCESS
Python 3.14 SUCCESS
```

This run covered the initial Stage 10G core/schema/module test set before later CLI-hardening commits.

A later implementation CI also showed Python 3.11 and 3.14 full success while the remaining matrix job was still progressing when documentation work continued. These intermediate runs are not the terminal authority because the branch changed afterward.

## 6. Terminal CI requirement

After all implementation-review, hardening, documentation, and index changes are complete, the unchanged exact HEAD must pass the repository CI matrix:

```text
Python 3.11
Python 3.13
Python 3.14
```

including:

- editable install
- package asset sync
- full unittest discovery
- existing `urs` version/profile/Finding validations
- wheel build

The final exact HEAD/run ID is recorded in the PR terminal metadata after this document is committed so that the CI evidence remains documentation-inclusive without introducing a circular post-CI documentation commit.

## 7. Safety interpretation

A Stage 10G implementation PASS proves that PIE can correctly inventory and replay a supplied evidence package.

It does **not** prove that the currently available evidence is sufficient.

For the committed repository snapshot inspected at stage start:

```text
R0_PILOT_ELIGIBILITY = NOT_ELIGIBLE
REASON = COMMITTED_EVIDENCE_PACKAGE_NOT_PRESENT
```

Because runtime roots are gitignored, an operator may later supply a separate package and rerun Stage 10G. Only that exact package's replay result can establish a later eligibility state.

No Stage 10G result authorizes pilot activation.
