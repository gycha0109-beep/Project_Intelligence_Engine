# AUTO-4A — Prospective Artifact Aggregation Core

## Status

AUTO-4A introduces a deterministic, read-only aggregation boundary for replayable prospective PR evidence artifacts.

It does **not** mutate a prospective campaign workspace, evaluate campaign thresholds, infer Outcomes, promote cross-project knowledge, or grant operational authority.

```text
ARTIFACT_VERIFICATION        = YES
SEMANTIC_REPLAY_DEDUP        = YES
REPLAY_CONFLICT_DETECTION    = YES
AGGREGATION_REPORT           = YES

CAMPAIGN_WORKSPACE_MUTATION  = NO
R0_COUNTER_MUTATION          = NO
CAMPAIGN_THRESHOLD_EVALUATION = NO
OUTCOME_INFERENCE            = NO
CROSS_PROJECT_PROMOTION      = NO
AUTO_APPROVAL                = NO
AUTO_MERGE                   = NO
AUTO_DEPLOY                  = NO
AUTO_PILOT                   = NO
AUTO_PRODUCTION_EFFECT       = NO
```

Contract:

```text
PIE_AUTO4_ARTIFACT_AGGREGATION_V1
```

CLI:

```text
pie-trust-campaign-aggregate \
  --artifact-root <extracted-artifact-A> \
  --artifact-root <extracted-artifact-B> \
  --output aggregate.json
```

## Input boundary

AUTO-4A accepts either:

```text
<artifact-root>/
├─ bundle/
│  ├─ manifest.json
│  ├─ summary.json
│  ├─ deterministic-result.json
│  └─ ...
└─ workflow-context.json
```

or a direct evidence bundle root containing `manifest.json`.

The staged Actions artifact form is preferred because `workflow-context.json` preserves provider transport identity separately from the deterministic PIE semantic result.

Every bundle is replay-verified through the existing `PIE_PROSPECTIVE_EVIDENCE_BUNDLE_V1` verifier before aggregation.

## Exact binding

AUTO-4A requires exact equality across the bundle manifest, summary, execution identity, deterministic result, and — when present — workflow context for:

```text
execution_id
execution_key_sha256
repository
pull_request
source_revision
pie_revision
deterministic_result_sha256
raw observation manifest hash
```

A workflow context must remain:

```text
human_review_recorded        = false
outcome_recorded             = false
automation_authorized        = false
pilot_authorized             = false
merge_authorized             = false
deploy_authorized            = false
production_effect_authorized = false
```

Any attempted authority elevation fails closed as `AUTHORITY_VIOLATION`.

## Replay semantics

The central AUTO-4A distinction is:

```text
RAW PROVIDER OBSERVATION
!=
DETERMINISTIC EXECUTION RESULT
```

The same governed execution can be observed more than once. Provider run identity, timestamps, transport metadata, or other raw evidence may legitimately produce different raw bundle manifest hashes.

Therefore this is allowed:

```text
execution_id                 = same
execution_key_sha256         = same
deterministic_result_sha256  = same
raw observation manifest A   != raw observation manifest B
```

Both raw observations remain preserved in the aggregation report.

This is not allowed:

```text
same execution_id
+
different execution_key_sha256
```

or:

```text
same execution_id
+
different deterministic_result_sha256
```

Those states fail closed as:

```text
NON_DETERMINISTIC_REPLAY
```

The inverse mapping is also protected: one `execution_key_sha256` cannot map to multiple execution IDs.

## Duplicate input handling

Supplying the exact same extracted artifact multiple times does not create additional observations.

AUTO-4A records:

```text
input_artifact_count
unique_observation_count
duplicate_observation_count
unique_execution_count
```

Duplicate input handling does not create campaign evidence or authority.

## Aggregation output

A successful report terminates at:

```text
status    = ARTIFACT_AGGREGATION_READY
next_step = PROJECT_LOCAL_CAMPAIGN_PROJECTION_REQUIRED
```

The report contains deterministic repository and execution projections, including:

```text
repository
pull_request
source_revision
PIE revision
execution id/key
deterministic result hash
raw observation count
raw observation manifest hashes
workflow run observations
```

`aggregation_sha256` is calculated from a canonical semantic projection and is invariant to input argument order.

## Why AUTO-4A does not mutate campaign state

The existing prospective campaign authority is project-local. Its workspace requires an exact project identity and source-reconciliation mapping, and `prospective-campaign-progress` remains the authority for campaign threshold computation.

AUTO-4A therefore does not flatten artifacts from multiple repositories into one synthetic campaign registry.

The boundary is intentionally:

```text
project artifacts
      ↓
AUTO-4A verify / dedup / conflict detect
      ↓
normalized aggregation report
      ↓
AUTO-4B project-local projection (future stage)
      ↓
existing prospective campaign authority
```

This preserves the distinction between evidence transport/aggregation and project-local Trust campaign authority.

## Factory Intelligence boundary

AUTO-4A is not a Factory Intelligence knowledge-promotion mechanism.

It may aggregate references to project-local evidence, but:

```text
cross_project_knowledge_promotion_authorized = false
```

No repeated artifact or repeated execution becomes a reusable Factory rule merely because AUTO-4A observed it.

## Failure classes

AUTO-4A fails closed on:

```text
INVALID_INPUT
EVIDENCE_HASH_MISMATCH
SOURCE_MISMATCH
NON_DETERMINISTIC_REPLAY
AUTHORITY_VIOLATION
```

Risk or Trust classification is not itself an AUTO-4A system failure. AUTO-4A is concerned with evidence integrity and replay identity, not with converting a risk band into CI control authority.

## Authority ceiling

Every successful AUTO-4A report preserves:

```text
workspace_mutation_performed          = false
campaign_thresholds_evaluated         = false
cross_project_knowledge_promotion_authorized = false
automatic_outcome_inference            = false
automation_authorized                  = false
pilot_authorized                       = false
merge_authorized                       = false
deploy_authorized                      = false
production_effect_authorized           = false
```

AUTO-4A authorizes only artifact verification, replay deduplication, conflict detection, and normalized reporting.

## Next stage

AUTO-4B may add a governed projection layer that partitions verified AUTO-4A executions by project and feeds only project-compatible evidence into existing prospective campaign workspaces.

That stage must preserve:

```text
per-project authority
exact source replay
existing campaign thresholds
synthetic evidence isolation
no automatic Outcome inference
no automatic pilot/merge/deploy authority
```

A later provider observer may retrieve Actions artifacts through a read-only credential boundary. AUTO-4A deliberately does not require such credentials.
