# AUTO-2 — Human Review Bridge

## Status

AUTO-2 adds a governed bridge from an exact GitHub pull request to a deterministic Stage 10K review packet. It does **not** record a human decision, outcome, merge approval, deployment approval, pilot authorization, or production-effect authorization.

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

## Deterministic replay

Raw Stage 10K `packet_sha256` can include transport/generation metadata. AUTO-2 therefore binds deterministic replay to the semantic Stage 10K identity:

```text
packet_id
evidence_snapshot_sha256
assessment_id
risk/readiness projection
authority source binding
exact GitHub target binding
Trust request content SHA-256
```

The bridge writes `result.json` and computes:

```text
deterministic_result_sha256
```

from that stable projection. Run-specific provider transport metadata is not part of this semantic replay hash.

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

and equality of:

```text
packet_id
packet_evidence_snapshot_sha256
deterministic_result_sha256
```

while all human/outcome/automation/pilot/merge/deploy/production-effect flags remain false.
