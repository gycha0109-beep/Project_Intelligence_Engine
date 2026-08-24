# PIE Operational Review Loop v1

## Status

```text
Program: PIE Operational Review Loop v1
Classification: project-local operational adapter layer
AUTO stage: NONE
Current implementation: ORL-1 Operational Policy Contract
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

The policy used to evaluate a PR must come from the exact PR base revision:

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

ORL-2 will bind the fetched base policy to exact provenance fields including:

```text
policy_revision
policy_blob_sha
policy_sha256
```

ORL-1 defines the semantic `policy_sha256`; GitHub base-revision/blob binding belongs to ORL-2.

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

ORL-2 must materialize existing Trust request fields only when their source provenance actually supplies the required fact. Missing facts remain missing and keep the flow at `WAITING_FOR_TRUST_INPUT`.

## Fail-closed policy validation

ORL-1 rejects:

- policy authority other than `PR_BASE_REVISION`,
- unknown Trust task classes,
- Trust readiness contract drift,
- absolute or parent-escaping path patterns,
- normalized duplicate path patterns,
- undeclared extra fields,
- review or Outcome fields inserted into the policy contract.

The normalized policy is deterministically ordered and receives a semantic SHA-256 so ORL-2 can bind the exact policy semantics used for a PR.

## Authority ceiling

ORL-1 grants none of the following:

```text
human review authority
Outcome authority
merge authority
deploy authority
production effect authority
pilot authority
automation authority
Factory Intelligence authority
cross-project promotion authority
```

The policy is an explicit project-local verification requirement contract only.

## Planned sequence

```text
ORL-1  Operational Policy Contract          IMPLEMENTED IN CURRENT PROGRAM PR
ORL-2  Operational Policy Binder            NEXT
ORL-3  Review Brief                          NOT IMPLEMENTED
ORL-4  Explicit Review Action                NOT IMPLEMENTED
ORL-5  Outcome Declaration Context           NOT IMPLEMENTED
ORL-6  Explicit Outcome Action               NOT IMPLEMENTED
ORL-7  Historical Recall                     DEFERRED FOR REAL CAMPAIGN CALIBRATION
ORL-8  Seven-repository rollout              NOT IMPLEMENTED
```

No phase in this list is named AUTO-5.
