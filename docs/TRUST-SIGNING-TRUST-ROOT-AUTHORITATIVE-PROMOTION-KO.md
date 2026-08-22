# Signing Trust-Root R3 Authoritative Promotion

> Status: **IN PROGRESS — exact-head CI pending**
>
> This document records the bounded promotion of the already-calibrated signing trust-root R3 discriminator. It does not authorize PR merge, automation, pilot execution, Stage10K human decision, blind generalization, or Production Execution Boundary remediation.

## 1. Starting authority

```text
Shadow calibration PR = #56
Shadow HEAD = 8a24e009c25c252d97dffe5c5b13f2385a6b7afd
Shadow exact-head CI = #1277 / 32548898359 / SUCCESS
Shadow merge main = f8a04a2f0565df2449f58be0a43c42675876d806

Authoritative promotion PR = #57
Base main = f8a04a2f0565df2449f58be0a43c42675876d806
Trust target = v1.5
```

PR #56 landed only the calibrated shadow dependency. PR #57 is a separately versioned authoritative promotion and remains Draft / Open / Unmerged until a later explicit merge authorization.

## 2. Promotion boundary

The shadow-calibrated semantic boundary is unchanged:

```text
signature-verification trust material
+
signing / verification / updater trust context
+
production / release / updater operational context
+
concrete trust-root / public verification key assignment
+
runtime or configuration surface
=
R3 signing trust-root authority candidate
```

Authoritative use additionally requires source-bound evidence tied to the exact GitHub PR source and diff.

## 3. Source-bound authority evidence

`TRUST_SIGNING_TRUST_ROOT_AUTHORITY_V1` binds the semantic result to:

- exact PR head revision,
- exact changed-file set,
- GitHub source evidence SHA,
- full diff SHA-256 and byte length,
- exact per-file diff section,
- per-file patch SHA-256,
- canonical evidence fingerprint.

A source pair mismatch, changed-file mismatch, diff mutation, missing section, or evidence fingerprint mutation fails closed.

The semantic discriminator is implemented in a pure repository-neutral module so the authoritative path does not depend on the shadow module or repository identity.

## 4. Risk-model versioning

```text
v1.1 = historical
v1.2 = generic-policy-token correction
v1.3 = source-bound R4 semantic authority
v1.4 = executable acceptance verifier-role authority
v1.5 = signing trust-root R3 authority
```

v1.4 remains explicitly available as `TRUST_RISK_MODEL_V1_4`.

Existing v1.3 and v1.4 reports/replay remain historical. Signing trust-root evidence is accepted only by v1.5.

The existing R4 semantic contract is unchanged. v1.5 reuses the v1.4 R4 contract and does not expand R4 authority.

## 5. Calibration anchors

Known positive MasterV PR #3 remains one observed signing-key rotation event with two relevant surfaces:

```text
src-tauri/src/updater.rs
v1.4 = R2
v1.5 candidate = R3

src-tauri/tauri.windows-independent-updater-release.conf.json
v1.4 = R2
v1.5 candidate = R3
```

Controls remain non-promoted:

```text
same-PR supporting contract     = NO PROMOTION
documentation signing text      = NO PROMOTION
test-only verification key      = NO PROMOTION
ordinary application crypto key = NO PROMOTION
example/dev updater config      = NO PROMOTION
```

The repository-neutral synthetic trust-root assignment remains a genericity control only. It is not independent real-world evidence.

## 6. Hard-gate behavior

Authoritative signing trust-root mutation uses reason:

```text
SEMANTIC_R3_SIGNING_TRUST_ROOT_AUTHORITY
```

That reason is included in the existing high-risk hard-gate set. Therefore a source-bound R3 signing trust-root mutation receives the existing human-approval treatment instead of merely changing the descriptive band.

## 7. CI remediation history

Initial authoritative wiring exposed a circular import:

```text
trust
→ trust_signing_trust_root_authority
→ trust_signing_trust_root_shadow
→ trust
```

CI #1284 failed during test import. The fix extracted a pure semantics module consumed independently by shadow and authority paths.

A later full-suite diagnostic reached 605 tests and found four stale v1.4 expectations only. No signing-discriminator assertion failed. Those tests were corrected so historical v1.3/v1.4 replay uses explicit version constants while current-model assertions target v1.5.

Temporary diagnostic workflows, diagnostic output, and temporary CI modifications were removed after diagnosis.

## 8. Explicit non-actions

```text
PRODUCTION_EXECUTION_BOUNDARY_GAP = UNTOUCHED
existing R4 semantic criteria     = UNCHANGED
repository-name heuristic         = NO
automation_authorized             = false
pilot_authorized                  = false
Stage10K HUMAN_DECISION           = NO
blind generalization              = NO
PR57_MERGE                        = NOT_AUTHORIZED
```

## 9. Closure status

This document is provisional until a normal user-authored promotion HEAD and the final documentation HEAD both pass exact-head CI across Python 3.11, 3.13, and 3.14 with the full validation chain.
