# PIE ORL-4 — Explicit Review Action

## Status

```text
Program: PIE Operational Review Loop v1
Stage: ORL-4 Explicit Review Action
AUTO stage: NONE
Contract: PIE_OPERATIONAL_REVIEW_ACTION_V1
Human review mutation: EXPLICIT ONLY
Outcome authority: NONE
Merge / deploy / production-effect authority: NONE
Factory Intelligence authority: NONE
```

ORL-4 adds the first explicit human mutation surface to the Operational Review Loop. It converts one deliberate operator action into the existing governed `HUMAN_DECISION` event path.

ORL-4 does not infer a decision from CI, Trust risk, Review Brief text, approval labels, GitHub review state, mergeability, or historical evidence.

## Human input

The GitHub `workflow_dispatch` surface asks for:

```text
target_repository
pull_request_number
decision
reason
confirmed_risk_band   # only for RECLASSIFY
```

The reviewer does not supply:

```text
assessment_id
review_packet_id
review_packet_sha256
Trust report hash
candidate hash
PR head SHA
PR base SHA
review level
```

Those values are resolved and replayed from governed evidence.

`review_level` is fixed to:

```text
REVIEWED
```

The review actor is fixed to:

```text
github.actor
```

## Canonical decisions

Only the existing Trust comparison vocabulary is accepted:

```text
APPROVE
REQUEST_CHANGES
HOLD
REJECT
RECLASSIFY
```

`NEEDS_WORK` is not an ORL decision.

`RECLASSIFY` requires an explicit confirmed risk band:

```text
R0
R1
R2
R3
R4
```

A confirmed risk band is rejected for every non-`RECLASSIFY` decision. ORL-4 never infers the confirmed band.

## Source resolution

ORL-4 first resolves the target PR from live GitHub state and requires it to remain open with exact 40-character base and head SHAs.

It then searches the PIE authority repository for non-expired AUTO-2 artifacts whose name is bound to the current repository, PR number, and current head prefix:

```text
pie-auto2-<repo>-pr-<number>-<head-prefix>-...
```

No user-entered packet identity chooses the source.

Every candidate AUTO-2 artifact must survive source replay before it is eligible.

## Exact source replay

For each candidate AUTO-2 artifact, ORL-4 verifies:

```text
AUTO-2 result contract and authority ceiling
prospective evidence-bundle manifest hashes
stabilized AUTO-2 semantic packet projection
governed Review Packet canonical representation
live repository identity
live PR number
live PR base SHA
live PR head SHA
live changed-file set
Trust assessment source reconciliation
ORL-3 Review Brief deterministic replay
```

When an ORL-2 binding is present, ORL-4 additionally re-reads the Operational Policy from the exact PR base revision and requires the following to remain identical:

```text
policy_revision
policy_blob_sha
policy_content_sha256
policy_sha256
binding_sha256
```

The PR head cannot make a modified policy authoritative for its own review.

## Packet selection

V1 is fail-closed.

```text
0 valid current packets
→ NO_CURRENT_REVIEW_PACKET

1 distinct valid packet
→ eligible

2+ distinct valid packets
→ AMBIGUOUS_REVIEW_PACKET
→ stop
```

Multiple artifact copies that replay to the same exact `review_packet_id` and `review_packet_sha256` are treated as duplicate transport copies, not competing decisions.

ORL-4 never chooses the newest packet, highest risk, or most convenient packet heuristically.

## Existing review mutation reuse

After source replay succeeds, ORL-4 calls the existing governed function:

```text
submit_review_packet(...)
```

with:

```text
review_level = REVIEWED
decision = explicit workflow input
actor = github.actor
reason_codes = [explicit reason]
confirmed_risk_band = explicit value only for RECLASSIFY
```

`submit_review_packet` remains authoritative for:

```text
live GitHub replay
duplicate exact packet rejection
packet archival
source reconciliation
record_case_review(...)
HUMAN_DECISION event creation
```

ORL-4 does not implement a second comparison registry or second review recorder.

## Repeated dispatch protection

An ORL-4 success artifact is named with the exact current target and recorded event:

```text
pie-orl4-<repo>-pr-<number>-<head-prefix>-<event-suffix>
```

Before a new review action, ORL-4 searches current-head ORL-4 artifacts. If a valid prior action already records human review for the same assessment, the new dispatch fails with:

```text
REVIEW_ALREADY_RECORDED
```

This prevents repeated workflow dispatches from replaying the immutable pre-review AUTO-2 artifact as if no decision had occurred.

## Mutation-race handling

`submit_review_packet` verifies live GitHub immediately before the governed mutation. ORL-4 then performs another live target read after the mutation.

If the target PR head or base changed during the action:

```text
STALE_SOURCE_REVISION
```

is returned and no successful ORL-4 artifact is uploaded.

The mutated campaign workspace in that failed runner is ephemeral and is not promoted as successful evidence.

## ORL-4 action artifact

A successful action creates:

```text
PIE_OPERATIONAL_REVIEW_ACTION_V1
```

and uploads an evidence capsule containing:

```text
action.json
bridge/
  result.json
  source/
  workspace/          # updated comparison registry with HUMAN_DECISION
  automation/         # original governed prospective evidence
```

The action binds:

```text
AUTO-2 deterministic bridge hash
semantic packet hash
project / repository / PR / base / head
assessment ID
review packet ID / SHA-256
ORL-3 Review Brief SHA-256
ORL-2 binding SHA-256 when present
explicit decision / reason / actor
recorded event ID / SHA-256 / timestamp
updated registry SHA-256
```

## Authority boundary

A successful ORL-4 action is the first ORL stage where:

```text
human_review_recorded = true
```

Every other execution authority remains schema-fixed:

```text
outcome_recorded = false
automation_authorized = false
pilot_authorized = false
merge_authorized = false
deploy_authorized = false
production_effect_authorized = false
```

The GitHub workflow itself has only:

```text
actions: read
contents: read
pull-requests: read
```

It has no write permission for repository contents or pull requests and contains no PR approval, merge, or push operation.

`APPROVE` is a governed PIE human decision. It is not a GitHub PR approval and is not merge authorization.

## Operational sequence after ORL-4

```text
PR
→ AUTO-1 exact candidate / impact
→ ORL-2 Operational Policy Binder when configured
→ existing AUTO-2 Trust materialization
→ ORL-3 deterministic Review Brief
→ ORL-4 explicit human Review Action
→ HUMAN_DECISION recorded
→ Outcome still NOT RECORDED
```

The next stage is ORL-5 Outcome Declaration Context. ORL-5 may prepare source-bound context for a later explicit Outcome action; it must not treat merge state, CI state, or the ORL-4 decision as Outcome authority.
