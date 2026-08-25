# PIE Operational Review Loop v1

## Status

```text
Program: PIE Operational Review Loop v1
Classification: project-local operational adapter layer
AUTO stage: NONE
Current implementation:
- ORL-1 Operational Policy Contract
- ORL-2 Operational Policy Binder
- ORL-3 Review Brief
- ORL-4 Explicit Review Action
Factory Intelligence authority: NONE
```

This program connects the completed PIE Automation V1 contracts to an operational development workflow without creating a new AUTO stage and without expanding PIE into Factory Intelligence.

The Operational Review Loop remains project-local. It does not create cross-project shared knowledge, a Factory registry, a shared database, merge authority, deploy authority, production-effect authority, or automatic human judgment.

## ORL-1 — Operational Policy Contract

Project repositories may declare a policy at:

```text
.review/operational/policy.yml
```

The V1 contract is:

```text
PIE_OPERATIONAL_POLICY_V1
```

A policy declares what verification requirements the project owner wants associated with a deterministically matched operational class.

It is not a review decision, Trust decision, Outcome, merge approval, deploy approval, or production authorization.

### Example

```yaml
schema_version: "1.0"
contract_version: PIE_OPERATIONAL_POLICY_V1
project_id: thought-drawer
policy_authority: PR_BASE_REVISION

operational_classes:
  reminder-runtime:
    paths:
      - "app/src/main/**/*Reminder*"
      - "app/src/main/**/*Worker*"

    trust_task_class: routine_code

    required_scenarios:
      - process-restart
      - duplicate-scheduling
      - timezone-change
      - reboot-recovery

    required_evidence:
      - android-ci

    readiness_policy:
      policy_id: thought-drawer-operational
      policy_version: 1.0.0
      min_ledger_runs: 1
      min_ledger_decisions: 1
      min_defects: 1
      min_closed_defects: 0
      min_reground_observations: 1
      min_reground_coverage: 1.0
      min_reground_precision: 1.0
      min_reground_recall: 1.0
      max_reground_false_positive_rate: 0.0
      require_active_policy: true
      require_pass_evaluation: true
      require_holdout: true
      require_repeatability: true
      require_zero_protected_negative_regressions: true
```

## Operational class is not Trust task class

Project-specific operational classes such as:

```text
reminder-runtime
android-ui
recommendation-ranking
```

are not added to the existing Trust vocabulary.

Each operational class must explicitly map to one existing `trust-request.schema.json` task class through:

```text
trust_task_class
```

PIE does not infer that mapping.

The ORL-1 loader verifies that the Operational Policy schema uses the exact current Trust `task_class` vocabulary. Contract drift fails closed.

## Readiness policy reuse

The `readiness_policy` structure is intentionally the existing Trust request readiness contract rather than a second readiness model.

The ORL-1 loader compares the Operational Policy readiness schema with `trust-request.schema.json`. If the two contracts drift, policy loading fails rather than silently creating a second Trust semantics implementation.

## Base-revision authority

The policy used to evaluate a PR comes from the exact PR base revision:

```text
PR base SHA = A
PR head SHA = B

policy authority for B = policy from A
```

Therefore the contract requires:

```text
policy_authority: PR_BASE_REVISION
```

A PR that edits `.review/operational/policy.yml` cannot weaken the policy used to evaluate itself. The changed policy becomes eligible only after it lands and is part of a later PR base revision.

ORL-2 records:

```text
policy_revision
policy_blob_sha
policy_content_sha256
policy_sha256
```

`policy_revision` is the exact Git base revision, `policy_blob_sha` is the exact Git blob identity returned for that base revision, `policy_content_sha256` binds the fetched bytes, and `policy_sha256` binds the normalized operational semantics.

## Evidence requirement is not evidence completion

`required_evidence` contains requirement identifiers only.

For example:

```text
required_evidence:
- android-ci
```

means that the policy requires that evidence. It does not prove:

```text
completed_scenarios.process-restart = true
rollback_evidence = true
replay_evidence = true
Outcome = SAFE
```

CI status metadata is not automatically treated as independently verified execution evidence.

