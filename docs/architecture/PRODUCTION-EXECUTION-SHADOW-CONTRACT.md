# PIE Production Execution Boundary — Shadow Contract & Dry-Run Calibration

> Status: **PEB-1 PASS / PEB-2 PASS — BLOCKED BEFORE CONTROLLED NON-PRODUCTION EXECUTION**
>
> Authority baseline: `8bb9373c3dd89606bdf1d43c3bd044a137e70d4a`
>
> This work is side-effect-free. It does not authorize production execution, pilot activation, automation, Stage10K human decision, provider credentials, or any external mutation.

## 1. Purpose

The Production Execution Boundary assessment confirmed that PIE had no governed authority chain between an authoritative Trust decision and an external production-affecting effect.

This stage closes only the **shadow contract** and **dry-run calibration** portions of that gap.

The implemented boundary models:

```text
exact source identity
+ Trust report binding
+ explicit capability
+ canonical action payload
+ exact target/environment
+ target precondition fingerprint
+ rollback evidence
+ execution authorization separation
+ pre-dispatch checks
+ adapter capability constraints
+ state transition trace
+ effect/verification placeholders
```

while enforcing:

```text
production_execution_authorized = false
external_side_effect_permitted = false
dispatch_attempted = false
external_effect_observed = false
```

## 2. PEB-1 — Shadow Execution Boundary Contract

Contract:

```text
TRUST_PRODUCTION_EXECUTION_SHADOW_V1
```

Primary implementation:

```text
src/review_system/trust_execution_shadow.py
```

Schemas:

```text
schemas/production-execution-shadow-request.schema.json
schemas/production-execution-shadow-run.schema.json
```

Package copies under `src/review_system/assets/schemas/` are frozen byte-identically.

### 2.1 Exact execution request identity

A shadow execution request is canonically bound to project id, exact source revision, source evidence SHA-256, Trust report id/SHA-256, Trust risk-model version/risk band, capability class/operation, canonical action payload SHA-256, provider/account/resource/environment, exact target precondition fingerprint, and rollback evidence reference/SHA-256.

The request id is content-derived. JSON key ordering does not create a different semantic request identity.

### 2.2 Capability allowlist

Only explicit capability classes can enter the contract:

```text
GITHUB_PR_MUTATION
DEPLOYMENT_PROMOTION
PRODUCTION_CONFIG_MUTATION
DATABASE_MIGRATION_EXECUTION
SECRET_OR_TRUST_ROOT_ROTATION
ROLLBACK_EXECUTION
```

An arbitrary shell/command capability cannot be materialized. This is a contract taxonomy only; no capability is operationally enabled.

### 2.3 Authorization remains separate

Every shadow request contains an ungranted authorization envelope:

```text
required = true
synthetic_only = true
authorization_id = null
authorized = false
```

Therefore:

```text
TRUST_DECISION != EXECUTION_AUTHORIZATION
HUMAN_REVIEW != EXECUTION_AUTHORIZATION
PILOT_ELIGIBILITY != EXECUTION_AUTHORIZATION
```

The verifier rejects any request that attempts to mutate these fields into real authorization.

### 2.4 Pre-dispatch checks

The frozen request contract requires:

```text
EXACT_SOURCE_REVISION
EXACT_TARGET_PRECONDITION
SYNTHETIC_AUTHORIZATION_PRESENT
KILL_SWITCH_CLEAR
ROLLBACK_EVIDENCE_AVAILABLE
```

The request itself remains unevaluated. These checks are evaluated only inside the shadow dry-run.

### 2.5 Execution state ceiling

A request can only be materialized as:

```text
state = PREPARED
```

It cannot claim `DISPATCHED`, `APPLIED`, or `VERIFIED`, and cannot carry an external effect receipt.

## 3. PEB-2 — Adapter Inventory / Dry-Run Calibration

### 3.1 Governed adapter eligibility

A candidate adapter is rejected if it exposes an arbitrary command surface, does not support exact target binding/effect receipt/postcondition verification/rollback, has external side effects enabled during shadow calibration, or does not support the requested allowlisted capability.

### 3.2 Current generic GitHub CLI classification

The existing `GitHubCLI` path is a generic command runner used by the current evidence collector. For execution-boundary purposes its observed shape is calibrated as:

```text
adapter_id = github-cli-generic
arbitrary_command_surface = true
target_binding_supported = false
effect_receipt_supported = false
postcondition_verifier_supported = false
rollback_supported = false
external_side_effects_enabled = true

status =
NOT_ELIGIBLE_FOR_GOVERNED_EXECUTION_ADAPTER
```

