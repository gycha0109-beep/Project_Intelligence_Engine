# PIE Stage 10D — Operating Observation & Threshold Policy

기준일: 2026-08-18  
선행 코드 기준선: PR #19 HEAD `c3a9facd6e2f530dfea069cb092636be734cee2e`  
작업 브랜치: `agent/stage-10d-operating-observation-threshold-policy`  
상태: `DESIGN_REVIEW_PASS`

## 1. 목적

Stage 10B의 Trust comparison registry에서 실제 관찰 표본을 읽어, **R0 pilot 검토를 논의할 만큼 운영 증거가 성숙했는지** versioned threshold policy로 평가한다.

이번 Stage는 자동화 activation Stage가 아니다. 모든 결과는 report-only이며 다음 값은 항상 고정한다.

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
target_band=R0
```

Threshold를 모두 만족하더라도 결과는 자동 PASS가 아니라 `THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION`이다. 별도 source reconciliation과 R0 pilot safety review가 완료되기 전에는 pilot을 시작하지 않는다.

## 2. Migration Plan과의 관계

원래 Stage 10 계획은 다음 순서다.

1. report-only risk band
2. human-confirmed decision comparison
3. R0 auto-pass pilot
4. R1 conditional auto-approval
5. override audit

Stage 10C/10D는 이 경계를 더 안전하게 분해한 후속 단계다. 10D evaluator 자체는 Stage 10B의 self-verified registry만 읽으므로 구현 가능하지만, **10C source reconciliation이 없으면 pilot authorization으로 이어질 수 없다.**

## 3. Threshold Policy Contract

새 schema:

```text
schemas/trust-observation-policy.schema.json
schemas/trust-observation-report.schema.json
```

Policy는 실행 권한이 아니라 관찰 충분성 기준만 정의한다.

필수 threshold:

- `minimum_assessment_count`
- `minimum_reviewed_count`
- `minimum_conclusive_outcome_count`
- `minimum_confirmed_safe_count`
- `minimum_confirmed_unsafe_count`
- `minimum_independent_audit_count`
- `minimum_outcome_coverage`
- `minimum_evidence_span_days`
- `maximum_confirmed_false_negatives`
- `maximum_false_negative_rate`

Stage 10D는 숫자 자체를 조직 정책으로 임의 확정하지 않는다. Threshold 값은 explicit policy input이어야 한다.

단, policy 자체가 trivially unsafe해지는 것을 막기 위해 다음 structural floor를 적용한다.

- 모든 minimum count는 1 이상
- `minimum_outcome_coverage`는 0 초과 1 이하
- `minimum_evidence_span_days`는 1 이상
- `maximum_confirmed_false_negatives`는 Stage 10D에서 반드시 0
- `maximum_false_negative_rate`는 Stage 10D에서 반드시 0.0

즉 R0 pilot 검토를 위한 policy가 "관찰된 미탐을 허용"하도록 설정되는 것은 허용하지 않는다.

## 4. 관찰 대상과 분모

Stage 10D는 `predicted_risk_band=R0`인 assessment만 대상으로 한다.

사람 decision 수준은 Stage 10B 계약을 그대로 따른다.

- `WORKFLOW_ACCEPTED`: reviewed count에서 제외
- `REVIEWED`: reviewed count에 포함하지만 ground truth가 아님
- `AUDITED`: reviewed count에 포함

Confirmed outcome은 Stage 10B의 conclusive 상태만 사용한다.

- `CONFIRMED_TRUE_NEGATIVE`
- `CONFIRMED_FALSE_NEGATIVE`
- `CONFIRMED_TRUE_POSITIVE`
- `CONFIRMED_FALSE_POSITIVE`

`UNCONFIRMED`와 `CONFIRMED_INCONCLUSIVE`는 정확도·FNR 분모에 들어가지 않는다.

## 5. 미탐 분모 방어

단순히 `false_negative_count=0`만 확인하면 unsafe 사례가 한 건도 없는 데이터에서도 완벽해 보일 수 있다.

따라서 policy는 반드시 다음 두 표본을 모두 요구한다.

```text
confirmed_safe_count >= minimum_confirmed_safe_count
confirmed_unsafe_count >= minimum_confirmed_unsafe_count
```

`false_negative_rate`의 분모인 confirmed unsafe 표본이 0이면 metric은 `null`이며 threshold PASS가 될 수 없다.

Controlled Evaluation, independent Audit, production Defect 등 Stage 10B Outcome이 이 unsafe 표본을 공급할 수 있다.

## 6. Evidence Span

수동 `generated_at`이나 단순 wall-clock 경과로 관찰 기간을 부풀리지 않는다.

`evidence_span_days`는 R0 assessment 및 연결된 decision/outcome event의 **실제 evidence timestamp 범위**로 계산한다.

```text
max(evidence timestamps) - min(R0 assessment captured_at)
```

R0 assessment가 하나뿐이거나 실제 evidence event가 같은 시점에 몰려 있으면 0일이며 threshold를 만족할 수 없다.

## 7. 평가 상태

출력 상태:

- `INSUFFICIENT_EVIDENCE`
  - 필수 분모가 없거나 minimum threshold 미달
- `THRESHOLD_BLOCKED`
  - 관찰된 false negative가 1건 이상이거나 FNR 한도 초과
- `THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION`
  - 모든 observation threshold는 충족했으나 source reconciliation 및 별도 pilot safety review 필요

어떤 상태에서도 automation 또는 pilot을 authorize하지 않는다.

## 8. Report 구조

Report는 다음을 포함한다.

- registry ID/hash
- policy ID/version/hash
- target band `R0`
- R0 assessment count
- reviewed count
- conclusive outcome count
- safe/unsafe confirmed sample count
- independent Audit count
- outcome coverage
- evidence span days
- TP/FP/TN/FN
- false-negative rate
- reviewer alignment rate는 정보용으로만 표시
- threshold check별 actual/required/pass
- blockers
- fixed source-reconciliation requirement
- report ID/hash

Reviewer alignment는 safety threshold로 사용하지 않는다.

## 9. CLI

```text
pie-trust verify-observation-policy --policy <policy.json>
pie-trust observe-readiness \
  --registry <trust-comparison-registry.json> \
  --policy <trust-observation-policy.json> \
  --output <trust-observation-report.json>
