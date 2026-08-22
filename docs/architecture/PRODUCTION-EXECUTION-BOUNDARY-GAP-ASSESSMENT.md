# PIE Production Execution Boundary Gap Assessment

> Status: **ASSESSMENT COMPLETE — GAP CONFIRMED**
>
> Authority baseline: `83ef8acde08ed0b65a683b514c52a56b43f5fe7c` (`main`, Trust v1.5)
>
> This document is assessment-only. It does **not** implement a production executor, authorize automation, authorize a pilot, authorize deployment, authorize GitHub mutation, or reopen any previously closed Trust risk-model remediation.

## 1. Assessment question

The question is not whether PIE can identify production-relevant changes. Trust v1.5 already classifies governed risk, binds source evidence, requires human review at the appropriate band, and preserves authoritative review/outcome evidence.

The question is narrower:

> Does the current PIE baseline contain a governed boundary that can take an authoritative Trust decision and safely cause an external production-affecting side effect while preserving exact source, action, target, authorization, effect, verification, and recovery provenance?

Assessment result:

```text
PRODUCTION_EXECUTION_BOUNDARY_GAP = CONFIRMED
```

No such governed production execution boundary is present in the current authoritative product surface.

This is currently a **capability gap, not an observed unsafe production execution defect**. The repository remains fail-closed because the missing boundary is not bypassed by an active autonomous production executor.

## 2. Current authoritative boundary

Current authority:

```text
main = 83ef8acde08ed0b65a683b514c52a56b43f5fe7c
Trust risk model = v1.5
Trust mode = REPORT_ONLY
```

The existing path reaches evidence-backed decision support and governed human evidence:

```text
GitHub exact-source capture
→ Trust assessment / risk projection
→ governed prospective case
→ deterministic review packet
→ explicit human REVIEWED / AUDITED event
→ later authoritative Outcome
→ reconciliation
→ observation
→ pilot eligibility review
→ REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION
```

The implemented path stops before a governed production side effect.

## 3. Source findings

### 3.1 Trust is explicitly report-only

`src/review_system/trust.py` defines the current model as v1.5 and emits Trust reports with:

```text
mode = REPORT_ONLY
automation_authorized = false
maximum_automation_band = NONE
```

Risk classification can require `HUMAN_APPROVAL_REQUIRED` or `DUAL_INDEPENDENT_REVIEW_REQUIRED`, but those requirements are review authority requirements, not execution authority.

### 3.2 Pilot safety eligibility does not authorize a pilot

`src/review_system/trust_pilot_review.py` keeps:

```text
MODE = REPORT_ONLY
TARGET_BAND = R0
automation_authorized = false
pilot_authorized = false
```

Even when every safety check passes, the terminal status is only:

```text
ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
next_step = REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION
```

Eligibility and authorization are therefore intentionally distinct.

### 3.3 Pilot evidence execution is evidence replay, not production execution

`src/review_system/trust_pilot_evidence_run.py` uses the term `run`, but its operation is an evidence-package inventory/source-replay/pilot-review run. It explicitly preserves:

```text
mode = REPORT_ONLY
automation_authorized = false
pilot_authorized = false
```

A successful evidence run still ends at `REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION`. It does not dispatch an external production action.

### 3.4 Prospective mutation mutates governed evidence state, not production state

`src/review_system/trust_prospective_mutation.py` performs controlled local mutations such as:

- recording a governed human review event,
- recording a source-reconcilable Outcome,
- copying exact authority artifacts into the prospective evidence workspace,
- atomically replacing local registry/manifest files.

Its mutation target is the governed evidence workspace. It does not represent a deployment, production configuration change, GitHub merge/comment/label mutation, infrastructure change, or application runtime mutation.

This distinction is important:

```text
EVIDENCE_STATE_MUTATION != PRODUCTION_STATE_MUTATION
```

### 3.5 GitHub integration is an evidence collector, not a governed write executor

The current GitHub intake path uses `gh pr view`, paginated read APIs, `gh pr diff`, repository inspection, authentication inspection, and discussion collection to produce source evidence.

`GitHubCLI` is a generic subprocess wrapper around `gh`, so it is technically capable of executing arbitrary arguments if a future caller is added. That generic command-running ability is **not** a production execution authority boundary: it does not itself provide action authorization, capability allowlisting, target binding, idempotency, effect receipts, rollback linkage, or postcondition verification.

No current product entry point establishes such a governed GitHub mutation/execution contract.

### 3.6 Product entry points expose review/evidence functions, not production execution

