# PIE Stage 10K — Governed Prospective Review Packet & Explicit Human Review Binding

## 1. Purpose

Stage 10K closes one governance gap in the existing Stage 10A/10B/10I/10J prospective evidence flow:

> What exact evidence snapshot did a human inspect when recording `REVIEWED` or `AUDITED`?

Stage 10K does not create a new review authority. It binds the existing Stage 10B human decision authority to a deterministic Stage 10K packet that replays the exact Stage 10I assessment sources and Stage 10J GitHub capture state.

```text
Stage 10J GitHub prospective capture
  -> Stage 10A Trust report
  -> Stage 10I prospective assessment
  -> Stage 10K governed review packet
  -> explicit human review action
  -> existing Stage 10B-compatible REVIEWED | AUDITED HUMAN_DECISION
```

Fixed boundary:

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
human_review_recorded=false   # packet preparation state
outcome_recorded=false        # packet preparation state
```

## 2. Review packet authority

The Stage 10K packet is evidence handoff material. It is not itself a safety decision.

Required packet identity/provenance includes:

- `packet_id`
- `packet_sha256`
- `project_id`
- `assessment_id`
- `assessment_sha256`
- `task_id`
- canonical `source_revision`
- `trust_report_id`
- `trust_report_sha256`
- Stage 10J GitHub candidate identity and evidence/report hashes
- GitHub hostname, repository, PR number, base OID, exact head OID
- `predicted_risk_band`
- exact `changed_files`
- `hard_gates`
- `review_requirement`
- Trust evidence references
- Stage 10I assessment source replay state
- reconciliation state
- `generated_at`
- fixed report-only governance flags
- `evidence_snapshot_sha256`

`packet_id` is deterministic from the governed assessment/GitHub/evidence snapshot identity. `packet_sha256` is a canonical JSON semantic hash of the packet excluding its own hash field. In addition, Stage 10K requires one canonical on-disk byte representation: UTF-8 JSON, recursively sorted object keys, two-space indentation, and one terminal newline. Formatting/key-order byte drift is rejected before review authority can be created, while semantic verification and authoritative source replay separately prevent changed packet meaning plus recomputed hashes from creating review authority.

## 3. Assessment and source binding

Packet preparation does not trust registry projection alone.

It replays the Stage 10I source manifest and requires the assessment to remain source-reconciled. The packet binds:

```text
project_id
assessment_id + assessment_sha256
task_id
source_revision
trust_report_id + trust_report_sha256
assessment source inventory/hash
Trust evidence fingerprint and optional source identities
```

A Trust source replay failure prevents preparation or later governed submission.

## 4. GitHub binding

Stage 10K reuses the Stage 10J candidate rather than inventing a parallel PR ontology.

The packet binds:

```text
candidate_id
candidate evidence/report hashes
hostname
repository
PR number
base OID
exact head OID
changed-files set
```

Before verification or submission, the current GitHub PR is recollected and compared against the packet/candidate state. Head, base, repository, PR, or changed-file drift makes the packet stale.

The raw GitHub head remains a 40-hex OID. The Trust/assessment boundary remains the existing canonical `git:<40-hex>` source revision.

## 5. Stale packet semantics

A packet is not reusable when its governed sources no longer reproduce it.

Fail-closed verification uses `STALE_REVIEW_PACKET` for source/provenance drift, including:

- assessment identity or assessment source replay change,
- source revision change,
- Trust report identity/hash change,
- GitHub PR head/base/repository/PR change,
- changed-files drift,
- GitHub candidate change,
- evidence snapshot change,
- project mismatch,
- reconciliation mismatch,
- semantically changed packet with a recomputed hash that no longer matches authoritative replay.

A stale packet cannot produce a Stage 10B human decision through the governed Stage 10K submission path. A fresh packet must be prepared from the current authoritative sources.

## 6. Explicit human-action boundary

The governed commands are:

```text
prepare-prospective-review
verify-prospective-review
submit-prospective-review
```

The legacy prospective `record-prospective-review` CLI name is retained only as a packet-required alias of the governed submit path. It is no longer a raw prospective review mutation path.

Submission requires all of:

```text
exact assessment identity
+ exact review packet identity
+ packet_sha256
+ successful current source/GitHub replay
+ explicit review level
+ explicit human decision
+ explicit actor
```

The Stage 10B-compatible `HUMAN_DECISION` event is bound to the packet through reserved, hash-chain-covered provenance reason codes:

```text
REVIEW_PACKET_ID:<packet_id>
REVIEW_PACKET_SHA256:<packet_sha256>
```

Caller-supplied spoofing of these reserved reason codes is rejected.

The exact packet and Stage 10J candidate used for the decision are archived under the assessment review directory before the decision is persisted. Failure during persistence removes the staged archive.

## 7. REVIEWED and AUDITED meaning

Stage 10K reuses the Stage 10B review levels without inventing another ontology.

- `REVIEWED`: a human actually inspected the governed evidence and recorded a decision.
- `AUDITED`: the Stage 10B deeper/separate human review level.

`WORKFLOW_ACCEPTED` remains non-review workflow evidence and is not accepted by Stage 10K submission.

Stage 10K `AUDITED` is not a Stage 10F `INDEPENDENT_AUDIT` Outcome. Stage 10F independent Outcome authority still requires its own Trust Root -> Issuer Grant -> Independent Audit Artifact chain and a genuine authorized/distinct actor where the existing contract requires it.

This implementation and this GPT do not act as an independent auditor or issuer.

## 8. Duplicate and archive binding

The same governed packet cannot be used to create a second prospective human review event for the same assessment.

The mutation path requires:

- valid packet ID/hash syntax,
- exact archived packet identity/hash,
- matching project and assessment,
- unchanged report-only governance flags,
- review timestamp not earlier than packet generation,
- no prior event already bound to the same packet ID/hash.

`WORKFLOW_ACCEPTED` cannot be passed through this path.

## 9. Non-automation guarantees

None of the following implies or creates `REVIEWED` or `AUDITED`:

```text
packet prepared
packet verified
CI SUCCESS
PR merge
workflow accepted
ChatGPT implementation complete
merge approval
```

None of the following is created by Stage 10K packet preparation or implementation validation:

- authoritative `SAFE` Outcome,
- pilot eligibility,
- `pilot_authorized=true`,
- `automation_authorized=true`,
- production enforcement,
- threshold relaxation.

## 10. Scope boundary

Stage 10K remains project-local PIE technical intelligence/evidence authority.

It does not implement or authorize:

- Factory Intelligence,
- cross-project databases,
- blueprints/client overlays,
- ERP/SI orchestration,
- Factory ingestion,
- BuildMap-specific schema,
- BuildMap runtime dependencies.

The long-term Factory/BuildMap integration vision remains non-normative for this Stage.

## 11. Post-Stage direction

After Stage 10K, the intended next evidence path is operational rather than another infrastructure expansion:

```text
real R0 change
  -> Stage 10J capture
  -> Stage 10I assessment
  -> Stage 10K explicit human review
  -> later authoritative real Outcome
  -> Stage 10C reconciliation
  -> Stage 10D observation
  -> Stage 10G/10H replay
```

Synthetic, unit-test, retrospective, or implementation-validation evidence must not be represented as real runtime campaign evidence.
