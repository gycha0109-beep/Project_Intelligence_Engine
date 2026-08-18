# PIE Stage 10D — Operating Observation & Threshold Policy

기준일: 2026-08-18  
선행 코드 기준선: PR #19 HEAD `c3a9facd6e2f530dfea069cb092636be734cee2e`  
작업 브랜치: `agent/stage-10d-operating-observation-threshold-policy`  
상태: `DESIGN_REVIEW_PASS`

## 1. 목적

Stage 10B의 Trust comparison registry에서 실제 관찰 표본을 읽어, **R0 pilot 안전 검토를 논의할 만큼 운영 증거가 성숙했는지** versioned threshold policy로 평가한다.

이번 Stage는 자동화 activation Stage가 아니다. 모든 결과는 report-only이며 다음 값은 항상 고정한다.

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
target_band=R0
```

Threshold를 모두 만족하더라도 결과는 자동 PASS나 pilot authorization이 아니라 `THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION`이다. 별도 source reconciliation과 별도 R0 pilot safety review가 완료되기 전에는 pilot을 시작하지 않는다.

## 2. Migration Plan과의 관계

원래 Stage 10 계획은 다음 순서다.

1. report-only risk band
2. human-confirmed decision comparison
3. R0 auto-pass pilot
4. R1 conditional auto-approval
5. override audit

Stage 10C/10D는 2와 3 사이의 안전 경계를 더 세분화한다. Stage 10D evaluator 자체는 Stage 10B의 self-verified registry만 읽으므로 먼저 구현할 수 있다. 그러나 **Stage 10C source reconciliation이 없으면 Stage 10D 결과가 pilot authorization으로 이어질 수 없다.**

## 3. Threshold Policy Contract

Schema:

```text
schemas/trust-observation-policy.schema.json
schemas/trust-observation-report.schema.json
```

Policy는 실행 권한이 아니라 관찰 충분성 기준만 정의한다.

필수 threshold:

- `minimum_r0_assessment_count`
- `minimum_r0_reviewed_count`
- `minimum_r0_conclusive_outcome_count`
- `minimum_r0_confirmed_safe_count`
- `minimum_confirmed_unsafe_challenge_count`
- `minimum_r0_independent_audit_count`
- `minimum_r0_outcome_coverage`
- `minimum_r0_evidence_span_days`
- `maximum_r0_false_negatives`
- `maximum_r0_false_negative_rate`

Stage 10D는 조직의 적정 표본 수·기간·coverage 값을 자동 추천하거나 자동 완화하지 않는다. 숫자는 explicit policy input이다.

단, trivially unsafe policy를 막기 위한 structural floor는 코드·schema가 강제한다.

- 모든 minimum count는 1 이상
- `minimum_r0_outcome_coverage`는 0 초과 1 이하
- `minimum_r0_evidence_span_days`는 1 이상
- `maximum_r0_false_negatives`는 반드시 0
- `maximum_r0_false_negative_rate`는 반드시 0.0

따라서 R0 pilot 검토 policy 자체가 **관찰된 R0 미탐을 허용**하도록 설정되는 것은 불가능하다.

`examples/trust-observation-policy.sample.json`의 숫자는 CLI·schema 사용 예시를 위한 **비규범적 샘플**이다. 조직 기준, 권고 threshold, 자동화 승인 기준으로 해석하지 않는다.

## 4. 관찰 대상

Stage 10D에는 서로 다른 두 종류의 표본이 필요하다.

### R0 safe cohort

`predicted_risk_band=R0`인 assessment에서 다음을 계산한다.

- assessment count
- `REVIEWED`/`AUDITED` count
- conclusive Outcome count
- confirmed SAFE count
- independent Audit count
- Outcome coverage
- evidence span
- reviewer alignment(정보용)

사람 decision 수준은 Stage 10B 계약을 그대로 따른다.

- `WORKFLOW_ACCEPTED`: reviewed count에서 제외
- `REVIEWED`: reviewed count에는 포함하지만 ground truth가 아님
- `AUDITED`: reviewed count에 포함

### confirmed unsafe challenge cohort

R0만 보아서는 "실제로 위험한 사례를 R0 밖으로 밀어낼 수 있는가"를 검증할 수 없다. 따라서 `outcome_verdict=UNSAFE`인 **모든 band의 conclusive Outcome**을 challenge denominator로 사용한다.

```text
predicted R0   + actual SAFE   = R0 TN
predicted R0   + actual UNSAFE = R0 FN
predicted > R0 + actual UNSAFE = R0 TP
predicted > R0 + actual SAFE   = R0 FP
```

여기서 TP/FP/TN/FN은 전체 Trust classifier의 일반 confusion matrix가 아니라 **R0 auto-pass boundary만을 위한 binary projection**이다.

## 5. 미탐 분모 방어

단순히 `r0_false_negative=0`만 확인하면 실제 unsafe 표본이 한 건도 없는 데이터에서도 완벽해 보일 수 있다.

따라서 반드시 다음 두 축을 동시에 요구한다.

```text
r0_confirmed_safe_count >= minimum_r0_confirmed_safe_count
confirmed_unsafe_challenge_count >= minimum_confirmed_unsafe_challenge_count
```

R0 false-negative rate는 다음처럼 계산한다.

```text
r0_false_negative_rate = R0_FN / (R0_TP + R0_FN)
```

즉 confirmed unsafe challenge가 0이면 분모가 0이므로 `null`이다. `null`은 `maximum_r0_false_negative_rate=0.0`을 만족하지 못한다.

Controlled Evaluation, independent Audit, production Defect, Regression, Security Incident 등 Stage 10B의 conclusive Outcome이 challenge evidence가 될 수 있다.

## 6. Evidence Span

수동 `generated_at`이나 단순 wall-clock 경과로 관찰 기간을 부풀리지 않는다.

`r0_evidence_span_days`는 R0 assessment 및 그 assessment에 연결된 decision/outcome event의 실제 timestamp 범위로 계산한다.

```text
max(R0 evidence timestamps) - min(R0 assessment captured_at)
```

보고서를 1년 뒤 다시 생성하더라도 evidence span은 늘어나지 않는다.

## 7. 평가 상태

- `INSUFFICIENT_EVIDENCE`
  - 필수 denominator 없음
  - minimum threshold 미달
  - FNR denominator가 없어 `null`
- `THRESHOLD_BLOCKED`
  - 관찰된 R0 false negative가 1건 이상
  - R0 FNR이 허용치 0.0 초과
- `THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION`
  - observation threshold는 모두 충족
  - 그러나 source reconciliation 및 별도 pilot safety review가 아직 필요

어떤 상태에서도 automation 또는 pilot을 authorize하지 않는다.

## 8. Report 구조

Report에는 다음을 보존한다.

- registry ID/hash
- derived policy ID/version/hash
- embedded threshold snapshot
- target band `R0`
- R0 safe cohort metrics
- all-band confirmed unsafe challenge count
- R0 boundary TP/FP/TN/FN
- R0 false-negative rate
- reviewer alignment rate(정보용)
- 10개 고정 threshold check의 actual/required/pass
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
pie-trust verify-observation-report \
  --report <report.json> \
  --registry <registry.json> \
  --policy <policy.json>
```

