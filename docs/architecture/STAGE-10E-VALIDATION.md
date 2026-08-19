# Stage 10E — Validation

## Scope

Stage 10E validation covers the R0 Pilot Safety Review implementation only. It does not authorize a pilot and does not claim that current repository evidence is pilot-eligible.

Fixed boundary under test:

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
target_band=R0
```

## CI matrix

The repository CI matrix remains:

```text
Python 3.11
Python 3.13
Python 3.14
```

For every matrix entry CI executes:

```text
pip install -e .
python scripts/sync_package_assets.py
python -m unittest discover -s tests -v
urs version
urs validate-profile profiles/examples/journey-connect.yml
urs validate-profile profiles/examples/bejewely.yml
urs validate-profile profiles/examples/buildmap.yml
urs validate-profile profiles/examples/generic-webapp.yml
urs validate-findings examples/findings.sample.json
pip wheel . --no-deps --wheel-dir dist-ci
```

## Preliminary implementation CI

The initial Stage 10E implementation was validated on PR #22 by CI run #767 (`32091946830`).

All three Python jobs completed successfully, including full unittest discovery, package asset sync, existing `urs` regression validation, and wheel build.

That run is not the final documentation-inclusive authority because implementation-review hardening and documentation commits followed it.

The final authoritative exact-head run is recorded in PR #22 metadata after all implementation, tests, review fixes, and documents are frozen.

## Focused Stage 10E coverage

`tests/test_trust_pilot_review.py` covers:

- synthetic future evidence can reach only `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW`
- eligibility never changes `automation_authorized` or `pilot_authorized`
- current Independent Audit provenance gap fails closed
- source replay failure blocks eligibility
- observation false-negative evidence blocks eligibility
- cross-plane Registry identity mismatch blocks eligibility
- audit denominator projection mismatch blocks eligibility
- generation time cannot change evidence identity
- semantic rehash cannot convert a blocked report into an eligible report
- `pilot_authorized=true` cannot be accepted by rehashing the report
- output symlink rejection
- atomic replacement failure preserves existing bytes
- combined Stage 10B/10C/10D projection exposes the current Independent Audit provenance blocker

`tests/test_trust_pilot_review_hardening.py` additionally freezes implementation-review corrections:

- source replay repair outranks downstream audit-authority remediation when both fail
- `assessment_unreconciled_count > 0` independently breaks reconciliation completeness

## Source replay validation

Stage 10E does not create a weaker source verifier.

It delegates exact replay to the existing upstream semantic verifiers:

```text
Stage 10C verify_reconciliation_report_sources(...)
Stage 10D verify_report_sources(...)
```

Both are replayed against the same Stage 10B Registry path supplied to Stage 10E.

Therefore validation covers both:

1. detached Stage 10E semantic integrity
2. exact underlying evidence replay

The second is required before any future human pilot authorization decision.

## Schema asset validation

Root schema:

```text
schemas/r0-pilot-safety-review-report.schema.json
```

Package asset:

```text
src/review_system/assets/schemas/r0-pilot-safety-review-report.schema.json
```

are byte-identical. CI also executes `scripts/sync_package_assets.py`, so packaged schema divergence fails the repository diff/check discipline.

## Fail-closed structural validation

Current Stage 10C and Stage 10D contracts intentionally cannot satisfy full pilot eligibility simultaneously because:

```text
Stage 10D valid policy
  -> minimum_r0_independent_audit_count >= 1

Stage 10C current authority model
  -> INDEPENDENT_AUDIT = PROVENANCE_UNVERIFIED
  -> reconciled = false
```

Stage 10E validation therefore requires both:

```text
NO_CONCLUSIVE_PROVENANCE_UNVERIFIED
VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD
```

and confirms that the current gap resolves to:

```text
NOT_ELIGIBLE
ESTABLISH_INDEPENDENT_AUDIT_AUTHORITY
```

rather than silently weakening the audit threshold or treating self-asserted references as provenance.

## Regression boundary

Stage 10E does not modify:

- Stage 10A Trust classifier semantics
- Stage 10B Registry event semantics
- Stage 10C reconciliation status rules
- Stage 10D observation denominators or thresholds

It consumes those artifacts and adds a separate report-only composition gate.

## Terminal interpretation

A green Stage 10E CI means:

```text
Stage 10E implementation PASS
```

It does not mean:

```text
R0 pilot authorized
R0 pilot eligible under current evidence
R0 automation enabled
```

The next prerequisite exposed by the current contracts is an Independent Audit Authority Contract. Actual pilot activation remains a later, separately authorized operation.
