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
- acquisition report writes use tempfile + fsync + replace.

## Current external blocker

Implementation authority and runtime evidence authority are separate.

At implementation time, available GitHub surfaces contain no genuine acquisition workspace. This means the code can be completed and reviewed, but no claim may be made that a real R0 package has been populated or that pilot eligibility has been reached.

Terminal implementation status must therefore be reported separately from runtime status, for example:

```text
STAGE_10H_IMPLEMENTATION_PASS
RUNTIME_ACQUISITION=BLOCKED_EXTERNAL_EVIDENCE_REQUIRED
PILOT_AUTHORIZED=false
```

## Remaining trust-model limits

The Stage 10H attestation is not cryptographic proof of physical-world truth. Stage 10F issuer metadata is repository-governed rather than external PKI. The system verifies deterministic provenance contracts and supplied bytes; stronger authenticity requires external signing/timestamp/independent observation infrastructure.
