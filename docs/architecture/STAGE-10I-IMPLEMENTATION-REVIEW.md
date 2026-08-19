# PIE Stage 10I — Implementation Review

## Result

Implementation target: a prospective case-intake and campaign-projection boundary layered on the existing Stage 10B/10C/10D/10F/10H contracts.

## Accepted design decisions

### Reuse Stage 10B registry and events

Stage 10I does not create another evidence database. Assessment, decision, and Outcome semantics remain owned by the existing comparison registry.

### Exact revision required

Prospective intake accepts only an exact 40-hex git revision. Ambiguous branch names, short SHAs, and mutable refs are not campaign authority.

### Exact Trust replay required

The supplied Stage 10A report must replay from its request/profile and optional evidence sources before intake.

### Preserve source basenames

Real intake testing showed that Stage 10A evidence fingerprints include source filename metadata. Renaming supplied sources while copying them would break exact replay. Stage 10I therefore stores each source in a field-specific directory while preserving its original basename.

### Reconcile before persistence

A new assessment source mapping and each conclusive Outcome authority are replayed through Stage 10C before the authoritative registry/manifest pair is replaced.

### Registry/manifest pair rollback

The two authoritative JSON files are written through temporary files. If the second replace or post-write validation fails, original bytes are restored.

### Review is explicit

Only `REVIEWED` and `AUDITED` are admitted by the Stage 10I review boundary. `WORKFLOW_ACCEPTED` is deliberately excluded.

### Report verifier reprojects semantics

The campaign report verifier recomputes:

- embedded policy ID and SHA,
- ten threshold checks,
- status and next step,
- observation identities,
- evidence snapshot,
- campaign ID,
- report SHA.

This prevents a threshold-relaxation plus rehash attack from becoming a valid campaign report.

### Immutable Stage 10H snapshots

Snapshot creation delegates to the Stage 10H publisher and verifies both workspace and package replay. Mutation of an existing snapshot is rejected rather than overwritten.

## Rejected approaches

- retroactively count historical PR merges or CI success as `REVIEWED`,
- create synthetic SAFE/UNSAFE outcomes to fill thresholds,
- silently adopt a relaxed observation policy,
- persist currently unsupported Outcome authorities and leave them unreconciled,
- generate an Independent Audit issuer or artifact without a real actor,
- treat Stage 10I readiness as pilot authorization.

## Safety properties

```text
mode=REPORT_ONLY
target_band=R0
automation_authorized=false
pilot_authorized=false
```

Additional controls:

- symlinked workspace/source input rejected,
- capture time cannot precede Trust report generation,
- duplicate `(task_id, source_revision)` inflation rejected,
- exact duplicates are idempotent,
- conclusive Outcome replay required before persistence,
- source reconciliation blocks readiness before metric progress,
- confirmed false-negative evidence blocks campaign readiness,
- immutable snapshots cannot be overwritten.

## Current operating state

Stage 10I makes prospective collection executable, but the real baseline still has zero collected cases. Counters change only when future real changes are assessed and explicitly reviewed/outcome-bound.
