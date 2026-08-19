# PIE Stage 10I — Prospective R0 Evidence Collection

## 1. Purpose

Stage 10I turns future real PIE changes into prospective R0 evidence without retroactively promoting historical workflow actions.

Fixed boundary:

```text
mode=REPORT_ONLY
target_band=R0
automation_authorized=false
pilot_authorized=false
```

Stage 10I collects evidence. It does not authorize a pilot and does not change Stage 10D thresholds.

## 2. Evidence chain

Each real case follows:

```text
exact source revision
  -> Stage 10A Trust assessment
  -> Stage 10B assessment capture
  -> explicit REVIEWED or AUDITED decision
  -> later authoritative Outcome
  -> optional Stage 10F Independent Audit
  -> Stage 10C source reconciliation
  -> Stage 10D observation projection
  -> immutable Stage 10H / Stage 10G replay snapshot
```

CI success, merge approval, workflow acceptance, or chat instructions are not safety-review evidence.

## 3. Prospective intake contract

`intake-prospective-case` requires an exact Stage 10A Trust report and the source bytes needed to replay it.

The Trust request must bind an exact 40-hex git source revision. Capture cannot precede Trust report generation.

For a `(task_id, source_revision)` pair:

- identical Trust identity is idempotent,
- a different Trust report is rejected,
- duplicate assessment inflation is therefore blocked.

Stage 10I preserves the original basename of every Trust source because Stage 10A evidence identity includes source filename metadata.

## 4. Human review contract

Only:

```text
REVIEWED
AUDITED
```

may be recorded by the prospective review command.

The existing Stage 10B decision contract remains authoritative. Stage 10I does not create a weaker parallel review model.

## 5. Outcome contract

Stage 10I accepts only authorities that the current Stage 10C/10F stack can replay:

```text
PRODUCTION_DEFECT
CONTROLLED_EVALUATION
INDEPENDENT_AUDIT
```

Currently unsupported authorities are rejected before registry mutation.

For a conclusive `SAFE` or `UNSAFE` Outcome, source reconciliation must succeed before persistence.

Controlled Evaluation evidence binds the evaluation report identity. Independent Audit evidence binds the audit artifact identity and existing Stage 10F issuer authority; Stage 10I does not invent an auditor.

## 6. Campaign progress

`prospective-campaign-progress` projects the existing Stage 10D policy against current prospective evidence.

Statuses:

```text
COLLECTING_EVIDENCE
BLOCKED_SOURCE_RECONCILIATION
BLOCKED_SAFETY_SIGNAL
READY_FOR_STAGE_10G_REPLAY
```

Source-reconciliation failure has priority over threshold progress. Confirmed false-negative evidence has safety-blocking priority.

The report embeds and verifies the authoritative policy identity, all ten threshold checks, status projection, evidence snapshot, campaign identity, and report SHA.

## 7. Immutable snapshots

`snapshot-prospective-campaign` uses Stage 10H package population to create a package keyed by the exact comparison-registry SHA.

A repeated snapshot is idempotent only when the existing package and acquisition report replay exactly. Existing mutated snapshot bytes fail closed.

## 8. CLI

Standalone:

```text
pie-trust-prospective intake-prospective-case
pie-trust-prospective record-prospective-review
pie-trust-prospective record-prospective-outcome
pie-trust-prospective prospective-campaign-progress
pie-trust-prospective snapshot-prospective-campaign
```

The same subcommands are delegated through `pie-trust`.

## 9. Runtime interpretation

Stage 10I implementation does not increase the real campaign counters by itself.

The initialized runtime baseline remains at zero observations until an actual future PIE change is assessed and captured at its exact revision.

The approved V1 gate remains unchanged:

```text
R0 assessments              >= 20
R0 reviewed                 >= 20
R0 conclusive outcomes      >= 12
R0 confirmed SAFE           >= 12
unsafe challenge evidence   >= 8
R0 independent audits       >= 5
R0 outcome coverage         >= 60%
evidence span               >= 14 days
R0 false negatives          = 0
R0 false-negative rate      = 0.0
```

This is an operational human-pilot-review gate, not a statistical safety certification.
