# AUTO-4C — Governed Event Projection

## Status

AUTO-4C projects already-governed human review decisions and explicit declaration-bound Outcomes from one project-local prospective campaign lineage into another workspace representing the same exact registry lineage.

It does not infer review, infer Outcome, re-author events, or merge unrelated project histories.

Contract:

```text
PIE_AUTO4_GOVERNED_EVENT_PROJECTION_V1
```

CLI:

```text
pie-trust-campaign-events \
  --workspace <destination-campaign> \
  --source-workspace <governed-source-campaign> \
  --declaration <auto3a-outcome-declaration.json> \
  --output auto4c-projection.json
```

Repeat `--declaration` once for every source Outcome event.

## Scope

AUTO-4B projects assessment evidence only.

AUTO-4C starts only after the destination already contains the exact corresponding assessment evidence.

The intended sequence is:

```text
AUTO-4B assessment projection
→ governed REVIEWED / AUDITED decision exists in a source campaign
→ AUTO-4C exact human-decision replay
→ explicit AUTO-3A Outcome declaration exists for any Outcome
→ AUTO-4C delegates Outcome transport to AUTO-3B
→ campaign_progress()
```

AUTO-4C does not create missing assessments.

If a source event references an assessment that is absent from the destination, projection fails closed as `ASSESSMENT_REQUIRED`.

## Registry lineage is part of event authority

Trust comparison event identity is not portable metadata.

The event identity chain includes:

```text
registry_id
sequence
event_type
assessment_id
occurred_at
actor
payload
previous_event_sha256
```

Therefore copying a source event row into a different registry lineage would create a different authority history.

AUTO-4C requires:

```text
source.registry_id == destination.registry_id
```

and every event already present in the destination must be an exact prefix of the source event chain.

Any divergence fails as:

```text
LINEAGE_MISMATCH
```

AUTO-4C never rewrites `event_id`, `event_sha256`, sequence, previous-event hash, actor, timestamp, or payload to make a foreign history fit.

## Governed human decision projection

AUTO-4C accepts only source `HUMAN_DECISION` events whose review level is:

```text
REVIEWED
AUDITED
```

`WORKFLOW_ACCEPTED` is not prospective human safety evidence and is not projected by this stage.

Every accepted source review event must bind exactly one governed packet through reserved reason codes:

```text
REVIEW_PACKET_ID:<prospective-review-packet-id>
REVIEW_PACKET_SHA256:<packet-sha256>
```

The source packet archive is verified through the existing governed review-packet loader.

The archive is copied exactly into the destination only when it is absent. If an archive already exists, the complete file-tree digest must match the source archive.

The human decision is not copied into the registry. AUTO-4C first asks the existing Trust comparison model to reproduce the exact candidate event and then calls:

```text
record_case_review()
```

with the exact governed packet binding, actor, timestamp, review level, decision, confirmed risk band, and non-reserved reason codes.

The resulting destination event must equal the source event exactly, including:

```text
event_id
event_sha256
sequence
previous_event_sha256
payload
```

Otherwise projection fails closed.

Thus AUTO-4C acquires already-authorized review evidence but does not authorize a review by itself.

## Explicit Outcome declaration requirement

AUTO-4C never infers an Outcome from:

```text
CI success
merge status
deploy status
human APPROVE decision
absence of defects
controlled evaluation presence
review packet contents
```

Every source `OUTCOME` event requires one explicit, valid AUTO-3A declaration.

If even one source Outcome lacks a declaration, the entire projection fails before destination mutation as:

```text
DECLARATION_REQUIRED
```

The declaration must identify exactly one source Outcome by the bound assessment, actor, declared timestamp, authority type, verdict, and defect binding where applicable.

Supported Outcome authorities remain the existing source-reconcilable set:

```text
PRODUCTION_DEFECT
CONTROLLED_EVALUATION
INDEPENDENT_AUDIT
```

## Existing AUTO-3 authority is reused

AUTO-4C does not implement a second Outcome authority model.

For every declared source Outcome it resolves the exact source authority files from the source campaign reconciliation manifest and delegates to:

```text
transport_declared_outcome()
```

The declaration is first replayed against a temporary copy of the source campaign.

Because the source already contains the governed Outcome, the AUTO-3B transport must return:

```text
same source event_id
idempotent = true
automatic_outcome_inference = false
```

This verifies that the declaration genuinely describes the source Outcome that AUTO-4C intends to project.

The same AUTO-3B transport is then used against destination preflight and destination commit workspaces.

The produced event must exactly equal the governed source event.

AUTO-4C does not call `record_case_outcome()` directly to bypass the declaration boundary.

## Source reconciliation

Both source and destination campaigns must already satisfy existing prospective source reconciliation before AUTO-4C starts.

For source Outcomes, AUTO-4C resolves the authority sources already recorded by `reconciliation-sources.json`:

```text
PRODUCTION_DEFECT
  defect_registry
  ledger

CONTROLLED_EVALUATION
  evaluation_report

INDEPENDENT_AUDIT
  audit_artifact
  audit_authority_registry
```

Paths must remain inside the source campaign workspace and must not contain symlinks.

Outcome authority remains verified by AUTO-3B and the existing reconciliation machinery.

## Preflight before authoritative mutation

AUTO-4C performs a complete isolated preflight:

```text
copy destination workspace
→ replay every governed source event in sequence
→ verify source reconciliation
→ calculate resulting registry identity
→ calculate source-manifest identity
→ calculate campaign evidence snapshot
```

Before authoritative replay, AUTO-4C re-reads destination registry and reconciliation manifest and requires the exact preflight base identities to remain unchanged.

This detects concurrent mutation.

AUTO-4C then repeats the exact projection on the authoritative destination.

The committed result must equal the preflight result for:

```text
projected/idempotent event counts
registry_sha256
reconciliation manifest SHA-256
campaign evidence_snapshot_sha256
```

Any difference fails as `PROJECTION_COMMIT_MISMATCH`.

## Idempotency

If the destination already contains an exact prefix of the governed source event chain:

- existing human decisions are treated as idempotent only when the exact governed review archive is also present and identical;
- declaration-bound Outcomes are replayed through AUTO-3B and must return the exact existing event identity idempotently.

A fully repeated AUTO-4C invocation therefore performs no new event mutation.

## Authority ceiling

AUTO-4C reports evidence collection mutation only.

It never grants operational authority.

Every successful report preserves:

```text
automatic_human_review_inference = false
automatic_outcome_inference      = false
automation_authorized            = false
pilot_authorized                 = false
merge_authorized                 = false
deploy_authorized                = false
production_effect_authorized     = false
```

`human_review_projected=true` means an already-governed human decision was reproduced through the governed review path.

`outcome_projected=true` means an already-declared Outcome was transported through AUTO-3B.

Neither field means that AUTO-4C itself created authority.

## Factory Intelligence boundary

AUTO-4C remains entirely inside one project-local PIE campaign lineage.

It does not create or promote:

```text
cross-project event streams
shared client evidence
factory rules
blueprint knowledge
cross-project patterns
pilot authorization
production authority
```

Cross-project aggregation/generalization remains a separate Factory Intelligence concern and must consume only later explicitly eligible project-local evidence.

## Terminal result

A successful projection reports:

```text
status = GOVERNED_EVENTS_PROJECTED
stage  = AUTO-4C
```

along with governed event counts, campaign counters, reconciliation state, final registry/source-manifest identities, and a deterministic projection hash.

The next action remains project-local evidence collection and governance, not automatic pilot activation.