The current `pyproject.toml` exposes CLI entry points for PIE/URS, Ledger, Defect, Evaluation, Policy, Reground, BuildMap export, Trust, Trust comparison/audit/observation/reconciliation, pilot review/evidence, evidence acquisition, and prospective evidence.

There is no product entry point for a governed production executor or deployment/action dispatcher.

## 4. Gap definition

The confirmed gap is:

```text
AUTHORITATIVE TRUST DECISION
        ↓
[ MISSING GOVERNED EXECUTION BOUNDARY ]
        ↓
EXTERNAL PRODUCTION-AFFECTING SIDE EFFECT
        ↓
VERIFIED EFFECT / RECOVERY EVIDENCE
```

The missing boundary is broader than a single `execute()` function. A safe production execution layer must establish all of the following as one replayable authority chain.

### 4.1 Exact execution request identity

An execution request needs a canonical immutable identity bound to at least:

- project identity,
- exact source revision / source evidence,
- action kind,
- canonical action payload digest,
- intended target identity,
- risk assessment identity,
- required review/authorization identity.

A semantically similar request must not silently inherit authority from a previously approved request.

### 4.2 Execution authorization separate from review eligibility

Current `REVIEWED`, `AUDITED`, Trust readiness, and pilot eligibility evidence must not automatically become execution authority.

Execution requires an explicit authorization object that is bound to the exact execution request and constrains at least:

- authorized action,
- authorized target,
- actor/issuer,
- authorization time,
- expiry or validity window,
- one-shot/replay semantics,
- applicable risk band,
- applicable execution mode.

### 4.3 Least-privilege capability boundary

Production effects must be exposed as explicit capabilities, not arbitrary shell or arbitrary `gh` argument execution.

Examples of capability classes that would require separate contracts include:

```text
GITHUB_PR_MUTATION
DEPLOYMENT_PROMOTION
PRODUCTION_CONFIG_MUTATION
DATABASE_MIGRATION_EXECUTION
SECRET_OR_TRUST_ROOT_ROTATION
ROLLBACK_EXECUTION
```

This assessment does not authorize any of them.

### 4.4 Exact target/environment binding

Source authority alone is insufficient. An execution must bind to the exact target it can mutate, for example:

- provider/account or organization,
- project/repository,
- environment (`production`, `staging`, etc.),
- deployment/service identity,
- region/cluster/database where applicable,
- target-state fingerprint before mutation.

Without this, a valid authorization for one target could be replayed against another.

### 4.5 Pre-dispatch revalidation

Immediately before the side effect, the boundary must fail closed if authoritative assumptions have drifted.

At minimum, revalidation must cover:

- source/head still exact,
- execution request still matches authorization,
- target identity still exact,
- target precondition/state still acceptable,
- authorization still valid and unused,
- kill switch / operator hold is not active,
- required rollback/recovery evidence remains available.

### 4.6 Explicit execution state machine

A production mutation must not collapse `authorized`, `executed`, and `verified` into one boolean.

A minimum lifecycle should distinguish states such as:

```text
PREPARED
→ AUTHORIZED
→ PRECONDITIONS_VERIFIED
→ DISPATCHED
→ APPLIED
→ VERIFIED
```

and failure/recovery states such as:

```text
BLOCKED
DISPATCH_FAILED
APPLY_UNKNOWN
APPLIED_UNVERIFIED
VERIFICATION_FAILED
ROLLBACK_REQUIRED
ROLLBACK_DISPATCHED
ROLLED_BACK
ROLLBACK_FAILED
```

The exact taxonomy is a future design decision; this assessment freezes only the need for phase separation.

### 4.7 Idempotency and replay protection

The boundary requires an execution-attempt identity and idempotency semantics so retries cannot accidentally duplicate non-idempotent production effects.

A prior successful receipt must not be accepted as proof for a different source revision, target, payload, or authorization.

### 4.8 External effect receipt

Local process exit code or provider API `2xx` is not sufficient proof that the intended production effect occurred.

The execution record should preserve provider/runtime evidence such as:

- provider request or deployment identity,
- dispatch timestamp,
- target-observed resulting identity/version,
- externally observable status,
- canonical receipt/provenance digest.

### 4.9 Postcondition verification

`APPLIED` must remain distinct from `VERIFIED`.

The boundary needs an explicit verifier for the intended postcondition. The verifier must be bound to the same execution request and target, and its evidence authority must be defined separately from CI success or command success.

### 4.10 Recovery / rollback provenance

For reversible actions, rollback authority and rollback outcome must be modeled independently rather than represented as free-text evidence.

