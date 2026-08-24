# PIE ORL-3 — Review Brief

## Status

```text
Program: PIE Operational Review Loop v1
Stage: ORL-3 Review Brief
AUTO stage: NONE
Contract: PIE_OPERATIONAL_REVIEW_BRIEF_V1
Authority: projection only
```

ORL-3 converts already-bound PIE prospective evidence into a deterministic, project-local review brief for a human developer or reviewer.

It does not create a Trust assessment, a human review decision, an Outcome, merge authority, deploy authority, production-effect authority, pilot authority, or Factory Intelligence authority.

## Inputs

The brief is derived only from evidence already present in the prospective run:

```text
AUTO-1 prospective candidate
AUTO-1 impact analysis
ORL-2 operational binding, when enabled
existing governed prospective review packet, when materialized
prospective run status / PIE revision
```

The projection does not query an LLM, infer an operational class, reinterpret Trust risk, infer CI completion, or create historical similarity.

## Exact source closure

Before a brief is created, PIE verifies exact closure across the supplied artifacts.

The following identities must agree:

```text
project_id
repository hostname/name
PR number
PR base SHA
PR head SHA
changed-file set
candidate ID
source revision
```

When ORL-2 is present, its binding must point to the same candidate and exact PR source.

When a governed review packet is present, the packet must also match:

```text
assessment ID
packet ID
project ID
task ID
candidate ID
repository
PR/base/head
changed files
predicted risk band, when the run summary supplies one
```

A packet or binding from another PR cannot be projected into the brief.

## Status preservation

ORL-3 does not invent pipeline state.

```text
WAITING_FOR_TRUST_INPUT
```

is emitted only without an assessment/review-packet binding.

```text
READY_FOR_HUMAN_REVIEW
```

requires the existing governed prospective review packet and copies its exact review requirement.

The brief cannot itself transition between these states.

## Sections

The Markdown and JSON projections contain the same semantic sections.

### CHANGE

Binds:

```text
repository
PR number
base SHA
head SHA
PIE revision
candidate ID
candidate artifact SHA-256
changed files
analysis limitations
```

### AFFECTED

Copies existing impact-analysis projections:

```text
direct components
dependent files
selected review packs
```

No additional dependency inference occurs in ORL-3.

### RISK

Before Trust materialization:

```text
predicted risk band = NOT ASSESSED
review requirement = NOT MATERIALIZED
hard gates = none projected
```

After governed packet materialization, ORL-3 copies:

```text
predicted_risk_band
review_requirement
hard_gates
```

from the existing packet. `readiness` is copied only from the prospective run summary when that field is available.

### REQUIRED VERIFICATION

When ORL-2 is enabled, ORL-3 copies:

```text
selected operational class
mapped Trust task class
required scenarios
required evidence IDs
missing explicit inputs
```

It also carries the existing impact-analysis `required_tests` list separately as `analysis_required_tests`.

An analysis-required test is not converted into a completed scenario or verified operational evidence.

### HISTORY

ORL-3 v1 always emits:

```text
available = false
reason = ORL-7_NOT_IMPLEMENTED
matches = []
```

Historical recall is intentionally deferred to ORL-7 after real project-local campaign evidence accumulates. ORL-3 does not fabricate placeholder matches.

### TRUST

When available, the brief binds exact identifiers and hashes for:

```text
assessment
Trust report
governed review packet
ORL-2 operational policy/binding
```

These are references to existing evidence. They do not themselves constitute a human decision or Outcome.

### AUTHORITY

Every ORL-3 brief is schema-constrained to:

```text
human_review_recorded = false
outcome_recorded = false
automation_authorized = false
pilot_authorized = false
merge_authorized = false
deploy_authorized = false
production_effect_authorized = false
```

The human-readable brief renders the same boundary as:

```text
Human review: NOT RECORDED
Outcome: NOT RECORDED
Automation authority: NOT GRANTED
Pilot authority: NOT GRANTED
Merge authority: NOT GRANTED
Deploy authority: NOT GRANTED
Production-effect authority: NOT GRANTED
```

## Determinism and replay

The JSON projection is normalized and receives a semantic `brief_sha256`.

The brief can be regenerated from its exact prospective source artifacts. `verify_operational_review_brief_sources` rebuilds the expected projection and requires exact equality.

The generated JSON and Markdown are included in the prospective evidence bundle:

```text
review/brief.json
review/BRIEF.md
```

The bundle manifest therefore binds both artifacts by SHA-256.

The brief hash has no decision or execution authority.

## Operational sequence after ORL-3

```text
PR
→ AUTO-1 capture / impact
→ ORL-2 Operational Policy Binder
→ existing AUTO-2 Trust materialization when explicit facts are sufficient
→ ORL-3 deterministic Review Brief
→ explicit human review remains required
```

ORL-4 will add the explicit human review action surface. ORL-3 does not implement that mutation path.
