# PIE Stage 10A — Trust Gate Readiness

기준일: 2026-07-25  
선행 기준선: PR #17 HEAD `cf4732bd78ca6d1e7ab78c44d0719285331d6803`  
작업 브랜치: `agent/stage-10a-trust-gate-readiness`  
상태: `DESIGN_REVIEW_PASS`

## 1. 목적

Stage 10의 첫 단계로 Trust Gate를 **report-only** 모드로 도입한다.

이번 단계는 다음 두 질문에만 답한다.

1. 현재 작업은 어느 Risk Band에 속하는가.
2. PIE가 다음 단계인 human-confirmed decision comparison을 시작할 만큼 운영 근거를 확보했는가.

자동 승인, 자동 merge, 기존 Gate 차단, GitHub write 동작은 구현하지 않는다.

```text
Task Request
+ Project Profile
+ Evidence Ledger
+ Defect Registry projection
+ Active Policy and Evaluation
+ Reground report and human observations
→ deterministic Risk Band
→ hard-gate advisory
→ readiness evidence report
```

## 2. 권위 기준

- `TARGET-STATE.md`의 Trust Gate hard gate와 R0~R4 정의를 유지한다.
- `MIGRATION-PLAN.md`의 Stage 10 순서를 유지한다.
- 이번 PR은 1단계 `report-only risk band`만 구현한다.
- 2단계 human-confirmed decision comparison은 별도 Stage 10B로 남긴다.
- R0 auto-pass pilot과 R1 conditional auto-approval은 이번 단계에서 금지한다.
- R2 이상은 이 단계의 결과로 자동 처리할 수 없다.

## 3. 비목표

- 자동 승인 또는 자동 merge
- 기존 Review Gate 결과 변경
- PR comment, review, label 또는 branch write
- 단일 AI 신뢰 점수
- ML 또는 AI judge 기반 분류
- Ledger schema migration
- Policy Registry lifecycle 변경
- Reground를 hard gate로 승격
- human override audit 저장
- 다중 저장소 중앙 Trust service

## 4. 입력 계약

### 4.1 Trust Request

`trust-request.schema.json`은 작업과 readiness threshold를 명시한다.

필수 작업 필드:

```text
schema_version
task_id
source_revision
task_class
changed_files
required_scenarios
completed_scenarios
repository_match
head_match
rollback_evidence
replay_evidence
readiness_policy
```

Task Class:

```text
generated_artifact
formatting
documentation
routine_code
dependency_change
authentication
authorization
database_migration
deployment
security
policy
verifier
```

Task Class는 모델이나 저장소 전체에 대한 신뢰 점수가 아니다. 동일 작업이라도 변경 경로가 더 높은 위험을 나타내면 경로 기반 floor가 우선한다.

### 4.2 Readiness Policy

Threshold는 숨은 상수가 아니라 request에 명시하고 hash에 포함한다.

```text
policy_id
policy_version
min_ledger_runs
min_ledger_decisions
min_defects
min_closed_defects
min_reground_observations
min_reground_coverage
min_reground_precision
min_reground_recall
max_reground_false_positive_rate
require_active_policy
require_pass_evaluation
require_holdout
require_repeatability
require_zero_protected_negative_regressions
```

Threshold를 낮추면 보고서에 그대로 기록된다. 이번 단계는 threshold 선택 자체를 승인하지 않는다.

### 4.3 Project Profile

Profile에서 다음을 사용한다.

- `project.id`
- `protected_paths`
- resolved profile hash

Repository 절대경로는 report에 기록하지 않는다.

### 4.4 Evidence Sources

Evidence source는 모두 선택 입력이다.

- Evidence Ledger
- Policy Registry
- Evaluation report
- Reground report
- Reground human observations

입력이 없으면 `available=false`와 readiness failure로 기록한다.

입력이 제공됐는데 integrity 또는 semantic verification이 실패하면 report를 만들지 않고 fail closed한다.

## 5. Reground Human Observation 계약

Reground false-positive 측정은 AI label이 아니라 명시적 human-confirmed observation으로만 수행한다.

```text
schema_version
dataset_id
project_id
reground_report_id
observations[]
  observation_id
  relation_id
  expected_status: CURRENT | STALE
  confirmed_by
  confirmed_at
```

