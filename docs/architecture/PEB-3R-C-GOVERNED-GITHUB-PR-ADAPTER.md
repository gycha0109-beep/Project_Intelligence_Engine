# PEB-3R-C — Governed GitHub Pull-Request Adapter Boundary

> Status: **IMPLEMENTATION PASS / LIVE TARGET BINDING BLOCKED**
>
> Authority baseline: `64b13fcd5c7380b75ab99d736f674ddfaeccd636`
>
> This stage does not create a repository, GitHub App, installation token, live calibration target, production authority, automation authority, pilot authority, or Stage10K decision.

## 1. Purpose

PEB-3R-B landed a fail-closed verifier for the dedicated non-production repository and credential boundary. The external administrator resource is still absent, but one internal blocker can be advanced safely: the governed adapter implementation.

The adapter must make it structurally impossible for a PIE call site to choose an arbitrary GitHub repository, pull request, API URL, command, merge, close, file write, branch write, workflow write, secret write, or repository-settings mutation.

## 2. Implementation

```text
src/review_system/trust_execution_governed_github_pr_adapter.py
```

Primary type:

```text
GovernedGitHubPullRequestAdapter
```

Constructor binding:

```text
repository = exact owner/name
pr_number = exact positive integer
expected_head_sha = exact lowercase 40-hex SHA
transport = narrow GitHubPullRequestTransport
```

After construction, public mutation methods accept no alternate repository or pull-request target.

## 3. Allowed public execution surface

```text
read_target()
mark_ready()
rollback_to_draft()
verify_state(expected_draft=...)
```

Allowed provider mutations are exactly:

```text
MARK_READY_FOR_REVIEW
CONVERT_TO_DRAFT
```

The adapter descriptor explicitly reports all of the following as absent:

```text
arbitrary command surface
arbitrary API/URL surface
merge surface
close surface
file-write surface
branch-write surface
workflow-write surface
secret-write surface
repository-settings surface
```

No public adapter method is provided for any of those operations.

## 4. Exact precondition contract

Before mutation, the adapter independently reads the bound target and requires:

```text
repository == bound repository
pr_number == bound PR
head_sha == bound exact HEAD
state == open
merged == false
draft == expected pre-state
```

Any mismatch terminates before provider mutation.

For `mark_ready()`:

```text
expected pre-state = draft=true
```

For `rollback_to_draft()`:

```text
expected pre-state = draft=false
```

## 5. Independent postcondition readback

After a provider mutation the adapter performs another provider readback and requires the same exact repository, PR, and HEAD plus:

```text
state == open
merged == false
draft == expected post-state
```

A provider call that returns without producing the expected state is not treated as success.

The returned receipt contains both before/after snapshots and:

```text
postcondition_verified = true
```

only after that independent readback passes.

## 6. Fail-closed tests

`tests/test_trust_execution_governed_github_pr_adapter.py` proves:

- exact repository / PR / HEAD are frozen in the descriptor,
- forbidden mutation methods are absent,
- mark-ready calls are bound to the exact target,
- rollback calls are bound to the exact target,
- wrong initial draft state suppresses dispatch,
- head drift suppresses dispatch,
- missing provider effect fails postcondition verification,
- malformed target bindings are rejected at construction.

No real GitHub PR mutation is executed by these tests.

## 7. Why the live adapter blocker remains

The implementation can now be considered prepared, but authoritative live binding cannot be claimed because the external target does not exist yet.

Current planned resource:

```text
gycha0109-beep/pie-peb3-calibration
```

Current provider search result:

```text
NOT_FOUND
```

Therefore the current frozen evidence records:

```text
implementation_ready = true
live_target_binding_proven = false
exact_pr_binding = false
exact_head_binding = false
exact_precondition_binding = false
```

The existing verifier therefore correctly continues to emit:

```text
GOVERNED_ADAPTER_BINDING_NOT_READY
```

This is now a **live-target establishment blocker**, not an adapter-code implementation gap.

## 8. Remaining external boundary

PEB-3R cannot close until an external GitHub administrative surface establishes and proves:

1. dedicated calibration repository exists,
2. selected-repository GitHub App installation is restricted to that repository,
3. short-lived installation token is downscoped to the exact repository and minimum permissions,
4. a Draft calibration PR exists in that repository,
5. its exact PR number and HEAD are provider-read back,
6. the adapter is instantiated with those exact values,
7. provider repository-set and permission-set evidence is replayable.

Only then may the PEB-3R verifier transition from `BLOCKED` to `READY_FOR_CONTROLLED_NON_PRODUCTION_EXECUTION_REVIEW`.

## 9. Authority ceiling

```text
production_execution_authorized = false
formal_nonproduction_dispatch = false
automation_authorized = false
pilot_authorized = false
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 / existing R4 authority = UNCHANGED
```

PEB-3E remains not started.