The system must be able to distinguish:

```text
rollback available
rollback authorized
rollback dispatched
rollback applied
rollback verified
```

## 5. Why existing Trust v1.5 does not close this gap

Trust v1.5 solves a different authority problem.

It answers questions such as:

- what risk band a change belongs to,
- whether source evidence is exact and replayable,
- what human review is required,
- whether review/outcome evidence is authoritative,
- whether evidence is sufficient for a later pilot-authorization review.

It intentionally does **not** answer:

- which production capability may now execute,
- against which exact target,
- with what one-shot authorization,
- whether the side effect was actually applied,
- whether the resulting production state was verified,
- whether recovery was required or successful.

Therefore:

```text
TRUST_DECISION_AUTHORITY != EXECUTION_AUTHORITY
REVIEW_AUTHORITY != EXECUTION_AUTHORITY
PILOT_ELIGIBILITY != PILOT_AUTHORIZATION
COMMAND_SUCCESS != PRODUCTION_EFFECT_VERIFICATION
```

## 6. Current safety interpretation

The confirmed gap does not mean PIE is presently autonomously mutating production without controls.

The opposite is true: current controls stop before production execution.

```text
CURRENT_PRODUCTION_EXECUTION_AUTHORITY = NONE
CURRENT_AUTOMATION_AUTHORITY = NONE
CURRENT_PILOT_AUTHORITY = NONE
CURRENT_SAFETY_POSTURE = FAIL_CLOSED_BY_ABSENCE_OF_EXECUTOR
```

This is safe for the current REPORT_ONLY product, but it is a blocker for any future claim that PIE can safely automate or dispatch production-affecting operations.

## 7. Non-findings

This assessment does **not** conclude that:

- Trust v1.5 risk classification is defective,
- signing trust-root R3 promotion should be reopened,
- current GitHub intake is unsafe merely because `GitHubCLI` wraps subprocess execution,
- production automation should be enabled now,
- R0 pilot eligibility is sufficient execution evidence,
- generic shell execution should become the implementation mechanism,
- BuildMap or Factory Intelligence should become runtime dependencies of PIE.

## 8. Remediation sequence candidate

The safest next work is **not** to add a real production executor immediately.

A bounded sequence is recommended:

### PEB-1 — Shadow Execution Boundary Contract

Define and validate, with zero external side effects:

- execution request contract,
- execution authorization contract,
- target binding,
- capability taxonomy,
- state machine,
- attempt/idempotency identity,
- effect receipt contract,
- postcondition verification contract,
- rollback/recovery linkage,
- fail-closed replay rules.

All outputs remain shadow/report-only.

### PEB-2 — Adapter Capability Inventory / Dry-Run Calibration

Prove that adapters expose only explicitly modeled capabilities and cannot inherit authority from arbitrary command construction. Use synthetic or non-production dry-run evidence only, with an explicit authority ceiling.

### PEB-3 — Controlled Non-Production Execution Calibration

Only after PEB-1/2 close, calibrate the state machine and provenance chain against a controlled non-production target.

### PEB-4 — Explicit Human Pilot Authorization Boundary

Only after separate evidence and explicit user authorization should any real pilot authorization mechanism be considered.

None of PEB-1 through PEB-4 is authorized by this assessment.

## 9. Assessment verdict

```text
PRODUCTION_EXECUTION_BOUNDARY_GAP
= CONFIRMED

GAP_CLASS
= GOVERNED_EXECUTION_AUTHORITY_AND_EFFECT_PROVENANCE_MISSING

CURRENT_TRUST
= v1.5 / REPORT_ONLY

CURRENT_PRODUCTION_EXECUTION_AUTHORITY
= NONE

CURRENT_EXTERNAL_PRODUCTION_SIDE_EFFECT_PATH
= NO GOVERNED PATH FOUND

CURRENT_SAFETY_POSTURE
= FAIL_CLOSED_BY_ABSENCE_OF_EXECUTOR

SIGNING_TRUST_ROOT_AUTHORITATIVE_PROMOTION
= CLOSED / UNCHANGED

EXISTING_R4_AUTHORITY
= UNCHANGED

automation_authorized
= false

pilot_authorized
= false

Stage10K HUMAN_DECISION
= NO NEW DECISION

PRODUCTION_EXECUTION_REMEDIATION
= NOT_AUTHORIZED
```

## 10. Next authorization boundary

The next bounded step, if explicitly approved, is:

```text
PRODUCTION_EXECUTION_BOUNDARY shadow contract 진행
```

That step must remain side-effect-free and must not create production execution authority.