Report에는 labeler 자유문과 개별 observation을 복제하지 않는다.

Report에 남기는 정보:

- dataset ID
- dataset SHA-256
- observation count
- coverage
- TP / FP / TN / FN
- precision
- recall
- false-positive rate
- exact rate

동일 relation ID의 중복 observation은 허용하지 않는다.

## 6. Risk Band 계산

### 6.1 Task Class 기본 Band

| Task Class | 기본 Band |
|---|---|
| generated_artifact | R0 |
| formatting | R0 |
| documentation | R1 |
| routine_code | R2 |
| dependency_change | R2 |
| authentication | R3 |
| authorization | R3 |
| database_migration | R3 |
| deployment | R3 |
| security | R3 |
| policy | R4 |
| verifier | R4 |

### 6.2 경로 기반 Floor

최종 Band는 Task Class와 모든 경로 floor 중 가장 높은 Band다.

```text
R0 generated/report-only path
R1 documentation path
R2 normal source, test, dependency manifest
R3 auth, permission, migration, deployment, secret or infrastructure path
R4 PIE verifier, protected baseline, Policy, Evaluation, Reground, Trust Gate path
```

`formatting`으로 선언해도 source code를 변경하면 최소 R2다.

### 6.3 Protected Path

Profile의 `protected_paths`와 일치하는 changed file은 다음을 발생시킨다.

- 최소 R3
- `PROTECTED_PATH_CHANGED` hard-gate advisory

점수 또는 다른 evidence로 상쇄하지 않는다.

## 7. Hard Gate Advisory

다음 hard gate를 결정적으로 계산한다.

```text
PROTECTED_PATH_CHANGED
REQUIRED_SCENARIO_MISSING
REPOSITORY_MISMATCH
HEAD_MISMATCH
AUTHORIZATION_OR_MIGRATION_CHANGE
VERIFIER_CHANGED
POLICY_EVALUATION_MISSING
ROLLBACK_OR_REPLAY_EVIDENCE_MISSING
```

`EVIDENCE_INTEGRITY_FAILURE`는 제공된 source가 invalid할 때 report 생성 자체를 거부하는 방식으로 처리한다.

Hard gate는 report-only advisory다. 기존 Gate exit code와 merge 상태를 변경하지 않는다.

## 8. Evidence Projection

### 8.1 Ledger

Project별 다음 count를 읽는다.

- runs
- artifacts
- claims
- evidence
- findings
- decisions

Ledger 전체 integrity, migration checksum, foreign key와 source artifact projection을 먼저 검증한다.

### 8.2 Defect

- registry source 존재 여부
- defect total
- lifecycle status별 count
- CLOSED count
- resolution evidence가 연결된 CLOSED count
- REOPENED transition 경험 수

Defect 원문 title, signature, root cause, resolution은 report에 포함하지 않는다.

### 8.3 Policy와 Evaluation

- Policy Registry integrity
- active Policy 존재 여부
- active Policy ID와 version
- evaluation reference
- Evaluation report integrity
- active ruleset과 challenger policy hash 일치
- PASS decision
- holdout case count
- baseline/challenger repeatability
- protected negative regression count

### 8.4 Reground

- Reground report integrity
- CURRENT / STALE 상태
- relation count
- stale relation count
- impacted recheck count
- human observation metrics

Reground stale 결과는 이번 단계에서 자동 차단으로 승격하지 않는다.

## 9. Readiness 판정

Readiness는 **자동화 승인 가능성**이 아니라 Stage 10B 진입 가능성을 뜻한다.

상태:

```text
NOT_READY
READY_FOR_HUMAN_COMPARISON
```

모든 threshold와 required condition을 만족하면 다음으로 이동할 수 있다.

```text
next_step = HUMAN_CONFIRMED_DECISION_COMPARISON
```

그렇지 않으면:

```text
next_step = COLLECT_READINESS_EVIDENCE
```

항상 다음 값이 유지된다.

```text
mode = REPORT_ONLY
automation_authorized = false
maximum_automation_band = NONE
```

## 10. Task Advisory

Risk Band에 따라 사람 검토 요구를 설명한다.

| Band | Advisory |
|---|---|
| R0 | HUMAN_CONFIRMATION_REQUIRED |
| R1 | INDEPENDENT_REVIEW_REQUIRED |
| R2 | INDEPENDENT_REVIEW_REQUIRED |
| R3 | HUMAN_APPROVAL_REQUIRED |
| R4 | DUAL_INDEPENDENT_REVIEW_REQUIRED |

