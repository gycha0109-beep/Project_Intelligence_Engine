# AUTO-4B — Project-local Campaign Projection

## Status

AUTO-4B projects verified AUTO-2 Human Review Bridge artifacts into one durable project-local prospective campaign workspace.

It does not merge unrelated projects into one Trust registry and does not copy registry rows directly.

The projection path is:

```text
AUTO-2 bridge artifact
→ verify bridge result / Stage 10K semantic replay
→ verify source campaign reconciliation
→ resolve stored Trust report / request / profile
→ temporary destination-campaign preflight
→ intake_prospective_case()
→ campaign_progress()
→ authoritative project-local projection
```

Contract:

```text
PIE_AUTO4_PROJECT_CAMPAIGN_PROJECTION_V1
```

CLI:

```text
pie-trust-campaign-project \
  --workspace .pie/campaigns/my-project \
  --artifact-root <auto2-artifact-A> \
  --artifact-root <auto2-artifact-B> \
  --output projection.json
```

## Why the projection starts from AUTO-2

The reusable AUTO-1 PR workflow intentionally terminates at:

```text
WAITING_FOR_TRUST_INPUT
```

unless an authority-safe Trust request is supplied.

Those raw PR observations are useful for capture and replay, but they are not yet authority-bearing prospective campaign assessments.

AUTO-2 already supplies the missing governed boundary:

```text
PIE authority revision
→ provider-fetched Trust request
→ exact target PR binding
→ Trust assessment
→ Stage 10I prospective intake
→ Stage 10K review packet
→ READY_FOR_HUMAN_REVIEW
```

Therefore AUTO-4B accepts only verified AUTO-2 bridge artifacts that stopped at `READY_FOR_HUMAN_REVIEW` with no human decision or Outcome recorded.

## Source artifact verification

AUTO-4B verifies all of the following before destination mutation:

```text
AUTO-2 result_contract
AUTO-2 bridge_contract
AUTO-2 Trust source contract
REPORT_ONLY mode
Trust request bytes SHA-256
result authority == source authority
result target == source target
result Trust task/source revision == source evidence
exactly one automation evidence bundle
bundle manifest integrity
Stage 10K semantic packet replay hash
AUTO-2 deterministic result hash
bundle repository / PR / head / PIE revision binding
bundle assessment / packet binding
source campaign project_id
source campaign assessment identity
source campaign source reconciliation
source observation policy
stored Trust report / request / profile paths
```

The existing AUTO-2 semantic replay rule remains intact:

```text
raw Stage 10K packet provenance may vary
semantic_packet_sha256 must remain stable
AUTO-2 deterministic_result_sha256 must remain stable
```

A tampered stabilized bridge result fails closed as:

```text
NON_DETERMINISTIC_REPLAY
```

## Project scope

One AUTO-4B invocation may project multiple bridge artifacts, but all of them must belong to exactly one `project_id`.

```text
Project A artifact ─┐
Project A artifact ─┼→ Project A campaign workspace
Project A artifact ─┘

Project B artifact ─X→ Project A campaign workspace
```

Cross-project flattening is rejected as `PROJECT_SCOPE_MISMATCH`.

This preserves the existing campaign authority model:

```text
comparison-registry.project_id
reconciliation-sources.project_id
campaign_progress.project_id
```

## No registry-row copying

AUTO-4B does not append source registry JSON rows into the destination registry.

Instead, for every source assessment it resolves the exact source files recorded by source reconciliation:

```text
trust_report
request
profile
ledger                    optional
policy_registry            optional
evaluation_report          optional
reground_report            optional
reground_observations      optional
```

and calls the existing authoritative intake path:

```text
intake_prospective_case()
```

The destination assessment id must reproduce the source assessment id exactly.

This means aggregation cannot bypass Trust-report verification, source revision binding, project identity, source reconciliation, or the existing prospective evidence contract.

## Preflight before mutation

AUTO-4B first prepares a temporary destination campaign.

For a new destination:

```text
new project-local registry
+ exact source observation policy
+ empty reconciliation map
→ project every input artifact
→ campaign_progress()
→ require complete source reconciliation
→ land the verified workspace
```

For an existing destination:

```text
copy authoritative workspace to temporary preflight
→ project all artifacts
→ verify campaign progress
→ only then repeat exact projection on authoritative workspace
→ require final registry_sha256 equality
→ require campaign evidence_snapshot_sha256 equality
```

Thus logical conflicts are discovered before authoritative mutation.

## Semantic replay and deduplication

Multiple AUTO-2 runs may preserve different raw packet ids or provider evidence hashes while representing the same exact assessment.

AUTO-4B accepts those observations only when the stabilized AUTO-2 deterministic result is equal.

The existing prospective intake then performs canonical assessment deduplication.

Example:

```text
AUTO-2 replay A
assessment = X
semantic result = H

AUTO-2 replay B
assessment = X
semantic result = H

projection result
assessment X stored once
second input = idempotent
```

But:

```text
assessment X
semantic result H1
semantic result H2
```

fails as:

```text
NON_DETERMINISTIC_REPLAY
```

## Observation policy

All source artifacts in one projection must use the same observation policy.

If the destination already exists, its policy must match the source policy exactly by canonical semantic hash.

Policy mixing fails closed as:

```text
POLICY_MISMATCH
```

AUTO-4B does not silently reinterpret historical evidence under a different threshold contract.

## Campaign authority

After projection, AUTO-4B invokes the existing:

```text
prospective campaign_progress()
```

This remains the authority for project-local campaign counters and threshold status.

AUTO-4B reports values such as:

```text
r0_assessment_count
r0_reviewed_count
r0_conclusive_outcome_count
campaign_status
source_reconciliation_complete
```

AUTO-4B does not calculate alternative R0 eligibility logic.

## Human review and Outcome boundary

AUTO-4B currently projects **assessment evidence only**.

Accepted AUTO-2 artifacts must satisfy:

```text
human_review_recorded        = false
outcome_recorded             = false
automation_authorized        = false
pilot_authorized             = false
merge_authorized             = false
deploy_authorized            = false
production_effect_authorized = false
```

Source campaigns containing human decision or Outcome events are rejected in AUTO-4B.

Therefore:

```text
human_review_projected = false
outcome_projected      = false
```

A later stage must project explicitly governed human decisions and declaration-bound Outcomes without weakening AUTO-2/AUTO-3 authority.

## Authority ceiling

AUTO-4B may mutate the **project-local evidence collection workspace** by adding verified assessments.

That is not automation/pilot/product-effect authority.

Every terminal report preserves:

```text
automatic_outcome_inference  = false
automation_authorized        = false
pilot_authorized             = false
merge_authorized             = false
deploy_authorized            = false
production_effect_authorized = false
```

`workspace_mutation_performed=true` means only that verified evidence was durably projected into the local campaign registry.

## Factory Intelligence boundary

AUTO-4B remains inside PIE's project-local Trust evidence lifecycle.

It does not create:

```text
cross-project pattern
factory rule
blueprint knowledge
cross-project promotion
client-shared evidence store
```

Different projects remain different campaign workspaces. Cross-project generalization remains outside PIE's project-local campaign authority.

## Next stage

AUTO-4C may add governed event projection for already-authorized:

```text
Stage 10K REVIEWED / AUDITED human decisions
AUTO-3 declaration-bound Outcomes
```

The projection must preserve the original event/declaration authority and must not infer either event automatically.
