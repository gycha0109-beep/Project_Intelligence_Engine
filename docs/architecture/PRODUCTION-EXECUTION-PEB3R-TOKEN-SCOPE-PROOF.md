# PEB-3R Short-Lived Token Scope Provider Proof

## Status

```text
PEB-3R TOKEN SCOPE
= PROVEN

SHORT_LIVED_TOKEN_SCOPE_NOT_PROVEN
= RESOLVED

AUTHORITATIVE_PROVIDER_SCOPE_EVIDENCE_INCOMPLETE
= RESOLVED
```

This evidence closes the remaining credential-scope blockers before PEB-3E controlled non-production PR-state calibration. It does not authorize production execution, automation, pilot operation, merge, close, branch/file mutation, workflow mutation, secret mutation, or repository settings mutation.

## Provider evidence

GitHub Actions workflow run `32625196298` in `pie-peb3-lab/pie-peb3-calibration` completed successfully and published artifact `peb3-token-scope-evidence` (`artifact_id=9489480532`). The artifact digest is:

```text
sha256:286296fbb533c7b97124f7c6f860bff5b7bcfbec73e26f7a74c4592454fd0198
```

Sanitized provider response established:

```text
GitHub App
= pie-peb3-calibration-executor
app_id = 4688931

registered permissions
= metadata:read
  pull_requests:write

installation
= 155856824
account
= pie-peb3-lab
repository_selection
= selected

short-lived token repository set
= [pie-peb3-lab/pie-peb3-calibration]

token permissions
= metadata:read
  pull_requests:write

expires_at
= 2026-08-23T08:18:08Z

independent /installation/repositories readback
= [pie-peb3-lab/pie-peb3-calibration]
verified
= true

token value retained in evidence
= false
```

The token itself and GitHub App private key are not recorded in PIE evidence.

## Formal target remains unchanged

PEB-3E formal target remains the isolated Draft PR:

```text
repository = pie-peb3-lab/pie-peb3-calibration
PR = #1
expected state = OPEN / DRAFT
expected HEAD = 295d73c9b263280705fe0ad66cd96d0edc5ee47c
```

Before dispatch, PEB-3E must mint a fresh short-lived token using the same GitHub App, re-prove exact token scope, and independently re-read the exact target state and HEAD. Only then may the frozen operation execute:

```text
DRAFT
→ MARK_READY_FOR_REVIEW
→ independent provider readback
→ CONVERT_TO_DRAFT rollback
→ independent provider readback
```

Any target drift, credential scope drift, permission drift, unexpected capability, or rollback-readiness failure must suppress dispatch.

## Authority ceiling

```text
production_execution_authorized = false
automation_authorized = false
pilot_authorized = false
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 = UNCHANGED
existing R4 authority = UNCHANGED
```
