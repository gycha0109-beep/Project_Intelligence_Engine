# PIE Trust/Risk Calibration Wave 1B — Seen Baseline Replay

Status: **SEEN BASELINE REPLAY FROZEN / HOLDOUT UNTOUCHED**

## 1. Authority

This baseline is evaluated against the exact PIE authority frozen by Wave 1A:

- repository: `gycha0109-beep/Project_Intelligence_Engine`
- main: `96b053f63a25465a4e75e58d755a62462b20ee68`
- tree: `478e938fafa800d410ca9bf25b45ee03a1557967`
- Wave 1A freeze commit: `c599f53f12bb9e8218b472752b3a8039f48413fb`
- Wave 1A Draft PR: `#40`

No classifier, review-pack selector, profile, threshold, automation, pilot, Stage10K decision, or Factory Intelligence scope is changed here.

## 2. Scope

Wave 1B replays only samples that were already exposed before the Wave 1A freeze:

- `calibration_seen`: 13
- `seen_validation`: 10
- total: 23

Explicitly not replayed:

- `frozen_holdout`: 11
- `external_seen_probe`: 5

This is a **risk-band-only** replay using the current `_risk_projection` contract. It is not a full Trust readiness decision, merge authorization, pilot authorization, or human decision.

## 3. Replay input policy

Caller-declared `task_class` is frozen from the primary PR intent before comparing the projection to the human-prior band:

- `documentation`: documentation-only PR
- `verifier`: the PR product is the verifier/gate authority itself
- `policy`: the PR product is the normative/governance policy evaluator itself
- `routine_code`: all other application/runtime/harness/migration work

The last rule is deliberate. Migration/auth/security elevation must be corroborated by the current PIE path/review-pack semantics rather than manually declaring every high-risk PR upward.

A PR merely containing a regression verifier does **not** receive task class `verifier`.

## 4. Result

| Metric | Result |
| --- | ---: |
| Seen samples | 23 |
| Exact expected-band matches | 21 / 23 |
| Acceptable-band matches | 22 / 23 |
| Under-classifications | 0 |
| Over-classifications vs preferred expected band | 2 |
| Unacceptable mismatches | 1 |

### Calibration partition

- exact preferred-band: **12 / 13**
- unacceptable mismatch: **RW-54**

### Seen-validation partition

- exact preferred-band: **9 / 10**
- acceptable-band: **10 / 10**
- boundary case: **KB-275**

## 5. D1 confirmed — blanket workflow floor over-elevates ordinary product logic

`RW-54` is the decisive failure.

Human-prior authority:

- expected: `R2`
- acceptable: `R2` only
- primary task: deterministic ranking-neighborhood domain algorithm
- regression verifier and CI wiring are supporting controls
- no migration
- no auth/security authority mutation
- no deployment/release authority mutation

Changed files include:

- `.github/workflows/ci.yml`
- `package.json`
- `scripts/verify-ia-1-contracts.mjs`
- `src/lib/queries/public.ts`
- `src/lib/ranking-neighborhood.ts`

Current PIE result:

- declared task class: `routine_code`
- path floor: `R3`
- effective risk: `R3`
- sole maximum path-floor contributor: `.github/workflows/ci.yml`

Current `trust.py` classifies every `.github/workflows/**` path as `HIGH_RISK_PATH` / R3. Therefore an ordinary R2 product change becomes R3 merely because its regression verifier is wired into CI.

This is not a hypothetical concern. It is now reproduced by a frozen real PR.

## 6. Boundary case — KB-275

`KB-275` also projects:

- preferred human band: `R2`
- frozen acceptable band: `R2` or `R3`
- PIE: `R3`

Its maximum floor is likewise the workflow path:

- `.github/workflows/eval-p3-persona-simulation.yml`

Unlike `RW-54`, the frozen human prior already classified this deterministic evaluation harness as an R2/R3 boundary. It is therefore **not** counted as an unacceptable failure, but it is a useful validation case for any future workflow-floor remediation.

## 7. What did not fail

The same current rules correctly preserve the major distinctions in the seen corpus:

- BuildMap #65 provider runtime remediation without migration: `R2`
- BuildMap #53/#59 provider OAuth/credential work with migrations: `R3`
- docs-only governance artifacts such as BuildMap #46 and K_beauty #273: `R1`
- K_beauty #262 verifier authority: `R4`
- K_beauty #272/#277/#279 policy authority: `R4`
- migrated publication/control-plane work in RankingWiki: `R3`
- RankingWiki #56 ordinary product logic + regression verifier without workflow/migration: `R2`

No seen sample is under-classified relative to the frozen preferred band.

## 8. R4 interpretation ceiling

The seen replay does **not** prove that arbitrary project file paths can infer R4 semantics.

The R4 samples are correctly classified because their primary PR intent is explicitly declared as `verifier` or `policy`. This distinction is intentional and must not be rewritten as a claim that filename/path heuristics independently discover all external policy authorities.

Wave 1 still has no independent frozen R4 holdout sample.

## 9. Next bounded task

The evidence justifies one narrow calibration candidate:

> Replace unconditional `.github/workflows/** -> R3` treatment with semantics that preserve R3 for deployment/release/security/credential/permission/control-plane workflows while allowing ordinary CI regression wiring to remain at the surrounding task risk.

Any remediation must be developed against `calibration_seen` first. `seen_validation` is validation evidence, not a tuning target. The frozen holdout remains unread by PIE until the remediation protocol is frozen and separately authorized for holdout evaluation.

No remediation is implemented by this Wave 1B evidence commit.
