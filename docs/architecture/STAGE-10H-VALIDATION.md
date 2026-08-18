# PIE Stage 10H — Validation

## Validation objective

Validate the acquisition boundary independently from whether genuine runtime evidence is currently sufficient for pilot review.

## Focused regression

Tests cover:

- missing required workspace inputs -> valid `BLOCKED_MISSING_INPUT`,
- missing manifest source closure -> valid `BLOCKED_MISSING_SOURCE_CLOSURE`,
- complete workspace -> `READY_TO_POPULATE` only,
- invalid/sample acquisition attestation rejection,
- symlinked source closure rejection,
- existing package target rejection,
- verified Stage 10G `NOT_ELIGIBLE` result may still publish a truthful package,
- Stage 10G source replay failure prevents package publication,
- report finalization failure leaves no published target,
- published package byte mutation is detected,
- semantic rehash cannot set `pilot_authorized=true`,
- standalone and delegated CLI command registration,
- non-mocked empty runtime package publish + post-rename replay reproduces the same Stage 10G run identity.

## Real-main replay finding

The user supplied a clean `main` checkout:

```text
HEAD=c8578aa2c8096b3f0fa7652248c078702a94d023
origin/main=c8578aa2c8096b3f0fa7652248c078702a94d023
working_tree=CLEAN
```

The checkout contained no prior `.pie/`, `.review-runs/`, Trust comparison, reconciliation, observation, or Independent Audit runtime evidence.

A prospective zero-observation workspace was initialized and populated using the Stage 10H tooling. The first real replay found:

```text
package replay pilot_evidence_run_id mismatch
```

Root cause: Stage 10G binds the package root basename into `package_contract.root_name`. Stage 10H had generated the Stage 10G run in a randomly named staging directory, then renamed that directory to the final package path. The bytes were unchanged but the logical root identity changed.

Fix: create a random staging parent containing a child directory whose basename already equals the final package basename, run Stage 10G against that child, then atomically move the child to the final target.

After the fix, the same real-main baseline produced:

```text
status=PACKAGE_POPULATED_NOT_ELIGIBLE
package_published=true
source_replay_verified=true
workspace_replayed=true
package_replayed=true
errors=[]
```

This scenario is now a non-mocked regression test.

## Approved prospective V1 evidence gate

The runtime baseline uses an explicit non-sample policy:

```text
minimum_r0_assessment_count=20
minimum_r0_reviewed_count=20
minimum_r0_conclusive_outcome_count=12
minimum_r0_confirmed_safe_count=12
minimum_confirmed_unsafe_challenge_count=8
minimum_r0_independent_audit_count=5
minimum_r0_outcome_coverage=0.60
minimum_r0_evidence_span_days=14
maximum_r0_false_negatives=0
maximum_r0_false_negative_rate=0.0
```

Interpretation: this is an operational minimum for considering a bounded R0 human pilot-authorization review. It is not a statistical safety certification or permission to automate.

At zero observations, Stage 10D correctly reports:

```text
status=INSUFFICIENT_EVIDENCE
r0_assessment_count=0
r0_reviewed_count=0
r0_conclusive_outcome_count=0
r0_confirmed_safe_count=0
confirmed_unsafe_challenge_count=0
r0_independent_audit_count=0
r0_outcome_coverage=null
r0_evidence_span_days=0.0
r0_false_negative=0
r0_false_negative_rate=null
```

The null false-negative rate is intentionally not treated as zero when no unsafe denominator exists.

## Full regression

Terminal validation requires the repository CI matrix on the documentation-inclusive exact Stage 10H head:

```text
Python 3.11
Python 3.13
Python 3.14
```

Each matrix job must complete:

- editable package installation,
- package asset synchronization,
- full unittest discovery,
- existing `urs` version/profile/Finding validation,
- wheel build.

Root/package copies of both Stage 10H schemas must remain byte-identical.

## Runtime evidence validation

The real-main prospective baseline is now initialized, but it contains zero observed cases. Runtime validation therefore transitions from workspace acquisition to prospective evidence collection.

For each real case, the evidence chain must eventually contain:

1. a Stage 10A Trust report tied to an exact source revision,
2. Stage 10B assessment capture,
3. an explicit `REVIEWED` or `AUDITED` human decision when applicable,
4. a later conclusive Outcome where real authority exists,
5. Stage 10F Independent Audit authority/artifact for cases counted toward the audit threshold,
6. updated Stage 10C reconciliation source closure,
7. regenerated Stage 10D observation report,
8. Stage 10G exact replay.

No `진행`, merge approval, CI success, or workflow acceptance may be promoted to `REVIEWED`/`AUDITED` evidence.

## Success interpretation

Stage 10H implementation PASS means the acquisition mechanism is ready and has been exercised successfully against the clean main baseline.

It does not mean:

- sufficient R0 cases exist,
- observations meet thresholds,
- independent audits exist,
- Stage 10G reached eligibility,
- pilot activation is authorized.

Those remain runtime evidence facts and stay fail-closed until actually demonstrated.
