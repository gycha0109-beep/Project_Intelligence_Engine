# AUTO-3A — Explicit Outcome Declaration Boundary

## Status

AUTO-3A defines the declaration boundary for Outcome transport. It does **not** record an Outcome and it does not infer a verdict.

```text
HUMAN_OUTCOME_DECLARATION = REQUIRED
AUTO_OUTCOME_INFERENCE    = FORBIDDEN
OUTCOME_RECORDED          = NO
AUTO_APPROVAL             = NO
AUTO_MERGE                = NO
AUTO_DEPLOY               = NO
AUTO_PILOT                = NO
AUTO_PRODUCTION_EFFECT    = NO
```

Contract:

```text
PIE_AUTO3_EXPLICIT_OUTCOME_DECLARATION_V1
```

Terminal state:

```text
EXPLICIT_OUTCOME_DECLARATION_VALIDATED
```

Next boundary:

```text
AUTO3B_VERIFY_AUTHORITY_SOURCE_AND_RECORD
```

## Purpose

The existing prospective Outcome API accepts an Outcome only when its authority can be reconciled from preserved source evidence. AUTO-3 must not replace that authority with workflow state, CI success, merge state, elapsed time, lack of incidents, model inference, or a generated summary.

AUTO-3A therefore packages only an explicit human declaration that is exact enough for a later transport layer to verify against the prospective campaign workspace before calling the existing `record_case_outcome()` implementation.

## Required exact bindings

Every declaration binds all of the following:

```text
actor
declared_at
project_id
assessment_id
source_revision
Trust report id
Trust report SHA-256
prior governed human-review event id
prior governed human-review event SHA-256
review level = REVIEWED | AUDITED
human decision
review packet id
review packet SHA-256
Outcome authority type
human-declared verdict
authority-specific source content hashes
```

A `WORKFLOW_ACCEPTED` event is not sufficient for AUTO-3. AUTO-3A deliberately requires a prior `REVIEWED` or `AUDITED` human decision even though lower-level comparison primitives can represent outcomes independently. The bridge is intentionally stricter than the primitive API.

## Supported authority types

AUTO-3A mirrors the source-reconcilable prospective Outcome authorities:

### PRODUCTION_DEFECT

Required declaration binding:

```text
defect_id
defect_registry_sha256
ledger_sha256
```

Permitted declared verdicts:

```text
UNSAFE
INCONCLUSIVE
```

`PRODUCTION_DEFECT + SAFE` is rejected before transport because the existing reconciliation contract cannot use a production defect as SAFE authority.

### CONTROLLED_EVALUATION

Required declaration binding:

```text
evaluation_id
evaluation_report_sha256
```

Permitted declared verdicts:

```text
SAFE
UNSAFE
INCONCLUSIVE
```

AUTO-3A does not claim that a declaration is supported by the evaluation. AUTO-3B must load the exact evaluation report, verify the declared content hash, bind it to the exact assessment source revision and Trust evidence, and rely on the existing reconciliation contract.

### INDEPENDENT_AUDIT

Required declaration binding:

```text
audit_id
audit_artifact_sha256
audit_authority_registry_sha256
```

Permitted declared verdicts:

```text
SAFE
UNSAFE
INCONCLUSIVE
```

Issuer identity, audit authority, assessment binding, revision binding, verdict equality, and reviewer independence remain AUTO-3B/reconciliation responsibilities.

## Deterministic identity

The declaration has a deterministic semantic identity:

```text
declaration_id = outcome-declaration-<first 32 hex of declaration payload SHA-256>
declaration_sha256 = canonical SHA-256 of the declaration payload
```

The declaration hash includes the explicit human actor, declared timestamp, assessment/review bindings, verdict, evidence references, and source content hashes. Replaying the same declaration bytes therefore preserves identity; changing any semantic field invalidates the hash.

## CLI

AUTO-3A adds the non-mutating command:

```text
pie-trust-prospective prepare-outcome-declaration
```

It prints a validated declaration only. It does not open a campaign workspace, mutate the comparison registry, add a reconciliation source, or call `record_case_outcome()`.

The existing command remains separate:

```text
pie-trust-prospective record-prospective-outcome
```

AUTO-3B will be responsible for connecting a validated declaration to that existing mutation path after exact source and prior-review verification.

## Non-authority statements

A validated AUTO-3A declaration never means any of the following:

```text
Outcome source reconciled
Outcome recorded
Trust prediction correct
change safe
change unsafe
merge approved
deploy approved
pilot authorized
production execution authorized
production effect authorized
```

AUTO-3A is a human-declaration envelope, not an Outcome authority engine.
