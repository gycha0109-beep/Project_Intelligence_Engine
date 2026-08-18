# Stage 10G — R0 Pilot Eligibility Evidence Run

## 1. Purpose

Stage 10G answers one operational question:

> Does the evidence package currently supplied to PIE actually reach `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW` under the existing Stage 10B/10C/10D/10E/10F contracts?

This stage does not add pilot activation authority. It inventories a bounded evidence package and dispatches the existing authority-aware Stage 10E exact replay only when the package is complete.

Fixed values remain:

```text
mode=REPORT_ONLY
target_band=R0
automation_authorized=false
pilot_authorized=false
```

`ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW` is not `PILOT_AUTHORIZED`.

## 2. Repository authority at stage start

Stage 10G was branched from:

```text
branch: agent/stage-10d-operating-observation-threshold-policy
exact SHA: 35697b32c1bc751b4831ea92756db44495e6c792
post-merge CI: #847 / run 32098825273 / SUCCESS
```

Stage 10F had already been merged into that stacked branch.

## 3. Initial committed-repository evidence inventory

The Stage 10G start snapshot does not contain a committed R0 pilot evidence package with the required Trust artifacts.

The repository contains implementation code, schemas, tests, and a sample observation policy. It does not contain a committed package consisting of the Stage 10B comparison registry, Stage 10C reconciliation source manifest/report, and Stage 10D observation policy/report required to invoke Stage 10E against real evidence.

This finding has an important scope boundary:

- `.pie/` is gitignored.
- `.review-runs/` is gitignored.
- therefore absence from the committed tree does **not** prove that a local or externally retained runtime evidence package cannot exist.
- tests, fixtures, and `*.sample.*` content must not be substituted merely to make the eligibility gate pass.

The correct committed-repository interpretation is therefore:

```text
COMMITTED_R0_EVIDENCE_PACKAGE_PRESENT = NO
COMMITTED_REPOSITORY_ELIGIBILITY = NOT_ELIGIBLE
NEXT_STEP = PROVIDE_COMPLETE_R0_EVIDENCE_PACKAGE
```

It is deliberately **not**:

```text
NO_RUNTIME_EVIDENCE_EXISTS_ANYWHERE
```

## 4. Canonical evidence-package contract

Stage 10G accepts an evidence root, conventionally:

```text
.pie/r0-pilot-evidence/
```

The top-level contract is:

```text
comparison-registry.json
reconciliation-sources.json
reconciliation-report.json
observation-policy.json
observation-report.json
```

The Stage 10C reconciliation source manifest remains responsible for safe relative references to underlying Trust reports, requests, profiles, Ledgers, Evaluation reports, Defect registries, Stage 10F audit artifacts, and Audit Authority registries.

Stage 10G does not copy sample data into this package and does not synthesize missing authority evidence.

## 5. Execution model

### 5.1 Inventory

For each required top-level file Stage 10G records:

- canonical key
- canonical filename
- presence
- SHA-256 when usable

A missing, symlinked, broken-symlink, or non-regular required file is not accepted as usable evidence and is represented as a missing evidence blocker.

A symlink in the evidence-root path itself is rejected as unsafe input.

### 5.2 Incomplete package

If any required top-level artifact is missing:

```text
status = NOT_ELIGIBLE
source_replay.attempted = false
pilot_review.attempted = false
next_step = PROVIDE_COMPLETE_R0_EVIDENCE_PACKAGE
```

This is a valid Stage 10G result, not a process crash and not a CI failure.

### 5.3 Complete package

Only a complete package is passed to the existing Stage 10E authority-aware review boundary.

That boundary verifies:

- Stage 10B comparison registry identity
- Stage 10C reconciliation report and exact source replay
- Stage 10D observation report and exact policy/registry replay
- Stage 10F Independent Audit provenance through Stage 10C
- Stage 10E cross-artifact registry/project binding and safety checks

Stage 10G does not weaken or replace any of those checks.

### 5.4 Exact replay failure

If the package is present but Stage 10E cannot verify its authority chain:

```text
status = NOT_ELIGIBLE
blocker includes SOURCE_REPLAY_FAILED
next_step = REPAIR_AND_REPLAY_SOURCE_EVIDENCE
```

### 5.5 Eligible result

Stage 10G can preserve Stage 10E eligibility only when all of the following are true:

```text
package_complete == true
source_replay.attempted == true
source_replay.verified == true
pilot_review.attempted == true
pilot_review.status == ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
blockers == []
```

Even then:

```text
pilot_authorized=false
automation_authorized=false
next_step=REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION
```

## 6. Verification model

The Stage 10G report contains:

- inventory SHA-256 values
- deterministic evidence snapshot SHA-256
- deterministic `run_id`
- outer report SHA-256
- Stage 10E review identity/hash projection when attempted
- Stage 10E blocker projection

`generated_at` participates in the outer report hash but not in evidence identity.

Self-contained verification checks report/schema/projection consistency. It does not substitute for source authority.

For an eligible report, CLI verification requires:

```text
--evidence-root
```

and reruns the exact evidence package. An eligible report cannot be accepted through the CLI on self-contained verification alone.

## 7. Real-evidence meaning and trust-model limit

Stage 10G uses “real evidence” to mean evidence supplied through the repository-defined authority contracts rather than samples/fixtures automatically manufactured by Stage 10G.

Stage 10G does **not** independently prove that every supplied artifact reflects an external real-world event rather than a deliberately constructed artifact. Its authority is bounded by the upstream contracts:

- Stage 10A Trust source replay
- Stage 10B event/assessment integrity
- Stage 10C semantic authority replay
- Stage 10D observation integrity
- Stage 10F repository-governed audit provenance

In particular, Stage 10F Trust Root metadata is not external PKI or independent non-repudiation. A separate external evidence attestation system would be required to prove stronger real-world authenticity.

## 8. CLI

Standalone:

```text
pie-trust-pilot-evidence run-r0-pilot-evidence \
  --evidence-root .pie/r0-pilot-evidence \
  --output .pie/r0-pilot-evidence-run.json
```

Delegated:

```text
pie-trust run-r0-pilot-evidence \
  --evidence-root .pie/r0-pilot-evidence \
  --output .pie/r0-pilot-evidence-run.json
```

Verification:

```text
pie-trust-pilot-evidence verify-r0-pilot-evidence-run \
  --report .pie/r0-pilot-evidence-run.json \
  --evidence-root .pie/r0-pilot-evidence
```

## 9. Terminal interpretation

Stage 10G implementation can PASS while the current evidence result remains `NOT_ELIGIBLE`.

Those are different statements:

```text
STAGE_10G_IMPLEMENTATION_PASS
!=
R0_PILOT_ELIGIBLE
```

The next stage, `R0 Pilot Activation Contract`, is only appropriate after an actual Stage 10G evidence run reaches `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW` and a human explicitly chooses to proceed.