Missing facts remain missing and keep the flow at `WAITING_FOR_TRUST_INPUT`.

## ORL-2 — Operational Policy Binder

ORL-2 consumes the existing exact-head GitHub prospective candidate and the ORL-1 policy from the exact PR base revision.

Conceptually:

```text
AUTO-1 exact PR candidate
        +
exact base-revision Operational Policy
        +
optional explicit ORL Trust Facts
        ↓
deterministic policy match
        ↓
NO_POLICY_MATCH
UNIQUE_POLICY_MATCH
AMBIGUOUS_POLICY_MATCH
        ↓
MISSING_TRUST_FIELDS
or
TRUST_REQUEST_MATERIALIZED
```

ORL-2 is not a second Trust evaluator.

When a request can be materialized, the output is the existing `trust-request.schema.json` contract and the existing prospective materialization / review-packet path remains authoritative.

### Matching behavior

V1 intentionally does not union multiple operational classes.

```text
0 matching classes
→ NO_POLICY_MATCH

1 matching class
→ UNIQUE_POLICY_MATCH

2+ matching classes
→ AMBIGUOUS_POLICY_MATCH
→ fail closed
```

An ambiguous match is not resolved by specificity heuristics, AI, priority guessing, or path-order selection.

### Explicit Trust Facts

The optional facts contract is:

```text
PIE_OPERATIONAL_TRUST_FACTS_V1
```

Example:

```yaml
schema_version: "1.0"
contract_version: PIE_OPERATIONAL_TRUST_FACTS_V1
project_id: thought-drawer
source_revision: git:<EXACT_PR_HEAD>

completed_scenarios:
  - process-restart
  - duplicate-scheduling

verified_evidence:
  - android-ci

rollback_evidence: false
replay_evidence: false

provided_by: github-user
provided_at: 2026-08-24T09:00:00Z
```

These facts are explicit operator input.

They are not:

```text
human review
Outcome
merge authority
deploy authority
production-effect authority
```

A false boolean is transported only when explicitly supplied. Absence is not converted into false.

`required_evidence` IDs cannot silently disappear during binding. If the selected Operational Policy requires an evidence ID that is not present in the explicit facts, ORL-2 remains at `MISSING_TRUST_FIELDS` and does not create a Trust request.

### Existing Trust contract reuse

When all required binder inputs exist, ORL-2 fills only fields whose provenance is explicit:

| Trust request field | Source |
|---|---|
| `task_id` | AUTO-1 candidate |
| `source_revision` | exact PR HEAD |
| `changed_files` | AUTO-1 candidate |
| `repository_match` | AUTO-1 exact verification |
| `head_match` | AUTO-1 exact verification |
| `task_class` | explicit ORL-1 mapping |
| `required_scenarios` | ORL-1 policy |
| `readiness_policy` | ORL-1 policy |
| `completed_scenarios` | explicit ORL Trust Facts |
| `rollback_evidence` | explicit ORL Trust Facts |
| `replay_evidence` | explicit ORL Trust Facts |

The resulting request is validated by the existing Trust request loader before it may be passed to AUTO-2 materialization.

### `run-github-pr` adapter

The existing orchestration command accepts two mutually exclusive Trust-source modes:

```text
--request <existing explicit Trust request>
```

or:

```text
--operational-policy .review/operational/policy.yml
[--operational-trust-facts <facts file>]
```

If the binder cannot materialize a request:

```text
status = WAITING_FOR_TRUST_INPUT
auto_trust_assessment = false
auto_packet_prepare = false
```

If the binder materializes a valid existing Trust request and a campaign workspace is supplied:

```text
generated existing Trust request
→ existing materialize_github_prospective_capture
→ existing Trust assessment
→ existing prepare_review_packet
→ READY_FOR_HUMAN_REVIEW
```

No parallel Trust evaluator or review-recording path is introduced.

### Operational evidence capsule

When ORL-2 is enabled, the prospective evidence bundle may include:

```text
operational/
  binding.json
  base-policy.yml
  trust-facts.yml
```

`binding.json` is a projection and carries a deterministic `binding_sha256`.

