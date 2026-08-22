# Trust R4 Semantic Underdetection Shadow Calibration

## 상태

`R4_SEMANTIC_UNDERDETECTION_SHADOW_V1`

이 문서는 authoritative Trust risk model을 변경하지 않는다. 현재 authority는 main `e5cb12b902baa1579253714922d099a74705fae2`, Trust risk model v1.2이다.

## 문제

현재 R4 path classifier는 소수의 파일명/경로(`trust.py`, `gate.py`, `evaluation.py`, `policy_registry.py`, `/verification/`, `/policies/` 등)를 R4로 분류한다. 따라서 실제 산출물이 verifier/policy/evaluation authority 자체여도 일반적인 `lib/*.js`, `scripts/*.mjs` 경로이면 R2/R3에 머물 수 있다.

Wave 1 human labels에는 실제 R4 seen 사례가 존재한다.

- KB-262: exact-main replay gate/verifier 자체
- KB-272: reassessment sufficiency policy evaluator
- KB-277: calibration methodology evaluator
- KB-279: normative acceptance evaluator
- AR-30: live verification harness 자체

Wave 1 frozen holdout에는 독립 R4 sample이 없으므로 이 Stage는 blind R4 generalization을 주장하지 않는다.

## Shadow semantic classes

### `NORMATIVE_DECISION_AUTHORITY`

다음을 함께 요구한다.

- executable `evaluate*` function
- normative/policy/methodology/acceptance/sufficiency authority marker
- 적어도 두 개의 decision-output marker
  - `decision_state`
  - `governance_state`
  - `execution_state`
  - `ready_for_*`
  - `promotion_rule` / `promotion_gate`
  - `hard_blocker`
  - `enforce_authorized`

### `EXECUTABLE_VERIFICATION_GATE_AUTHORITY`

다음 중 하나를 요구한다.

1. explicit `gate:` / `...GATE = ...` / `BLOCKED_*` outcome + executable assertions + fail-closed behavior
2. `live-verification` role + live/persisted evidence operation + executable assertions + fail-closed behavior

일반적인 `PASS` 로그 문자열 하나는 gate authority signal이 아니다.

### `SUPPORTING_EVALUATION_ONLY`

Synthetic/diagnostic/evaluation-only authority ceiling이 코드 자체에 명시된 harness이다. 예: EVAL-P3 persona simulation. 이런 harness는 production policy/verifier authority로 승격하지 않는다.

### `SUPPORTING_REGRESSION_ONLY`

제품/domain logic의 regression assertion을 수행하지만 별도 governance/gate authority outcome을 만들지 않는 supporting verifier이다. 예: RW-54 IA-1 contract verifier.

### `UNKNOWN`

R4 authority가 충분히 입증되지 않은 경우이다. UNKNOWN은 이 shadow v1에서 R4로 승격하지 않는다.

## Seen calibration cases

Positive R4:

- KB-262 → `EXECUTABLE_VERIFICATION_GATE_AUTHORITY`
- KB-272 → `NORMATIVE_DECISION_AUTHORITY`
- KB-277 → `NORMATIVE_DECISION_AUTHORITY`
- KB-279 → `NORMATIVE_DECISION_AUTHORITY`
- AR-30 → `EXECUTABLE_VERIFICATION_GATE_AUTHORITY`

Negative controls:

- RW-54 → `SUPPORTING_REGRESSION_ONLY`
- KB-275 → `SUPPORTING_EVALUATION_ONLY`
- docs verification text → `UNKNOWN`
- ordinary domain candidate-policy → `UNKNOWN`

## Evidence boundary

Fixture는 frozen PR head/path와 classifier 결정을 재생하는 exact source/patch excerpt를 보존한다. 전체 PR patch byte-for-byte 보존물이 아니므로 이 Stage는 excerpt-bounded semantic calibration이다.

## Risk shadow bridge

R4 positive semantic evidence가 있는 changed path에 대해서만 shadow candidate path floor를 R4로 올린다.

- authoritative `_risk_projection()`은 변경하지 않는다.
- `mode=REPORT_ONLY`
- `authority=SHADOW_ONLY`
- `automation_authorized=false`
- `pilot_authorized=false`

## Regression requirements

- 5개 real seen R4 positive 모두 semantic R4
- RW-54 / KB-275 / domain-policy negative control은 semantic R4 아님
- 일반 PASS 출력만으로 R4 승격 금지
- Wave 1 authoritative v1.2 34개는 34/34 acceptable, underclassification 0 유지
- 새로운 blind R4 generalization claim 금지

## 아직 해결하지 않는 것

- source-bound full-diff runtime evidence contract
- `trust.py` authoritative R4 promotion
- PIE 내부 evidence-authority helper의 별도 call-graph 분류
- MasterV-specific high-risk semantic blind spot
- automation/pilot authorization
- Stage10K HUMAN_DECISION
