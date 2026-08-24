# AUTO-3B — Declared Outcome Transport

## Status

AUTO-3B transports a previously validated AUTO-3A declaration into the existing prospective Outcome mutation path. It does not accept a verdict as a transport-time argument and it never infers an Outcome.

```text
AUTO_OUTCOME_INFERENCE = NO
HUMAN_DECLARATION      = REQUIRED
PRIOR_REVIEW           = REVIEWED | AUDITED REQUIRED
SOURCE_RECONCILIATION  = REQUIRED
OUTCOME_RECORDING      = YES, prospective evidence only
AUTO_APPROVAL          = NO
AUTO_MERGE             = NO
AUTO_DEPLOY            = NO
AUTO_PILOT             = NO
AUTO_PRODUCTION_EFFECT = NO
```

Contract:

```text
PIE_AUTO3_DECLARED_OUTCOME_TRANSPORT_V1
```

Successful terminal state:

```text
DECLARED_OUTCOME_RECORDED_AND_RECONCILED
```

## Inputs

The transport command is:

```text
pie-trust-prospective record-declared-prospective-outcome
```

Required common inputs:

```text
--workspace
--declaration
```

Authority source paths are supplied only for the authority type already frozen in the declaration:

```text
PRODUCTION_DEFECT:
  --defect-registry
  --ledger

CONTROLLED_EVALUATION:
  --evaluation-report

INDEPENDENT_AUDIT:
  --audit-artifact
  --audit-authority-registry
```

There is deliberately no `--verdict`, `--actor`, `--assessment-id`, or `--outcome-type` override on the transport command. Those semantic choices are inherited from the signed-by-hash declaration envelope.

## Exact workspace binding

Before mutation AUTO-3B verifies that the campaign contains the declaration's exact:

```text
project_id
assessment_id
source_revision
Trust report id
Trust report SHA-256
```

The declaration must also bind a real `HUMAN_DECISION` event whose:

```text
event_id
event_sha256
assessment_id
review_level
decision
```

match exactly.

The event reason codes must contain both governed packet bindings:

```text
REVIEW_PACKET_ID:<exact packet id>
REVIEW_PACKET_SHA256:<exact packet hash>
```

The archived review packet is then reloaded through the existing governed review-packet archive verifier. `WORKFLOW_ACCEPTED` alone is never sufficient for AUTO-3B.

The declaration timestamp must not precede the bound human review event.

## Authority source binding

AUTO-3B loads the exact authority source and verifies the declaration's semantic source hash before prospective mutation.

### Production defect

```text
defect registry registry_sha256 == declared defect_registry_sha256
ledger file SHA-256              == declared ledger_sha256
```

### Controlled evaluation

```text
evaluation_id        == declared evaluation_id
report.report_sha256 == declared evaluation_report_sha256
```

### Independent audit

```text
audit_id                         == declared audit_id
artifact.artifact_sha256         == declared audit_artifact_sha256
authority_registry.registry_sha256 == declared audit_authority_registry_sha256
artifact issuer_subject          == declaration actor
artifact verdict                 == declaration verdict
```

These checks are preconditions. They do not replace the existing source reconciliation logic.

## Preflight before commit

AUTO-3B does not use `record_case_outcome()` against the authoritative campaign first.

It performs:

```text
validate declaration
→ validate campaign binding
→ validate governed human review
→ validate authority source binding
→ snapshot registry / source-manifest identity
→ copy campaign workspace to an isolated temporary directory
→ call existing record_case_outcome() in the copy
→ run exact source reconciliation in the copy
→ require RECONCILED
→ verify authoritative campaign did not drift
→ call the same record_case_outcome() on the authoritative campaign
→ reconcile again
→ require preflight/commit identity equality
```

AUTO-3B is stricter than the primitive API for `INCONCLUSIVE`: the bridge requires `RECONCILED` authority even when the lower-level primitive can represent an inconclusive event without a conclusive-source requirement.

## Successful projection

A successful transport records:

```text
declaration_id
declaration_sha256
assessment_id
source_revision
review_event_id
Outcome authority type
human-declared verdict
base registry SHA-256
base source-manifest SHA-256
Outcome event id
resulting registry SHA-256
idempotent flag
reconciliation status
authority key
transport SHA-256
```

and preserves:

```text
human_outcome_declared        = true
automatic_outcome_inference   = false
outcome_recorded              = true
automation_authorized         = false
pilot_authorized              = false
merge_authorized              = false
deploy_authorized             = false
production_effect_authorized  = false
```

## Non-authority statements

A recorded prospective Outcome is evidence for Trust calibration. It is not permission to merge, deploy, activate a pilot, execute a production action, or bypass the PEB-4 human authorization sequence.
