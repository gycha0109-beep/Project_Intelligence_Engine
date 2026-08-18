# PIE Stage 10H — Implementation Review

## Result

Implementation target: a fail-closed runtime evidence acquisition and package-publication boundary.

The implementation does not create evidence. It validates and packages supplied evidence.

## Authority decisions

### Accepted: preserve full reconciliation source closure

A Stage 10G top-level package is not self-sufficient when `reconciliation-sources.json` points to nested source authorities. Stage 10H therefore inventories and copies every referenced source while preserving relative paths.

### Accepted: regenerate derived reports

`reconciliation-report.json` and `observation-report.json` are regenerated in staging from supplied source bytes. Existing derived reports are not trusted as acquisition inputs.

### Accepted: Stage 10G source replay before publication

A structurally complete workspace is not enough. The staging package must pass Stage 10G source replay before publication.

### Accepted: byte manifest over the published package

The acquisition report binds every package path and SHA-256 plus a deterministic manifest hash. This detects later mutation outside the five Stage 10G top-level inputs, including attestation and nested source bytes.

### Accepted: validate report before directory rename

The final acquisition report is semantically finalized before the staging directory is renamed to the target. Report-validation failure therefore cannot leave a supposedly published target package.

### Accepted after real-main replay: preserve final package basename during staging

A replay against the uploaded clean `main` checkout exposed a root-identity bug that mocked tests did not catch.

Stage 10G includes `package_contract.root_name` in the evidence snapshot/run identity. The initial Stage 10H publisher ran Stage 10G directly against a randomly named temporary staging directory, then renamed that directory to the final package name. The resulting package bytes were valid, but a later replay from the final directory recomputed a different Stage 10G `run_id` because the root basename had changed.

Observed failure:

```text
package replay pilot_evidence_run_id mismatch
```

Fix:

```text
random staging parent
  / final-package-basename
      <package bytes>
```

Stage 10G now sees the final logical package basename before publication. Atomic `os.replace` moves that child directory to the target without changing its basename, so the published package reproduces the original Stage 10G run identity.

A non-mocked end-to-end regression now creates an empty but schema-valid runtime workspace, publishes it, and verifies the acquisition report against both the original workspace and the renamed package.

### Rejected: copy previously generated Stage 10C/10D reports

Reason: stale or rewritten reports could be packaged without proving they still replay from the acquisition source bytes.

### Rejected: use the repository sample observation policy

Reason: the sample explicitly is not organization policy. Stage 10H requires the runtime acquisition workspace to supply the policy actually being used.

### Rejected: infer human review from workflow history

Reason: Stage 10B explicitly separates workflow acceptance from reviewed/audited safety decisions.

### Rejected: synthesize missing Independent Audit evidence

Reason: Stage 10F requires an actual issuer authority/artifact relationship and temporal/outcome binding.

## Safety properties

The implementation enforces:

```text
mode=REPORT_ONLY
target_band=R0
automation_authorized=false
pilot_authorized=false
```

Additional controls:

- no package overwrite,
- no symlink workspace/source traversal,
- no `..` traversal through manifest refs,
- reserved top-level path collision rejection,
- missing raw inputs are explicit blockers,
- missing nested source closure is an explicit blocker,
- invalid attestation fails verification,
- source replay failure prevents publication,
- package file path/SHA manifest detects byte mutation,
- acquisition report has deterministic evidence snapshot and report identity,
- acquisition report writes use tempfile + fsync + replace,
- final package basename is stable across staging/publication so Stage 10G run identity replays exactly.

## Real-main prospective baseline

After the user supplied a clean `main` checkout, Stage 10H was exercised against the actual repository baseline rather than a test fixture.

Repository authority:

```text
branch=main
HEAD=c8578aa2c8096b3f0fa7652248c078702a94d023
origin/main=c8578aa2c8096b3f0fa7652248c078702a94d023
working_tree=CLEAN
```

No prior `.pie/`, `.review-runs/`, comparison, reconciliation, observation, or audit runtime evidence existed in that checkout. A prospective runtime workspace was therefore initialized from zero observations.

The approved V1 human-pilot-review evidence gate is:

```text
minimum_r0_assessment_count=20
minimum_r0_reviewed_count=20
minimum_r0_conclusive_outcome_count=12
minimum_r0_confirmed_safe_count=12
minimum_confirmed_unsafe_challenge_count=8
minimum_r0_independent_audit_count=5
minimum_r0_outcome_coverage=0.60
minimum_r0_evidence_span_days=14
maximum_r0_false_negatives=0
maximum_r0_false_negative_rate=0.0
```

This is an operational minimum for entering a bounded human pilot-authorization review, not a statistical safety certification.

After the root-identity fix, the zero-observation baseline successfully publishes and replays:

```text
status=PACKAGE_POPULATED_NOT_ELIGIBLE
package_published=true
source_replay_verified=true
pilot_authorized=false
```

The runtime package remains local/gitignored evidence and is not committed as repository truth.

## Current runtime interpretation

Implementation authority and runtime evidence authority remain separate.

The real-main baseline now exists, but it contains zero prospective observations. Therefore the previous external-workspace blocker has been replaced by an evidence-collection blocker:

```text
RUNTIME_BASELINE=INITIALIZED
R0_PILOT_ELIGIBILITY=NOT_ELIGIBLE
NEXT=COLLECT_PROSPECTIVE_REVIEWED_AND_OUTCOME_EVIDENCE
```

No claim may be made that the observation thresholds, Independent Audit threshold, or pilot eligibility have been reached.

## Remaining trust-model limits

The Stage 10H attestation is not cryptographic proof of physical-world truth. Stage 10F issuer metadata is repository-governed rather than external PKI. The system verifies deterministic provenance contracts and supplied bytes; stronger authenticity requires external signing/timestamp/independent observation infrastructure.
