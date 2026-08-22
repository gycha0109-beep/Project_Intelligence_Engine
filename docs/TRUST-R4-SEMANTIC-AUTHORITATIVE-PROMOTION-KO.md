# Trust R4 Semantic Authority — Authoritative Promotion

## Status

- defect: `R4_SEMANTIC_UNDERDETECTION`
- shadow contract: `TRUST_R4_SEMANTIC_UNDERDETECTION_SHADOW_V1`
- promoted Trust risk model: `1.3`
- authority mode: `REPORT_ONLY`
- `automation_authorized = false`
- `pilot_authorized = false`
- blind R4 holdout: **not available**
- blind R4 generalization claim: **not made**

이 문서는 PR #51에서 검증된 R4 semantic discriminator를 Trust authoritative risk projection에 승격하는 bounded promotion을 기록합니다.

## 1. Promotion boundary

이번 변경은 path/name inventory만으로 잡히지 않는 실제 verifier/policy authority를 source-bound semantic evidence가 입증할 때만 R4로 승격합니다.

다음은 이번 범위가 아닙니다.

- MasterV/project-specific high-risk blind spot remediation
- generic policy-token collision 재설계
- workflow semantics 재설계
- 새로운 hard-gate 추가
- profile / review-pack selector 확장
- automation 또는 pilot authorization
- Stage10K HUMAN_DECISION

## 2. Risk model versioning

- `1.1`: historical model
- `1.2`: D1/documentation/D2까지 포함한 이전 authoritative model
- `1.3`: source-bound R4 semantic authority를 추가한 현재 promotion model

R4 semantic evidence는 `1.3`에서만 authoritative input으로 허용합니다. `1.2` replay에 R4 semantic evidence를 주입하면 fail closed로 거부합니다.

`1.2`의 generic policy-token correction은 `1.3`에서도 그대로 보존합니다.

## 3. Source-bound evidence contract

새 evidence module:

`src/review_system/trust_r4_semantics_authority.py`

외부 입력 surface는 추가하지 않습니다. 기존 Trust source pair를 재사용합니다.

- `--github-source`
- `--workflow-diff`

동일 source pair에서 다음을 검증합니다.

1. GitHub source schema validity
2. Trust request `source_revision`과 PR exact head 일치
3. Trust request `changed_files`와 GitHub source changed-files exact match
4. full diff SHA-256 일치
5. full diff byte length 일치
6. per-file diff section 분리
7. 모든 changed file에 대한 diff section exact coverage
8. 각 file patch SHA-256 기록
9. semantic evidence canonical fingerprint 기록

따라서 filename/path token만으로 semantic R4 authority를 생성하지 않습니다.

## 4. Authoritative classifications

PR #51에서 검증된 semantic contract를 그대로 사용합니다.

- `NORMATIVE_DECISION_AUTHORITY`
- `EXECUTABLE_VERIFICATION_GATE_AUTHORITY`
- `SUPPORTING_EVALUATION_ONLY`
- `SUPPORTING_REGRESSION_ONLY`
- `UNKNOWN`

R4 authority로 인정되는 것은 앞의 두 class뿐입니다.

일반 `PASS` 로그, 단순 regression assertion, synthetic/evaluation-only harness는 R4 authority의 충분조건이 아닙니다.

## 5. Risk projection

`_risk_projection()`은 v1.3에서 source-bound R4 evidence를 선택적으로 받습니다.

해당 path에 `is_r4_authority = true`가 검증되면:

- path floor = `R4`
- reason = `SEMANTIC_R4_AUTHORITY`
- effective band는 최소 `R4`
- task class가 더 낮게 선언되었으면 기존 `TASK_CLASS_UNDERDECLARED` semantics가 그대로 적용됩니다.

R4 evidence가 없거나 semantic authority가 입증되지 않으면 기존 workflow/path/review-pack projection을 그대로 사용합니다.

## 6. Evidence persistence and replay

Trust report의 `evidence`에는 선택적으로 다음이 추가됩니다.

`r4_semantics`

이 evidence는 기존 fingerprint payload에 포함됩니다. `verify_trust_report_data()`는 canonical form과 fingerprint를 재계산하며, `verify_trust_report_sources()`는 동일 GitHub source/full diff pair로 assessment를 재실행합니다.

따라서 diff tamper, head mismatch, changed-files mismatch 또는 evidence mutation은 replay/verification에서 거부됩니다.

## 7. Calibrated evidence ceiling

현재 real seen positive는 다음 5개입니다.

- KB-262 — executable exact-main replay gate
- KB-272 — normative reassessment sufficiency evaluator
- KB-277 — normative calibration methodology evaluator
- KB-279 — normative acceptance evaluator
- AR-30 — live verification harness

PR #51 shadow calibration에서 5/5가 semantic R4 authority로 판별되었습니다.

Negative controls:

- RW-54 — supporting regression only
- KB-275 — supporting evaluation only
- documentation verification text — non-authoritative
- ordinary domain `candidate-policy` — non-authoritative

Wave 1에는 independent R4 holdout이 없습니다. 따라서 이 promotion은 **seen-calibrated bounded promotion**이며 blind R4 generalization을 주장하지 않습니다.

## 8. Regression requirements

Promotion acceptance에는 최소 다음을 요구합니다.

- real seen R4 positives: 5/5 authoritative R4
- negative controls: semantic R4 미승격
- source binding tamper tests: reject
- v1.2 replay compatibility 유지
- generic-policy D2 correction 유지
- Wave 1 historical regression: 34/34 acceptable
- Wave 1 underclassification: 0
- Python 3.11 / 3.13 / 3.14 full CI success

## 9. Governance boundary

이 promotion은 risk classification authority만 변경합니다.

- 새로운 hard gate를 추가하지 않습니다.
- `REPORT_ONLY`를 변경하지 않습니다.
- 자동 통과를 허용하지 않습니다.
- automation/pilot을 authorize하지 않습니다.
- CI success는 merge authorization이 아닙니다.
- merge는 Stage10K HUMAN_DECISION이 아닙니다.

현재 promotion PR은 Draft / verification 대상이며, 별도의 명시적 merge 승인 전에는 merge하지 않습니다.
