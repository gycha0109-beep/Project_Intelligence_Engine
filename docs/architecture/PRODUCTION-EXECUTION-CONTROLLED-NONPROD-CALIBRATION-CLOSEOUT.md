# Production Execution Boundary — Controlled Non-Production Calibration Closeout

Status: `PEB-3E CONTROLLED NON-PRODUCTION CALIBRATION PASS`

## Authority

Starting PIE main:

```text
d8144ab08fc1b944d3df058c3b8fda69009b7ad9
```

This closeout does not authorize production execution, automation, pilot operation, Stage10K promotion, Trust-model changes, or R4 changes.

## Isolated target

```text
repository = pie-peb3-lab/pie-peb3-calibration
PR = #1
HEAD = 295d73c9b263280705fe0ad66cd96d0edc5ee47c
environment = NON_PRODUCTION_CALIBRATION
```

The target contains no production code, production secret, deployment binding, automation authority, or pilot authority.

## Credential boundary

Dedicated GitHub App:

```text
app = pie-peb3-calibration-executor
app_id = 4688931
installation_id = 155856824
installation_account = pie-peb3-lab
repository_selection = selected
repository_set = [pie-peb3-lab/pie-peb3-calibration]
permissions = metadata:read + contents:write + pull_requests:write
```

The `contents:write` permission was required by GitHub's GraphQL PR-stage transition path. It remains bounded to the isolated calibration repository. The governed executor exposes only the exact PR-state transition and rollback sequence; no file, branch, merge, close, workflow, secret, or repository-settings operation is part of the execution contract.

Fresh token proof:

```text
run = 32626770084
artifact = 9489895023
digest = sha256:a549c5a4049d3e6933d6ca5b2c2a1eea94959ffe21d98cf33b9880b76b5c8479
result = PASS
```

The token was provider-issued, short-lived, repository-scoped to the single calibration repository, permission-scoped to `contents:write + pull_requests:write + metadata:read`, and independently read back through `/installation/repositories`. Token value was not persisted in evidence.

## Formal PEB-3E execution

Workflow:

```text
run = 32626852473
trigger PR = #5
trigger HEAD = 5117721f53f43c7abfcad084a4991b80d4c4f394
artifact = 9489917030
digest = sha256:0561d2d5cbc179871d42d0b4553ceceed120aa770d816609e0348033e9c19428
```

Verified sequence:

```text
OPEN / DRAFT / exact HEAD
→ MARK_READY_FOR_REVIEW
→ OPEN / READY / exact HEAD readback VERIFIED
→ CONVERT_TO_DRAFT
→ OPEN / DRAFT / exact HEAD readback VERIFIED
```

Final independent provider readback after the workflow also confirmed:

```text
state = OPEN
draft = true
merged = false
HEAD = 295d73c9b263280705fe0ad66cd96d0edc5ee47c
```

Therefore:

```text
external non-production effect = OBSERVED
postcondition verification = PASS
rollback dispatch = OBSERVED
rollback verification = PASS
final target restoration = PASS
```

## Earlier fail-closed attempt

The first formal stage-change attempt was rejected before effect because the App registration had gained `contents:write` while the organization installation had not yet approved that permission. PIE recorded this as `UPDATED_GITHUB_APP_PERMISSION_NOT_APPROVED_ON_INSTALLATION` in the preceding blocker evidence. After explicit installation approval, provider readback and a fresh token proved the updated permission boundary before the successful retry.

## Result

```text
PEB-3R = COMPLETE
PEB-3E = PASS
CONTROLLED_NON_PRODUCTION_EXECUTION_AND_ROLLBACK = VERIFIED
PRODUCTION_EXECUTION_AUTHORITY = NONE
AUTOMATION_AUTHORIZED = false
PILOT_AUTHORIZED = false
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 = UNCHANGED
existing R4 authority = UNCHANGED
```

This establishes that PIE can bind a trust decision to a narrowly isolated provider credential and exact target, observe a real non-production side effect, verify its postcondition, execute rollback, and verify restoration. It does not authorize production execution. Any production-capable stage requires a separate explicit authority decision and additional production-specific safety evidence.
