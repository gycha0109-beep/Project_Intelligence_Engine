# PIE Stage 10H — R0 Evidence Acquisition & Runtime Package Population

## 1. Purpose

Stage 10H converts genuine runtime Trust evidence into the canonical Stage 10G package without inventing missing observations, relaxing thresholds, or treating workflow acceptance as safety review.

Fixed boundary:

```text
mode=REPORT_ONLY
target_band=R0
automation_authorized=false
pilot_authorized=false
```

Stage 10H is an acquisition and packaging boundary, not an activation boundary.

## 2. Why this stage exists

Stage 10G proved that PIE can deterministically evaluate a complete R0 evidence package, but the connected repository snapshot did not contain one. `.pie/` and `.review-runs/` are ignored, so committed-tree absence is not proof that no runtime evidence exists elsewhere.

Stage 10H therefore defines how real runtime evidence must be supplied and replayed before it may become a canonical package.

## 3. Workspace contract

A Stage 10H acquisition workspace starts with:

```text
acquisition-attestation.json
comparison-registry.json
reconciliation-sources.json
observation-policy.json
<all files referenced by reconciliation-sources.json>
```

The manifest source closure may include Trust reports, requests, profiles, Ledger databases, Policy Registry snapshots, Evaluation reports, Reground artifacts, Defect Registries, Independent Audit artifacts, and Audit Authority Registries.

Stage 10H preserves those relative paths exactly in the package.

## 4. Acquisition attestation

`acquisition-attestation.json` is required to prevent accidental packaging of fixtures or examples.

The contract fixes:

```text
evidence_origin=RUNTIME_OBSERVED
synthetic_evidence_used=false
sample_evidence_used=false
thresholds_relaxed=false
```

The attestation is repository-governed metadata. It is not an external signature, trusted timestamp, or proof that a human statement is physically true.

## 5. Human evidence semantics

Stage 10B remains authoritative:

- `WORKFLOW_ACCEPTED` is not `REVIEWED`.
- `진행`, PR creation, CI success, merge approval, or accepting a next task is not automatically a safety review.
- `REVIEWED` requires an actual review decision with the Stage 10B decision contract.
- `AUDITED` requires a separate deep review.
- an Independent Audit cannot be established merely by naming an actor `auditor`.

Stage 10H never retroactively upgrades existing chat or GitHub workflow actions into safety evidence.

## 6. Package population algorithm

When the workspace is complete:

1. create a staging directory beside the target package,
2. copy the four top-level acquisition inputs,
3. copy every reconciliation source reference while preserving its relative path,
4. regenerate Stage 10C reconciliation from the copied source bytes,
5. regenerate Stage 10D observation from the copied Registry and policy,
6. run Stage 10G against the staging directory,
7. require Stage 10G source replay verification,
8. build a canonical path/SHA-256 manifest over every package file,
9. semantically verify the Stage 10H acquisition report,
10. atomically rename the staging directory into the target package.

If replay or report verification fails, the package is not published.

An existing package target is never overwritten.

## 7. Canonical published package

The published package contains at least:

```text
acquisition-attestation.json
comparison-registry.json
reconciliation-sources.json
reconciliation-report.json
observation-policy.json
observation-report.json
```

plus the full Stage 10C source closure.

The acquisition report records every package file as:

```text
path
sha256
```

and binds the ordered list with `manifest_sha256`.

Therefore mutation of the attestation, generated report, or nested source is detectable by Stage 10H package replay.

## 8. Status model

```text
BLOCKED_MISSING_INPUT
BLOCKED_MISSING_SOURCE_CLOSURE
READY_TO_POPULATE
BLOCKED_SOURCE_REPLAY
PACKAGE_POPULATED_NOT_ELIGIBLE
PACKAGE_POPULATED_ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

`READY_TO_POPULATE` means only that the acquisition workspace is structurally complete.

`PACKAGE_POPULATED_NOT_ELIGIBLE` is a valid Stage 10H outcome. Stage 10H does not exist to force eligibility.

Even:

```text
PACKAGE_POPULATED_ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

still leaves:

```text
pilot_authorized=false
automation_authorized=false
```

## 9. Current evidence authority result

The connected GitHub/repository/Actions surfaces were searched before implementation.

Observed:

- no canonical runtime R0 acquisition workspace,
- no GitHub Actions evidence artifacts on the inspected Stage 10F/10G/post-merge runs,
- no issue-carried runtime evidence,
- only non-normative sample policy/examples in the committed tree.

Therefore current runtime acquisition status is:

```text
BLOCKED_EXTERNAL_EVIDENCE_REQUIRED
```

This is not an implementation failure. It means the remaining input is genuine runtime/human evidence outside the currently connected authority surfaces.

## 10. Evidence that must not be fabricated

Stage 10H must not manufacture:

- R0 assessments,
- human `REVIEWED` / `AUDITED` decisions,
- SAFE/UNSAFE outcomes,
- Independent Audit results,
- audit issuer independence,
- production defects,
- controlled-evaluation ground truth,
- evidence timestamps,
- an organization observation policy.

The committed `trust-observation-policy.sample.json` is a schema/CLI example and must not silently become organization activation policy.

## 11. External evidence handoff

To continue an actual runtime acquisition, provide or connect a workspace containing the four top-level inputs and all relative files referenced by `reconciliation-sources.json`.

If those artifacts do not yet exist, the required work is actual observation collection under Stage 10B/10F contracts, including genuine reviewed cases and independent-audit evidence where required by the chosen policy.

Only after Stage 10H publishes the package and Stage 10G exact replay reaches `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW` may a separate R0 Pilot Activation Contract be considered.
