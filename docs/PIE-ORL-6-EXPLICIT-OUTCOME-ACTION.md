# PIE ORL-6 — Explicit Outcome Action

## Status

```text
Program: PIE Operational Review Loop v1
Stage: ORL-6 Explicit Outcome Action
AUTO stage: NONE
Adapter contract: PIE_OPERATIONAL_OUTCOME_ACTION_V1
Outcome authority: existing AUTO-3A / AUTO-3B only
Factory Intelligence authority: NONE
```

ORL-6 is the explicit human action surface that consumes an ORL-5 Outcome Declaration Context and invokes the already-governed AUTO-3 contracts.

It does not introduce a new Outcome evaluator, a new verdict vocabulary, or a second Outcome registry.

## Authority chain

```text
ORL-5 source-bound context
+ explicit human actor
+ explicit authority type
+ explicit verdict
+ exact authority-source artifact file(s)
        ↓
existing AUTO-3A build_outcome_declaration(...)
        ↓
existing AUTO-3B transport_declared_outcome(...)
        ↓
existing governed OUTCOME event
        ↓
existing source reconciliation
        ↓
PIE_OPERATIONAL_OUTCOME_ACTION_V1 receipt
```

The ORL-6 receipt is a projection of the existing AUTO-3A declaration and AUTO-3B transport result. It is not an independent Outcome authority.

## Explicit Outcome semantics

The human action must select one existing AUTO-3 authority type:

```text
PRODUCTION_DEFECT
CONTROLLED_EVALUATION
INDEPENDENT_AUDIT
```

and one existing verdict:

```text
SAFE
UNSAFE
INCONCLUSIVE
```

The existing rule remains unchanged:

```text
PRODUCTION_DEFECT + SAFE = invalid
```

ORL-6 does not infer the authority type or verdict from merge state, CI, GitHub review state, filenames, workflow success, or artifact metadata.

## Authority-source files

The explicit action identifies physical evidence files. ORL-6 loads those files through the existing PIE source contracts and derives the semantic IDs and hashes required by AUTO-3A.

```text
PRODUCTION_DEFECT
  primary source   = defect registry
  secondary source = ledger
  explicit input   = defect_id

CONTROLLED_EVALUATION
  primary source   = evaluation report

INDEPENDENT_AUDIT
  primary source   = audit artifact
  secondary source = audit authority registry
```

The operator does not manually copy:

```text
assessment_id
trust_report_sha256
review_event_sha256
review_packet_sha256
evaluation_report_sha256
audit_artifact_sha256
defect_registry_sha256
```

Assessment and review identities come from the exact ORL-5 context. Authority-source identities come from parsing the exact supplied source files.

This is deterministic source transport, not Outcome inference.

## Evidence references

ORL-6 preserves optional explicit evidence references and also adds the exact semantic identity of the explicitly selected authority source where the existing reconciliation contract requires it.

For example, a controlled evaluation contributes its `evaluation_id` and `report_sha256` to the AUTO-3 declaration evidence references. An independent audit contributes its `audit_id` and artifact identity.

These references identify the selected evidence. They do not make a verdict valid by themselves. AUTO-3B still executes the existing source reconciliation checks.

## Existing AUTO-3A reuse

The ORL-5 context supplies the exact existing AUTO-3A fields:

```text
project_id
assessment_id
source_revision
trust_report_id
trust_report_sha256
review_event_id
review_event_sha256
review_level
decision
review_packet_id
review_packet_sha256
```

ORL-6 supplies only the unresolved explicit fields and source-derived bindings, then calls:

```text
build_outcome_declaration(...)
```

A valid declaration therefore remains:

```text
PIE_AUTO3_EXPLICIT_OUTCOME_DECLARATION_V1
human_outcome_declared = true
outcome_recorded = false
```

until AUTO-3B succeeds.

## Existing AUTO-3B reuse

ORL-6 then calls:

```text
transport_declared_outcome(...)
```

against a preserved copy of the governed ORL-4 campaign workspace.

AUTO-3B remains responsible for:

- exact assessment binding,
- exact prior HUMAN_DECISION binding,
- review-packet archive binding,
- authority-source semantic verification,
- authority-specific reconciliation,
- preflight on a copied workspace,
- preflight/commit divergence rejection,
- recording the governed `OUTCOME` event.

ORL-6 accepts completion only when AUTO-3B returns:

```text
reconciliation_status = RECONCILED
outcome_recorded = true
automatic_outcome_inference = false
idempotent = false
```

An idempotent transport result cannot be promoted into a new ORL-6 action receipt.

## Duplicate protection

Before mutation, ORL-6 searches current-head ORL-6 artifacts.

If a valid prior action already binds the same:

```text
repository
PR
head SHA
assessment_id
ORL-4 review_action_sha256
```

ORL-6 fails with `OUTCOME_ALREADY_RECORDED`.

A malformed prior ORL-6 artifact also fails closed rather than being ignored as if no prior action existed.

## ORL-5 context freshness

ORL-6 discovers current-head ORL-5 artifacts and replays each candidate against:

- the embedded ORL-4 review-action source,
- the governed workspace,
- the exact assessment and HUMAN_DECISION,
- the current GitHub repository / PR / base / head.

Multiple ORL-5 snapshots for the same exact review action are allowed because ORL-5 observations may be refreshed without creating a new authority decision. Distinct valid review actions for the same current PR are ambiguous and fail closed.

## GitHub workflow

`.github/workflows/operational-outcome-action.yml` is a `workflow_dispatch` surface in the PIE authority repository.

Human semantic inputs are:

```text
target_repository
pull_request_number
authority_type
verdict
```

The actor is fixed to:

```text
github.actor
```

The workflow also requires an exact authority-source locator:

```text
source_run_id
source_artifact_name
primary_source_path
secondary_source_path when required
```

V1 downloads that exact artifact from the PIE authority repository. The artifact's workflow success status is not Outcome authority. The downloaded file must still pass the existing authority-specific source contract and AUTO-3 reconciliation.

Source paths must be relative, non-escaping, regular files without symlink components.

The workflow permissions are read-only:

```text
actions: read
checks: read
contents: read
pull-requests: read
```

It has no GitHub PR approval, merge, push, deployment, or target-repository write operation.

## Preserved evidence

A successful ORL-6 artifact preserves:

```text
action.json
context.json
declaration.json
transport.json
review-action-source/
authority-source/
```

`action.json` binds the ORL-5 context, explicit human semantics, authority-source identities, AUTO-3A declaration, AUTO-3B transport, and resulting governed Outcome event with a deterministic `action_sha256`.

## Authority ceiling

A successful ORL-6 action may establish only the explicitly declared, source-reconciled PIE Outcome:

```text
human_review_recorded = true
human_outcome_declared = true
automatic_outcome_inference = false
outcome_recorded = true
```

It still grants none of:

```text
automation authority
pilot authority
merge authority
deploy authority
production-effect authority
Factory Intelligence authority
cross-project promotion authority
```

A `SAFE` Outcome is therefore a governed technical evidence result. It is not permission to merge, deploy, or affect production.

## Next stage boundary

ORL-7 Historical Recall remains deferred until enough real ORL campaign evidence exists for calibration.

ORL-6 does not implement historical matching or AUTO-4 campaign projection. No ORL-7 or ORL-8 behavior is included in this stage.
