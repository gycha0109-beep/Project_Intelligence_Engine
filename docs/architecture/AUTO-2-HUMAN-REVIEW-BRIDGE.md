# AUTO-2 — Human Review Bridge

## Status

AUTO-2 adds a governed bridge from an exact GitHub pull request to Stage 10K human-review evidence. It does **not** record a human decision, outcome, merge approval, deployment approval, pilot authorization, or production-effect authorization.

```text
AUTO_CAPTURE           = YES
AUTO_ANALYSIS          = YES
AUTO_TRUST_ASSESSMENT  = YES, only from an authority-repository Trust request
AUTO_PACKET_PREPARE    = YES
AUTO_REVIEW            = NO
AUTO_OUTCOME           = NO
AUTO_APPROVAL          = NO
AUTO_MERGE             = NO
AUTO_DEPLOY            = NO
AUTO_PRODUCTION_EFFECT = NO
```

The terminal state is:

```text
READY_FOR_HUMAN_REVIEW
```

with:

```text
human_review_recorded = false
outcome_recorded = false
automation_authorized = false
pilot_authorized = false
merge_authorized = false
deploy_authorized = false
production_effect_authorized = false
```

## Trust-source authority

AUTO-2 never derives Trust semantics from PR title, body, labels, changed files, or a PR-head-authored request.

The only v1 Trust-request authority repository is:

```text
gycha0109-beep/Project_Intelligence_Engine
```

The request must:

1. exist under `evidence/trust/requests/`;
2. be fetched from the exact 40-hex PIE revision executing the bridge;
3. have an explicitly supplied SHA-256 that matches the provider-returned bytes;
4. bind the exact target repository, PR number, live head, live base, and changed-file set through the existing GitHub prospective capture contract;
5. preserve `repository_match=true` and `head_match=true`.

The workflow is `workflow_dispatch` only and must be dispatched from PIE `main`. A branch or arbitrary caller repository cannot supply the Trust authority revision.

For a PIE-targeted PR, the authority revision must equal the target PR's exact base revision. This prevents an unrelated PIE revision from self-authorizing a PIE change.

## Provider evidence

The bridge records sanitized provider-issued evidence:

```text
authority repository
authority revision
authority commit timestamp
Trust request path
provider Git blob SHA
Trust request SHA-256
target repository
target PR number
target head SHA
target base SHA
target changed-files
```

The Trust request content itself is materialized only as a governed evidence input. No token or credential value is written to the evidence capsule.

## Raw provenance vs semantic replay

Stage 10K packet evidence deliberately preserves raw GitHub prospective-capture provenance. Provider collection metadata such as retrieval time can therefore change the candidate evidence hash and, transitively, raw Stage 10K values such as:

```text
packet_id
packet_sha256
evidence_snapshot_sha256
github.candidate_evidence_snapshot_sha256
github.candidate_report_sha256
```

These values remain in the evidence capsule and remain governed by the existing Stage 10K verification/archive contracts. AUTO-2 does not rewrite or weaken them.

AUTO-2 separately derives a semantic packet projection. The projection preserves the review-relevant meaning:

```text
packet contract
project / assessment / task identity
source revision and Trust-report identity
GitHub candidate identity
repository / PR / base / head
predicted risk
changed-files / hard gates / review requirement
Trust evidence references
source reconciliation state
authority flags
```

and excludes only run-variant transport fields:

```text
generated_at
packet_id
packet_sha256
evidence_snapshot_sha256
github.candidate_evidence_snapshot_sha256
github.candidate_report_sha256
```

The official AUTO-2 CLI records:

```text
semantic_packet_sha256
deterministic_result_sha256
```

`deterministic_result_sha256` binds the semantic packet hash together with the exact authority revision, Trust request, target repo/PR/base/head/changed-files, assessment, risk/readiness projection, and all negative authority flags.

Therefore:

```text
raw provider / packet provenance may differ across observations
semantic_packet_sha256 must remain equal for identical semantics
deterministic_result_sha256 must remain equal for identical governed inputs
```

A semantic change such as a different target head, assessment, Trust source, risk projection, or review-relevant packet field must change the semantic/deterministic hash.

The bridge uses the authority commit timestamp for the ephemeral Stage 10I workspace, Trust assessment capture, and Stage 10K packet generation. Replaying the same authority revision, Trust request, and exact PR target therefore receives the same governed temporal anchor.

## Existing contracts reused unchanged

AUTO-2 reuses, rather than redesigns:

- Stage 10J GitHub prospective capture;
- Trust request schema and Trust assessment;
- Stage 10I prospective intake/reconciliation;
- Stage 10K governed review-packet preparation and stale-target verification;
- existing explicit human review submission commands.

`submit-prospective-review` is deliberately absent from the AUTO-2 workflow.

## Workflow

```text
.github/workflows/prospective-human-review-bridge.yml
```

The workflow has only:

```text
contents: read
pull-requests: read
```

It receives no secrets, does not use `pull_request_target`, checks out the exact target PR head without persisted credentials, installs the exact PIE authority revision, prepares the evidence capsule, and stops.

## Calibration rule

Initial runtime proof must use a synthetic calibration target and a Trust request explicitly marked synthetic/calibration-only. Real BuildMap, K_beauty, or Myeonghwa Trust semantics must not be fabricated by AUTO-2.

A valid replay proof requires two runs with the same:

```text
authority revision
Trust request SHA-256
target repository
target PR
target head
target base
changed-files
```

The proof must show equality of:

```text
assessment_id
execution_id
semantic_packet_sha256
deterministic_result_sha256
```

Raw `packet_id`, raw packet evidence hashes, provider retrieval metadata, and the raw observation manifest are retained as provenance and are permitted to differ between observations.

All human/outcome/automation/pilot/merge/deploy/production-effect flags must remain false.