별도 entry point:

```text
pie-trust-observation
```

## 10. Identity / Integrity

- policy ID와 SHA-256은 semantic policy body에서 deterministic 생성
- report는 policy threshold snapshot을 내장하고 self-contained 재검산
- report ID는 project + registry identity + policy identity로 deterministic 생성
- threshold check set/order, status, blocker, next step을 재계산
- internal observation arithmetic와 denominator를 재계산
- optional source replay 시 현재 Stage 10B registry와 policy에서 report 전체를 재생성해 exact match 확인
- root/package schema asset drift regression 유지
- symlink input/output 거부
- atomic temp + fsync + replace write

## 11. 하지 않는 것

- R0 auto-pass 실행
- GitHub approve/merge/comment/label
- R1 conditional approval
- threshold 값 자동 추천 또는 자동 완화
- reviewer alignment를 ground truth로 사용
- Outcome 없는 사례를 SAFE로 취급
- source reconciliation을 완료했다고 추정
- Stage 10C 기능을 우회 구현
- Defect Registry 존재성 자동 검증
- Ledger migration

## 12. 완료 기준

- R0 safe cohort와 all-band unsafe challenge cohort를 구분한다.
- `WORKFLOW_ACCEPTED`가 reviewed 분모에 들어가지 않는다.
- R0 confirmed SAFE와 confirmed unsafe challenge 양쪽 표본이 없으면 readiness가 성립하지 않는다.
- unsafe challenge denominator 0이면 R0 FNR은 null이며 PASS 불가다.
- `predicted R0 + actual UNSAFE`가 1건이라도 있으면 `THRESHOLD_BLOCKED`다.
- policy는 R0 FN/FNR 허용치를 0보다 크게 설정할 수 없다.
- generated time 변경으로 evidence span을 늘릴 수 없다.
- threshold 만족 상태도 `pilot_authorized=false`다.
- source reconciliation이 pilot 전 별도 선행조건으로 고정된다.
- embedded-policy tamper, re-hash, source mismatch, symlink, atomic replace failure가 fail closed다.
- Python 3.11·3.13·3.14 전체 회귀와 wheel build가 통과한다.