이번 단계에서 R0도 자동 PASS하지 않는다.

## 11. Identity와 Hash

Report는 다음 identity를 가진다.

```text
request_sha256
profile_sha256
evidence_fingerprint_sha256
snapshot_sha256
report_id
report_sha256
```

- `generated_at`은 stable snapshot과 report ID에서 제외한다.
- 동일 request와 동일 evidence는 동일 `snapshot_sha256`과 `report_id`를 만든다.
- `report_sha256`은 `generated_at`을 포함하므로 생성 시점이 바뀌면 달라진다.
- absolute source path는 hash descriptor와 report에 포함하지 않는다.

## 12. 검증

### 12.1 Self-contained Verification

- JSON Schema 2020-12
- canonical ordering
- duplicate ID
- Risk Band 재계산
- protected path 재계산
- hard gate 재계산
- readiness condition 재계산
- snapshot, report ID와 outer hash 재계산

### 12.2 Optional Source Replay

원본 request, profile과 evidence source가 제공되면 report를 동일 timestamp로 다시 만들고 snapshot을 비교한다.

Self-contained hash 재계산만으로 source truth를 증명했다고 주장하지 않는다.

## 13. CLI

독립 adapter:

```text
pie-trust assess
pie-trust verify-report
```

기존 CLI additive command:

```text
pie trust-assess
pie validate-trust-report
urs trust-assess
urs validate-trust-report
```

`assess`는 valid report를 만들면 readiness가 `NOT_READY`여도 exit 0이다.

`verify-report`는 valid report면 readiness와 무관하게 exit 0이다.

- input/source error: exit 3
- report integrity error: exit 4

기존 Gate exit code를 재사용하지 않는다.

## 14. 설계 리뷰

### DR-1 — 단일 Trust Score 금지

Risk Band, hard gate와 readiness condition을 개별 근거로 출력한다. weighted total score는 만들지 않는다.

판정: `PASS`

### DR-2 — 자동 승인 경로 차단

Report schema에 `mode=REPORT_ONLY`, `automation_authorized=false`, `maximum_automation_band=NONE`을 상수로 둔다.

판정: `PASS`

### DR-3 — 낮은 Task Class로 위험 경로 은폐 방지

Task Class Band와 path floor의 maximum을 사용한다.

판정: `PASS`

### DR-4 — Hard Gate 상쇄 방지

Hard gate는 score나 readiness metric과 독립된 boolean advisory다.

판정: `PASS`

### DR-5 — Missing과 Invalid Evidence 분리

Missing source는 readiness gap이다. Provided invalid source는 report 생성 실패다.

판정: `PASS`

### DR-6 — Reground 자체 예측으로 정확도 주장 금지

별도 human observation dataset만 measurement source로 인정한다.

판정: `PASS`

### DR-7 — Active Policy와 임의 PASS Evaluation 혼합 방지

Policy Registry active Policy의 evaluation ID, report hash와 challenger ruleset hash가 입력 Evaluation과 일치해야 한다.

판정: `PASS`

### DR-8 — Threshold 은폐 방지

Threshold를 request에 포함하고 request hash와 report에 보존한다.

판정: `PASS`

### DR-9 — Source Path 노출 방지

Report에는 source basename과 content hash만 기록한다.

판정: `PASS`

### DR-10 — Human Decision Comparison 범위 분리

이번 단계는 사람이 내린 최종 결정과 report recommendation을 비교하지 않는다. 별도 Stage 10B로 고정한다.

판정: `PASS`

## 15. Exit Criteria

- deterministic R0~R4 classification
- Profile protected path hard-gate advisory
- Ledger·Defect·Policy·Evaluation·Reground evidence projection
- human-confirmed Reground precision·recall·false-positive measurement
- `NOT_READY`와 `READY_FOR_HUMAN_COMPARISON` 재현 가능
- report-only constant 검증
- generated time과 무관한 stable report identity
- tamper, reorder, duplicate, unsafe path와 source mismatch 차단
- existing CLI, Gate, Ledger schema와 artifact contract 회귀 없음
- Python matrix, asset sync와 wheel build PASS
