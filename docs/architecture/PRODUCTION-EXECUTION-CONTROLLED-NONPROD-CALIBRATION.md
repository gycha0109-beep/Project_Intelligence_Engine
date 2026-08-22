# PIE Production Execution Boundary — Controlled Non-Production Calibration

> Status: **PEB-3 BLOCKED / FAIL-CLOSED BEFORE GOVERNED DISPATCH**
>
> Authority baseline: `5b5af6fd7f54365dadf5cf233c044507bf349fdf`
>
> Production execution, automation, and pilot authority remain unavailable.

## 1. Purpose

PEB-1 and PEB-2 established the side-effect-free execution boundary contract and dry-run calibration. PEB-3 attempts to cross only the next boundary: a controlled, explicitly authorized, non-production execution with exact target binding, effect readback, and recovery evidence.

The frozen PEB-3 capability is:

```text
GITHUB_PR_MUTATION
operation = MARK_READY_FOR_REVIEW
rollback_operation = CONVERT_TO_DRAFT
```

The intended state transition is:

```text
DRAFT
→ READY
→ independent provider readback
→ DRAFT rollback
→ independent rollback readback
```

No production resource is in scope.

## 2. Starting authority

```text
main = 5b5af6fd7f54365dadf5cf233c044507bf349fdf
Trust = v1.5 / REPORT_ONLY
PEB-1 = PASS / LANDED
PEB-2 = PASS / LANDED
production_execution_authorized = false
automation_authorized = false
pilot_authorized = false
```

The user explicitly authorized continuation across the PEB-3 boundary. That authorization permits only controlled non-production calibration and does not grant production, automation, or pilot authority.

## 3. Non-authoritative transport probe

Before the final governed PR target was isolated, a reversible GitHub branch-file canary was used to confirm that the connected provider surface can produce real external effect/readback/rollback evidence.

Target:

```text
branch = calibration/peb3-controlled-nonprod-20260822
path = .pie-calibration/peb3-canary.json
starting main = 5b5af6fd7f54365dadf5cf233c044507bf349fdf
```

Precondition readback confirmed the path did not exist.

Effect receipt:

```text
write commit = 84f138682011e049acf0d8044edfd21d56c5b3e9
readback blob = 61bfd12481868726390ff13e8311901c0a3c7116
```

The provider readback reproduced the expected canary content.

Rollback receipt:

```text
rollback commit = 9a195057d33617e212e72cc0b6bcce53dd6f8966
post-rollback path readback = NOT FOUND
```

Final integrity comparison:

```text
compare(
  5b5af6fd7f54365dadf5cf233c044507bf349fdf,
  9a195057d33617e212e72cc0b6bcce53dd6f8966
)

ahead_by = 2
behind_by = 0
files = []
```

Therefore the canary produced a real non-production effect and a complete state restoration.

This probe is **not** accepted as PEB-3 authority evidence because the operation is a branch-file mutation rather than the PEB-2 frozen `GITHUB_PR_MUTATION` capability, and the connected credential was not demonstrated to be target-scoped.

## 4. Isolated governed calibration target

To avoid conflating evidence delivery with the execution target, PR #60 is the evidence PR and a separate Draft PR is the governed target.

Target PR:

```text
PR = #61
title = test(trust): PEB-3 isolated non-production target
state = OPEN / DRAFT
head = 39ba94c0b847017f1f9f8e315fdbb198c15b65b9
base = main @ 5b5af6fd7f54365dadf5cf233c044507bf349fdf
environment = NON_PRODUCTION_CALIBRATION
merge_intent = NONE
```

The target branch contains only an inert calibration marker and is not a deployment or production path.

## 5. Pre-dispatch validation

The controlled execution report freezes:

```text
contract = TRUST_CONTROLLED_NON_PRODUCTION_EXECUTION_CALIBRATION_V1
capability = GITHUB_PR_MUTATION
operation = MARK_READY_FOR_REVIEW
rollback = CONVERT_TO_DRAFT
production_execution_authorized = false
non_production_execution_authorized = true
automation_authorized = false
pilot_authorized = false
```

The following pre-dispatch checks were satisfied:

```text
EXACT_SOURCE_HEAD = PASS
EXACT_TARGET_PRECONDITION = PASS
KILL_SWITCH_CLEAR = PASS
ROLLBACK_READY = PASS
```

The remaining requirement failed:

```text
TARGET_SCOPED_CREDENTIAL = NOT PROVEN
```

The available connected GitHub mutation surface is broader than PR #61: the same connection has already been able to mutate other repository resources, including prior PR lifecycle operations and the isolated canary branch. Therefore no evidence establishes that the execution credential can mutate only the designated PEB-3 target.

The frozen contract does not permit target binding in the request to substitute for credential scoping.

## 6. Fail-closed result

Because credential scope is a pre-dispatch requirement, the formal PEB-3 operation was suppressed.

```text
PR #61 MARK_READY_FOR_REVIEW = NOT ATTEMPTED
dispatch.suppressed = true
provider effect receipt = null
postcondition verification = false
rollback dispatch = NOT ATTEMPTED
final target state = original OPEN / DRAFT preserved
```

This is intentional. Performing the PR state mutation with a broader connected credential and then arguing from successful rollback would violate the PEB-2 least-privilege contract.

The authoritative report is:

```text
evidence/trust/peb3-controlled-nonprod-20260822.json
```

Its result is:

```text
PEB-3 = BLOCKED
BLOCKER = TARGET_SCOPED_CREDENTIAL_NOT_PROVEN
NEXT_STEP = ESTABLISH_TARGET_SCOPED_NON_PRODUCTION_CREDENTIAL
```

## 7. Implemented evidence verifier

Implementation:

```text
src/review_system/trust_execution_controlled_nonprod.py
```

Schema:

```text
schemas/controlled-nonprod-execution-calibration-report.schema.json
```

Packaged schema is kept byte-identical under:

```text
src/review_system/assets/schemas/
```

Tests:

```text
tests/test_trust_execution_controlled_nonprod.py
```

The verifier enforces:

- production authority remains false,
- non-production authorization cannot imply automation or pilot authority,
- target remains a GitHub PR in a non-production calibration environment,
- capability remains exactly `GITHUB_PR_MUTATION`,
- authorization identity is present,
- any pre-dispatch blocker suppresses dispatch,
- suppressed dispatch cannot claim provider effect evidence,
- successful future dispatch requires independent readback and rollback restoration,
- target/head binding cannot drift,
- blocker/status/next-step projections are deterministic,
- evidence and report digests are tamper-evident.

## 8. Current ceiling

```text
PRODUCTION_EXECUTION_AUTHORITY = NONE
PRODUCTION_MUTATION = NOT AUTHORIZED
AUTOMATION_AUTHORITY = NONE
PILOT_AUTHORITY = NONE
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 / existing R4 authority = UNCHANGED
```

PEB-3 has not failed because the provider cannot mutate or rollback. The non-authoritative canary demonstrated those mechanics. It is blocked because the formal governed boundary cannot prove a credential whose authority is constrained to the designated non-production target.

## 9. Next blocker-remediation boundary

```text
PEB-3R
TARGET-SCOPED NON-PRODUCTION CREDENTIAL / ADAPTER BINDING
```

PEB-3R must establish, before any formal dispatch:

1. a credential or provider identity whose effective mutation authority is bounded to the designated non-production target or an equivalently isolated non-production resource boundary,
2. replayable evidence of that scope,
3. an adapter that cannot escape that scope,
4. exact binding between the credential scope, request target, provider target, and rollback target.

Only after those conditions are independently verified may the Draft→Ready→Draft controlled mutation be attempted.
