# PIE Stage 10C — Source Replay & Outcome Reconciliation

## 1. Purpose

Stage 10C verifies that Stage 10B Trust assessments and Outcome events still resolve to the original evidence authorities they claim to represent. It is an evidence-verification stage, not an activation stage.

The stage is fixed to:

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
```

A successful reconciliation does not authorize R0 auto-pass, GitHub approval, merge, labels, comments, branch mutation, R1 conditional approval, or any higher-band automation.

## 2. Authoritative base

Stage 10C is stacked on PR #20 exact head:

```text
82e5af48c1c3beb8ad4277a715ebb134330c5799
```

The base keeps the Stage 10D contract unchanged. Stage 10C produces a separate reconciliation artifact; Stage 10D threshold denominators are not modified in this stage.

## 3. Problem statement

Stage 10B protects registry structure, assessment hashes, event hashes, event order, and comparison projections. It intentionally does not prove that Outcome references resolve to an external authority.

Therefore none of the following is sufficient evidence by itself:

```text
non-empty defect_id
non-empty evidence_refs
actor name containing auditor
a self-declared SAFE/UNSAFE verdict
an outer registry hash that still validates
```

Stage 10C must replay the assessment Trust source and reconcile conclusive Outcomes against real domain authorities.

## 4. Existing authority constraints discovered during design

### 4.1 Trust report

Stage 10A already provides the strongest replay primitive required by 10C:

```python
verify_trust_report_sources(...)
```

It re-runs `assess_trust(...)` from the original request/profile/evidence inputs using the report `generated_at`, then compares `snapshot_sha256`, `report_id`, and `report_sha256`.

A Stage 10B assessment is not fully reconciled unless both of the following succeed:

1. Trust report semantic verification.
2. Original Trust source replay.

Exact report ID/hash matching without source replay is intentionally insufficient for `RECONCILED`.

### 4.2 Defect Registry

The standalone Defect Registry proves defect identity and lifecycle structure, but its `first_seen_run_id` / `last_seen_run_id` strings do not independently prove that a run exists or belongs to the assessment revision.

The Evidence Ledger is the stronger relational authority because it stores:

```text
runs.project_id
runs.source_revision
registry_sources.registry_sha256
defects.first_seen_run_id
defects.last_seen_run_id
finding_defects
defect_artifacts
```

Therefore a `PRODUCTION_DEFECT` conclusive Outcome requires the Defect Registry and an Evidence Ledger that imported that exact registry hash.

### 4.3 Evaluation report

The Evaluation report is semantically self-verifying and includes case `source_revision`, holdout split, repeatability, protected-negative regressions, and gate decision.

It does not contain a Stage 10 project ID. Project binding is therefore inherited only when the Evaluation authority matches the exact Evaluation ID/hash captured inside the reconciled Stage 10A Trust report policy evidence.

### 4.4 Unsupported Outcome authorities

The repository currently has no standalone cryptographically attributable authority for:

```text
INDEPENDENT_AUDIT
REGRESSION
SECURITY_INCIDENT
FALSE_POSITIVE_REVIEW
```

Stage 10C does not invent one. These Outcome types remain unreconciled unless a future stage adds a versioned source authority contract.

## 5. Additive source-manifest contract

Stage 10C adds a `trust-reconciliation-sources` manifest. It is an execution input, not a new source of truth.

All referenced paths are relative to the manifest directory and must reject:

- absolute paths,
- `..` traversal,
- symlink components,
- missing/non-regular files.

Conceptual shape:

```json
{
  "schema_version": "1.0",
  "project_id": "demo",
  "assessment_sources": [
    {
      "assessment_id": "assessment-...",
      "trust_report": "trust/report.json",
      "request": "trust/request.json",
      "profile": "trust/profile.yml",
      "ledger": "evidence.sqlite",
      "policy_registry": "policy-registry.json",
      "evaluation_report": "evaluation.json",
      "reground_report": "reground.json",
      "reground_observations": "reground-observations.json"
    }
  ],
  "outcome_sources": [
    {
      "event_id": "event-...",
      "authority_type": "PRODUCTION_DEFECT",
      "defect_registry": "defects.json",
      "ledger": "evidence.sqlite"
    },
    {
      "event_id": "event-...",
      "authority_type": "CONTROLLED_EVALUATION",
      "evaluation_report": "evaluation.json"
    }
  ]
}
```

Optional Trust source fields must exactly reflect what was used to produce the Trust report. Omitting an evidence source that was originally present causes source replay mismatch and therefore fails closed.

Manifest identity is canonical JSON SHA-256. Absolute local paths are never copied into the reconciliation report.

## 6. Assessment reconciliation

Each Stage 10B assessment is reconciled against exactly one manifest assessment source entry.

Required checks:

1. Registry assessment exists and is structurally valid.
2. Trust report loads and passes Stage 10A semantic verification.
3. `trust_report_id` equals the assessment reference.
4. `trust_report_sha256` equals the assessment reference.
5. Trust report `project_id` equals the comparison registry project.
6. Trust report request `task_id` equals the assessment task.
7. Trust report request `source_revision` equals the assessment source revision.
8. Trust report risk effective band equals `predicted_risk_band`.
9. Trust report advisory hard gates equal `triggered_hard_gates`.
10. Trust report readiness status equals `readiness_status`.
11. `verify_trust_report_sources(...)` succeeds against the supplied original sources.

Possible assessment statuses include:

```text
RECONCILED
SOURCE_MISSING
SOURCE_HASH_MISMATCH
PROJECT_MISMATCH
TASK_MISMATCH
REVISION_MISMATCH
REPORT_ID_MISMATCH
PROJECTION_MISMATCH
SOURCE_REPLAY_FAILED
DUPLICATE_SOURCE
```

`reconciled=true` is legal only for `RECONCILED`.

## 7. Outcome reconciliation

Outcome reconciliation is event-specific. The manifest must not provide multiple authority entries for the same event.

### 7.1 PRODUCTION_DEFECT

A conclusive `PRODUCTION_DEFECT` Outcome can reconcile only when all required facts are proven:

1. Outcome has `defect_id`.
2. Defect Registry loads and validates.
3. Defect Registry project matches the comparison project.
4. Evidence Ledger validates.
5. Ledger `registry_sources` contains the project and the exact Defect Registry canonical/file hash imported by the ledger.
6. Defect exists in both registry and ledger with matching identity/lifecycle projection.
7. The defect is related to a Ledger run for the same project and assessment `source_revision` through a linked finding or first/last-seen run relation.
8. A conclusive `UNSAFE` Outcome requires lifecycle at least `REPRODUCED` and concrete `reproducer` or `diagnostic` artifact evidence.
9. Supporting defect lifecycle/artifact/finding evidence must not be temporally later than the Outcome event where timestamps exist.
10. A `SAFE` verdict cannot be established by a Production Defect authority and fails with verdict mismatch.

A CLOSED defect additionally relies on the existing Defect Registry invariant that CLOSED requires resolution text and `resolution_evidence`.

### 7.2 CONTROLLED_EVALUATION

A conclusive `CONTROLLED_EVALUATION` Outcome can reconcile only when:

1. Evaluation report loads and passes semantic verification.
2. Outcome `evidence_refs` identifies the Evaluation authority by `evaluation_id` or `report_sha256`.
3. The Evaluation ID/hash equals the Evaluation evidence captured in the reconciled Stage 10A Trust report.
4. At least one Evaluation case has the assessment `source_revision`.
5. Repeatability is true for baseline and challenger.
6. Holdout evidence is present for a conclusive SAFE verdict.
7. SAFE requires Evaluation gate PASS and zero protected-negative regressions.
8. UNSAFE requires the assessment revision to resolve to a case explicitly listed in `protected_negative_regressions`.
9. Broad gate failure caused only by unrelated aggregate thresholds is not converted into task-level UNSAFE ground truth.

`INCONCLUSIVE` may be structurally reconciled to a verified matching Evaluation source without being usable as conclusive accuracy evidence.

### 7.3 INDEPENDENT_AUDIT

Current repository support can prove only Stage 10B actor separation and event integrity. It cannot prove independent provenance.

Result:

```text
PROVENANCE_UNVERIFIED
reconciled=false
```

### 7.4 REGRESSION / SECURITY_INCIDENT / FALSE_POSITIVE_REVIEW

No dedicated repository authority exists in the current base.

Result:

```text
UNSUPPORTED_SOURCE
reconciled=false
```

## 8. Duplicate authority defense

A single conclusive authority record must not inflate future evidence counts across multiple Outcomes.

Authority keys are granular:

```text
PRODUCTION_DEFECT: defect-registry-hash + defect_id
CONTROLLED_EVALUATION: evaluation-report-hash + matched case_id
```

If the same authority key is used to support more than one conclusive Outcome event, affected events are `DUPLICATE_AUTHORITY` and unreconciled.

This stage does not modify Stage 10D denominators. The duplicate defense is recorded now so a later pilot-safety stage has a safe source artifact to consume.

## 9. Reconciliation report contract

New artifact:

```text
trust-reconciliation-report
```

Conceptual fields:

```text
schema_version
report_id
project_id
generated_at
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
comparison_registry
source_manifest
assessment_reconciliation[]
outcome_reconciliation[]
summary
status
evidence_snapshot_sha256
report_sha256
```

Status:

```text
RECONCILED
UNRECONCILED
```

`RECONCILED` means every assessment and every conclusive Outcome in the comparison registry has an authority result that is `reconciled=true`.

Non-conclusive Outcome events are still represented and verified, but they do not independently block `source_reconciliation_complete` unless their source claim is explicitly mapped and contradictory.

The report never contains absolute local paths, actor names, or human rationale text.

## 10. Identity and semantic verification

### 10.1 Deterministic evidence snapshot

`evidence_snapshot_sha256` covers source identities, reconciliation projections, summary, and status. It excludes `generated_at`.

`report_id` is derived from:

```text
project_id
comparison registry identity/hash
source manifest hash
evidence_snapshot_sha256
```

Therefore changing `generated_at` does not alter evidence truth or `report_id`.

### 10.2 Report hash

`report_sha256` covers the full report except itself, including `generated_at`.

### 10.3 Self-contained semantic verification

`verify_reconciliation_report_data(...)` recomputes:

- fixed safety flags,
- canonical order,
- `reconciled` from status,
- duplicate authority projection,
- summary,
- overall status,
- evidence snapshot hash,
- report ID,
- outer report hash.

Changing only an outcome/assessment status and rehashing the outer report therefore fails semantic verification.

### 10.4 Source replay verification

`verify_reconciliation_report_sources(...)` reruns reconciliation from the comparison registry and source manifest with the report `generated_at` and compares the complete deterministic evidence projection plus hashes.

This catches source mutation after report creation and semantic facts that an attacker attempted to rewrite consistently with a new outer hash.

## 11. CLI

Additive commands under `pie-trust`:

```text
pie-trust reconcile-sources \
  --registry <trust-comparison.json> \
  --sources <trust-reconciliation-sources.json> \
  --output <trust-reconciliation-report.json>