pie-trust verify-observation-report --report <report.json>
pie-trust verify-observation-report --report <report.json> --registry <registry.json> --policy <policy.json>
```

별도 entry point:

```text
pie-trust-observation
```

## 10. Identity / Integrity

- policy ID는 semantic policy body에서 deterministic 생성
- policy SHA-256 재계산
- report ID는 project + registry identity + policy identity로 deterministic 생성
- report semantic projection 재계산
- optional source replay 시 registry/policy hash와 metrics를 다시 평가
- root/package schema asset drift test 유지
- symlink input/output 거부
- atomic fsync+replace output

## 11. 하지 않는 것

- R0 auto-pass 실행
- GitHub approve/merge/comment/label
- R1 conditional approval
- Threshold 값 자동 추천 또는 자동 완화
- reviewer alignment를 ground truth로 사용
- Outcome 없는 사례를 SAFE로 취급
- source reconciliation을 했다고 추정
- Stage 10C 기능을 이 Stage에서 우회 구현
- Defect Registry 존재성 자동 검증
- Ledger migration

## 12. 완료 기준

- R0만 집계한다.
- `WORKFLOW_ACCEPTED`가 reviewed 분모에 들어가지 않는다.
- confirmed safe/unsafe 양쪽 표본이 없으면 readiness가 성립하지 않는다.
- unsafe denominator 0이면 FNR은 null이며 PASS 불가다.
- observed FN > 0이면 반드시 `THRESHOLD_BLOCKED`다.
- policy는 observed FN/FNR 허용치를 0보다 크게 설정할 수 없다.
- generated time 변경으로 evidence span을 늘릴 수 없다.
- threshold 만족 상태도 `pilot_authorized=false`다.
- source reconciliation이 별도 선행조건으로 명시된다.
- tamper/re-hash/source mismatch/symlink/atomic failure가 fail closed다.
- Python 3.11·3.13·3.14 전체 회귀와 wheel build가 통과한다.