This does not classify the current GitHub evidence collector as unsafe. It means the generic runner cannot itself become execution authority.

### 3.3 Synthetic explicit adapter control

A synthetic side-effect-disabled adapter with an explicit capability, exact target binding, effect receipt contract, postcondition verifier contract, and rollback contract is accepted only as:

```text
ELIGIBLE_FOR_CONTROLLED_NON_PRODUCTION_IMPLEMENTATION_REVIEW
```

This is a genericity/control fixture, not real execution evidence.

### 3.4 Positive dry-run terminal state

A structurally valid request with exact source, exact target, synthetic authorization, clear kill switch, rollback evidence, and an eligible synthetic adapter reaches:

```text
PREPARED
→ SHADOW_AUTHORIZED
→ PRECONDITIONS_VERIFIED
→ DISPATCH_SUPPRESSED
```

Terminal result:

```text
status = SHADOW_CALIBRATION_PASS
next_step = CONTROLLED_NON_PRODUCTION_EXECUTION_REQUIRED

dispatch_attempted = false
external_effect_observed = false
effect_receipt = null
postcondition_verified = false
rollback_dispatch_attempted = false
```

A successful shadow run proves only that the contract can reach the dispatch boundary while remaining unable to cross it.

### 3.5 Negative calibration matrix

The following all fail closed:

```text
source revision drift
target precondition drift
synthetic authorization absent
kill switch active
rollback evidence unavailable
requested capability unsupported by adapter
```

Every negative path terminates at `BLOCKED` with no dispatch and no external effect.

### 3.6 Tamper resistance

The verifier rejects tampering of source revision, target fingerprint, action payload, authorization fields, dispatch/effect claims, adapter assessment, canonical request/run identities, and evidence snapshot/report hashes.

## 4. Frozen evidence

Calibration fixture:

```text
tests/fixtures/trust-execution-shadow/calibration-v1.json
```

Automated verification:

```text
tests/test_trust_execution_shadow.py
```

The tests cover deterministic identity, request tamper rejection, arbitrary capability rejection, current generic GitHub CLI rejection, explicit synthetic adapter acceptance, positive dry-run, negative fail-closed paths, requested-capability mismatch, run-side-effect claim rejection, adapter-assessment tamper rejection, external-execution dependency isolation, and schema asset synchronization.

## 5. Current authority ceiling

After PEB-1/2:

```text
PRODUCTION_EXECUTION_BOUNDARY_SHADOW_CONTRACT
= IMPLEMENTED

SHADOW_DRY_RUN_CALIBRATION
= IMPLEMENTED

PRODUCTION_EXECUTION_AUTHORITY
= NONE

PRODUCTION_MUTATION
= NOT AUTHORIZED

NON_PRODUCTION_MUTATION
= NOT AUTHORIZED

automation_authorized
= false

pilot_authorized
= false

Stage10K HUMAN_DECISION
= NO NEW DECISION
```

## 6. Blocker

The next stage can no longer be proven using only synthetic/report-only execution.

A real PEB-3 calibration requires:

1. an explicitly designated **non-production target**,
2. a least-privilege adapter that can mutate only that target,
3. credentials scoped to that target,
4. explicit authorization to cause the non-production side effect,
5. a provider/runtime effect receipt,
6. an independently checked postcondition,
7. rollback/recovery execution evidence.

None of these authorities is created by PEB-1/2.

Therefore:

```text
PEB-3
= BLOCKED

BLOCKER
= CONTROLLED_NON_PRODUCTION_EXECUTION_REQUIRED

BLOCKER_CLASS
= EXTERNAL_SIDE_EFFECT_AND_TARGET_AUTHORITY_REQUIRED
```

Crossing this boundary without an explicitly authorized non-production target would invalidate the separation between shadow calibration and real execution evidence.

## 7. Final stage result

```text
PEB-1_SHADOW_EXECUTION_BOUNDARY_CONTRACT
= PASS

PEB-2_ADAPTER_INVENTORY_AND_DRY_RUN_CALIBRATION
= PASS

CURRENT_GENERIC_GITHUB_CLI_AS_EXECUTION_ADAPTER
= REJECTED

SHADOW_POSITIVE_TERMINAL_STATE
= DISPATCH_SUPPRESSED

PRODUCTION_EXECUTION
= NOT ATTEMPTED

NON_PRODUCTION_EXECUTION
= NOT ATTEMPTED

NEXT_STAGE
= PEB-3 CONTROLLED NON-PRODUCTION EXECUTION CALIBRATION

NEXT_STAGE_STATUS
= BLOCKED_PENDING_EXPLICIT_EXTERNAL_TARGET_AND_EXECUTION_AUTHORITY
```