pie-trust verify-reconciliation-report \
  --report <trust-reconciliation-report.json> \
  [--registry <trust-comparison.json> --sources <trust-reconciliation-sources.json>]
```

Dedicated entry point:

```text
pie-trust-reconciliation
```

Exit-code behavior follows the existing Trust CLI convention:

```text
0 valid
3 operational/input error
4 semantic verification error
```

## 12. Stage 10D boundary

Stage 10D continues to read the Stage 10B Registry exactly as before.

Stage 10C does not:

- filter Stage 10D denominators,
- change threshold policy,
- mark Stage 10D `source_reconciliation.verified_in_this_stage=true`,
- authorize a pilot.

A future R0 Pilot Safety Review may consume 10B + 10C + 10D together.

## 13. Fail-closed matrix

The following can never produce a reconciled conclusive Outcome:

- missing source file,
- source hash/ID mismatch,
- Trust semantic verification failure,
- Trust source replay failure,
- project/task/revision mismatch,
- unsupported authority type,
- duplicate authority mapping,
- duplicate authority reuse,
- Defect Registry not imported into the supplied Ledger at the expected hash,
- defect with no same-revision relation,
- defect UNSAFE claim without reproduction/diagnostic artifact evidence,
- Evaluation authority not captured by the assessment Trust report,
- Evaluation source revision mismatch,
- SAFE Evaluation without repeatability/holdout/PASS/zero protected regressions,
- UNSAFE Evaluation without a matching protected-negative regression case,
- path traversal,
- symlink input/output,
- malformed schema,
- report semantic projection tamper,
- source mutation after report generation.

## 14. Design review

The pre-implementation review rejected the following weaker designs.

### Rejected: report hash match only

Reason: a semantically valid Trust report can become stale relative to its original request/profile/evidence sources.

Resolution: require Stage 10A source replay for full assessment reconciliation.

### Rejected: Defect Registry file alone proves production defect

Reason: standalone run IDs are not relationally constrained to an actual run/revision.

Resolution: require an Evidence Ledger that imported the exact Defect Registry and use run/finding/artifact relations.

### Rejected: any Evaluation PASS means SAFE

Reason: Evaluation gate PASS is policy-level evidence and may be unrelated to the assessment revision.

Resolution: bind the exact Evaluation ID/hash through the reconciled Trust report and require a matching source-revision case.

### Rejected: any Evaluation FAIL means UNSAFE

Reason: aggregate precision/recall failures do not establish task-level unsafe ground truth.

Resolution: only a matching protected-negative regression can establish controlled-evaluation UNSAFE.

### Rejected: actor separation proves independent Audit

Reason: actor strings are not provenance or cryptographic identity.

Resolution: retain `PROVENANCE_UNVERIFIED` until an audit authority exists.

### Rejected: modify Stage 10D now

Reason: it would mix evidence verification with observation policy semantics and silently change existing denominators.

Resolution: keep 10C additive and leave 10D unchanged.

## 15. Planned validation

Focused tests cover:

- exact Trust report + source replay,
- report/hash/project/task/revision/projection mismatch,
- semantic Trust tamper with recomputed outer hash,
- source mutation after reconciliation,
- valid/missing/wrong-project Defect,
- Defect registry-to-ledger hash mismatch,
- same-revision Defect relation requirement,
- insufficient Defect reproduction evidence,
- valid/invalid Defect lifecycle evidence,
- valid Evaluation authority,
- Evaluation hash/project-binding/revision mismatch,
- repeatability/holdout/protected-negative semantics,
- unsupported authorities,
- duplicate mappings and authority reuse,
- malformed/rehashed reconciliation reports,
- symlink and traversal rejection,
- atomic output preservation,
- generated-at invariance,
- deterministic report ID,
- fixed automation/pilot false flags,
- CLI direct and delegated commands,
- full regression and package asset sync.

## 16. Exit condition

Stage 10C can end only as:

```text
STAGE_10C_PASS
READY_FOR_REVIEW
UNMERGED
```

A reconciled report is evidence for a later R0 Pilot Safety Review. It is never activation authority by itself.
