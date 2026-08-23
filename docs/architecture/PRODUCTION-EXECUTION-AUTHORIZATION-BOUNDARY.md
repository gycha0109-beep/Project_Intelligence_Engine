# Production Execution Boundary — PEB-4A Authorization Review

Status: `PEB-4A BLOCKED / FAIL-CLOSED BEFORE PRODUCTION EFFECT AUTHORIZATION`

## Starting authority

Authoritative PIE main at stage entry:

```text
19922fc7148d73ce3d8d686858582da560f915c5
```

Inherited closeout:

```text
PEB-3R = COMPLETE
PEB-3E = PASS
CONTROLLED_NON_PRODUCTION_EXECUTION_AND_ROLLBACK = VERIFIED
PRODUCTION_EXECUTION_AUTHORITY = NONE
```

The user explicitly authorized continuation into the next production-execution boundary. PEB-4A records that as **production-boundary entry authority only**:

```text
production_boundary_authorized = true
production_execution_authorized = false
effect_authorization.authorized = false
automation_authorized = false
pilot_authorized = false
```

Boundary entry is not an authorization for an unspecified production side effect.

## Purpose

PEB-4A creates the authorization-review contract that must exist before PIE may ask for a one-shot production effect authorization.

A production effect request is not eligible for PEB-4B until it binds all of the following into one deterministic request hash:

```text
exact PIE source revision
+ authoritative Trust report id / hash / risk band
+ exact production provider and target resource
+ exact capability class
+ exact operation
+ exact rollback operation
+ canonical action payload hash
+ exact target precondition fingerprint
+ production credential-scope evidence
+ rollback evidence
+ independent postcondition verifier evidence
+ bounded blast-radius evidence
+ kill-switch evidence
+ recovery-window evidence
```

The resulting `request_sha256` is the object that a later PEB-4B authorization decision must approve. PEB-4A itself can never set `production_execution_authorized=true`.

## Frozen authority distinctions

```text
PRODUCTION_BOUNDARY_ENTRY_AUTHORITY
!= PRODUCTION_EFFECT_AUTHORIZATION

PRODUCTION_EFFECT_AUTHORIZATION
!= AUTOMATION_AUTHORITY

TRUST_DECISION_AUTHORITY
!= EXECUTION_AUTHORITY

TARGET NOMINATION
!= CREDENTIAL SCOPE

COMMAND SUCCESS
!= PRODUCTION EFFECT VERIFICATION

ROLLBACK PLAN
!= ROLLBACK PROOF
```

A generic instruction to continue the production-boundary work may authorize PEB-4A review work, but it must not be projected onto a not-yet-defined target, operation, payload, or rollback.

## Current review

Current evidence:

```text
evidence/trust/peb4a-production-authorization-20260823.json
```

Boundary authorization is present:

```text
basis = EXPLICIT_HUMAN_PRODUCTION_BOUNDARY_AUTHORIZATION
authorization_id = human-peb4a-20260823-proceed
authorization_ref = conversation:2026-08-23:user-proceed-after-peb3e-closeout
```

No production target or effect request has yet been nominated.

Current blockers:

```text
PRODUCTION_ACTION_PAYLOAD_NOT_BOUND
PRODUCTION_BLAST_RADIUS_NOT_BOUNDED
PRODUCTION_CREDENTIAL_SCOPE_NOT_PROVEN
PRODUCTION_KILL_SWITCH_NOT_PROVEN
PRODUCTION_OPERATION_NOT_NOMINATED
PRODUCTION_POSTCONDITION_VERIFIER_NOT_PROVEN
PRODUCTION_RECOVERY_WINDOW_NOT_PROVEN
PRODUCTION_ROLLBACK_NOT_PROVEN
PRODUCTION_TARGET_NOT_NOMINATED
PRODUCTION_TARGET_PRECONDITION_NOT_BOUND
TRUST_DECISION_BINDING_NOT_PROVEN
```

Therefore:

```text
status = BLOCKED
next_step = NOMINATE_PRODUCTION_TARGET_AND_COMPLETE_SAFETY_EVIDENCE
production_execution_authorized = false
```

No production provider mutation is attempted in PEB-4A.

## Contract implementation

Pure review/verification logic:

```text
src/review_system/trust_execution_production_authorization.py
```

Schema:

```text
schemas/production-execution-authorization-review.schema.json
src/review_system/assets/schemas/production-execution-authorization-review.schema.json
```

Tests:

```text
tests/test_trust_execution_production_authorization.py
```

The verifier rejects, among other things:

- claiming production execution authority during PEB-4A;
- claiming a production effect authorization during PEB-4A;
- incomplete target / operation / Trust bindings;
- missing credential, rollback, postcondition, blast-radius, kill-switch, or recovery evidence;
- forged blocker projections;
- forged request hashes;
- forged report hashes.

A synthetic fully evidenced request may reach:

```text
PRODUCTION_EFFECT_AUTHORIZATION_REQUEST_READY
```

but still remains:

```text
production_execution_authorized = false
effect_authorization.authorized = false
```

Its only next step is:

```text
PEB4B_EXPLICIT_ONE_SHOT_EFFECT_AUTHORIZATION_REQUIRED
```

## Current ceiling

```text
PEB-4A = BLOCKED / REVIEW CONTRACT READY
PRODUCTION_EXECUTION_AUTHORITY = NONE
AUTOMATION_AUTHORIZED = false
PILOT_AUTHORIZED = false
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 = UNCHANGED
existing R4 authority = UNCHANGED
```

The next work is target nomination and production-specific evidence collection. A real production mutation remains prohibited until an exact, hashed effect request reaches PEB-4B and receives explicit one-shot authorization.
