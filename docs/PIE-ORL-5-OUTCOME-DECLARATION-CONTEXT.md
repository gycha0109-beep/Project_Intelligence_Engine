# PIE ORL-5 — Outcome Declaration Context

## Status

```text
Program: PIE Operational Review Loop v1
Stage: ORL-5 Outcome Declaration Context
AUTO stage: NONE
Contract: PIE_OPERATIONAL_OUTCOME_CONTEXT_V1
Authority: context projection only
```

ORL-5 prepares the exact source bindings needed by the existing AUTO-3A explicit Outcome declaration contract after ORL-4 has recorded a governed human decision.

It does not declare an Outcome, choose an Outcome authority, choose a verdict, record an Outcome, or grant merge/deploy/production-effect authority.

## Source chain

```text
ORL-4 action artifact
+ governed campaign workspace
+ exact assessment / HUMAN_DECISION event
+ exact review packet / Review Brief / optional ORL-2 binding
+ current GitHub PR observation
→ PIE_OPERATIONAL_OUTCOME_CONTEXT_V1
```

The ORL-4 action is replayed against its bundled governed workspace. The current GitHub repository, PR number, base SHA, and head SHA must still bind the same source revision.

An assessment that already contains an `OUTCOME` event is rejected rather than producing another pre-declaration context.

## AUTO-3 reuse

ORL-5 does not introduce a second Outcome evaluator.

It projects the existing AUTO-3A declaration identity fields:

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

The existing AUTO-3 authority vocabulary remains unchanged:

```text
PRODUCTION_DEFECT
CONTROLLED_EVALUATION
INDEPENDENT_AUDIT
```

The existing verdict vocabulary remains unchanged:

```text
SAFE
UNSAFE
INCONCLUSIVE
```

`PRODUCTION_DEFECT` still cannot prove `SAFE`.

ORL-5 records only the source-field requirements for each authority type. It does not claim that any authority source exists or is valid.

## Merge and CI observations

GitHub PR state and status-check rollup are captured under `observations`.

Examples include:

```text
PR state
merged boolean
merged_at
merge_commit_sha
check name
check workflow
check status
check conclusion
```

These values are observations only.

The following implications are prohibited:

```text
merged == true          -> SAFE
all checks == SUCCESS   -> SAFE
GitHub review APPROVED  -> SAFE
```

The schema therefore requires:

```text
merge_observation_is_outcome_authority = false
ci_observation_is_outcome_authority = false
human_outcome_declared = false
automatic_outcome_inference = false
outcome_recorded = false
```

A completely green and merged PR still requires an explicit AUTO-3A human Outcome declaration backed by one of the existing source-reconcilable authority types.

## Unresolved explicit inputs

ORL-5 deliberately leaves these unresolved:

```text
actor
authority_type
verdict
authority_source
```

It also schema-constrains:

```text
selected_authority_type = null
selected_verdict = null
declaration_materialized = false
```

ORL-6 may provide an explicit user action surface that uses this context to construct the existing AUTO-3A declaration and then transport it through AUTO-3B. ORL-5 does neither.

## GitHub workflow

`.github/workflows/operational-outcome-context.yml` is a read-only `workflow_dispatch` surface.

Inputs:

```text
target_repository
pull_request_number
```

It exposes no authority type, verdict, actor, evidence, merge, or deploy input.

The workflow preserves:

```text
context.json
review-action-source/
```

in an ORL-5 evidence artifact.

## Authority ceiling

ORL-5 may observe that human review already exists, but it grants no new execution authority.

```text
human_review_recorded = true
human_outcome_declared = false
automatic_outcome_inference = false
outcome_recorded = false
automation_authorized = false
pilot_authorized = false
merge_authorized = false
deploy_authorized = false
production_effect_authorized = false
```

Factory Intelligence authority remains `NONE`.