It remains non-authoritative for human review, Outcome, merge, deploy, or production effect.

### Replay binding

When ORL-2 stops before Trust request materialization, the existing deterministic prospective result also binds:

```text
operational_binding_status
operational_match_status
operational_binding_sha256
operational_policy_sha256
operational_missing_inputs
```

Therefore policy matching changes cannot silently alter an otherwise same-input replay result.

## ORL-1 fail-closed policy validation

ORL-1 rejects:

- policy authority other than `PR_BASE_REVISION`,
- unknown Trust task classes,
- Trust readiness contract drift,
- absolute or parent-escaping path patterns,
- normalized duplicate path patterns,
- undeclared extra fields,
- review or Outcome fields inserted into the policy contract.

The normalized policy is deterministically ordered and receives a semantic SHA-256.

## ORL-2 fail-closed conditions

ORL-2 rejects or stops on:

- candidate exact-head blockers,
- unresolved or non-exact PR base revision,
- GitHub base-policy readback failure,
- base policy project mismatch,
- missing base policy,
- no operational-class match,
- ambiguous operational-class match,
- stale Trust Facts source revision,
- missing required evidence IDs,
- invalid materialized Trust request.

These conditions do not create review authority or an Outcome.

## ORL-4 — Explicit Review Action

ORL-4 records one deliberate human decision through the existing governed prospective review mutation path.

The high-level action is:

```text
workflow_dispatch
→ target repository + PR + decision + reason
→ live PR head/base resolution
→ current-head AUTO-2 artifact discovery
→ governed packet / ORL-3 brief / optional ORL-2 policy replay
→ existing submit_review_packet(...)
→ existing HUMAN_DECISION event
→ ORL-4 action artifact
```

The action surface does not ask the reviewer to copy an assessment ID, packet hash, candidate hash, or PR revision. Those identities are resolved from governed evidence and checked against live GitHub state.

The canonical decisions are:

```text
APPROVE
REQUEST_CHANGES
HOLD
REJECT
RECLASSIFY
```

`review_level` is fixed to `REVIEWED`, and the workflow actor is `github.actor`.

`RECLASSIFY` requires an explicit `R0`-`R4` confirmed risk band. No other decision may carry a confirmed risk band.

A successful ORL-4 result sets:

```text
human_review_recorded = true
```

but keeps:

```text
outcome_recorded = false
automation_authorized = false
pilot_authorized = false
merge_authorized = false
deploy_authorized = false
production_effect_authorized = false
```

`APPROVE` is therefore a PIE human decision only. It is not a GitHub PR approval and it does not authorize merge or deployment.

ORL-4 fails closed on missing current packets, multiple distinct valid packets, replay mismatch, stale base-policy binding, repeated review of the same current assessment, or a PR head/base move during submission.

Detailed contract and evidence behavior are documented in `docs/PIE-ORL-4-EXPLICIT-REVIEW-ACTION.md`.

## Authority ceiling

ORL-1 through ORL-3 do not record human judgment. ORL-4 may record only an explicit, human-dispatched `HUMAN_DECISION` after exact source replay.

ORL-1 through ORL-4 grant none of the following:

```text
automatic human decision authority
Outcome authority
merge authority
deploy authority
production effect authority
pilot authority
automation authority
Factory Intelligence authority
cross-project promotion authority
```

ORL-2 automates deterministic policy binding and safe request transport. ORL-3 adds a deterministic, source-bound review projection. ORL-4 adds only explicit human-review recording through the pre-existing governed mutation contract.

## Planned sequence

```text
ORL-1  Operational Policy Contract          IMPLEMENTED
ORL-2  Operational Policy Binder            IMPLEMENTED
ORL-3  Review Brief                          IMPLEMENTED
ORL-4  Explicit Review Action                IMPLEMENTED
ORL-5  Outcome Declaration Context           NEXT
ORL-6  Explicit Outcome Action               NOT IMPLEMENTED
ORL-7  Historical Recall                     DEFERRED FOR REAL CAMPAIGN CALIBRATION
ORL-8  Seven-repository rollout              NOT IMPLEMENTED
```

No phase in this list is named AUTO-5.
