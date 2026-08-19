# PIE Stage 0 — Target State

기준일: 2026-07-23  
대상 기준선: PIE `0.3.0` 이후 점진적 확장

## 1. 목표

PIE의 목표 상태는 기존 Review System을 대체하는 거대한 새 플랫폼이 아니다.

목표는 현재 파일 기반 검증 코어 위에 다음 폐쇄 루프를 추가하는 것이다.

```text
Work Intake
→ Deterministic Collection
→ Review and Verification
→ Evidence-backed Decision
→ Defect Memory
→ Rule Candidate
→ Baseline/Challenger Evaluation
→ Approved Policy
→ Reground
```

최종 제품 정의:

> PIE는 프로젝트 변경, 검토 주장, 실행 증거, 결함, 정책과 결정을 연결하여 자동화 가능한 검토 범위를 증거에 따라 확장하는 Project Intelligence Control Plane이다.

## 2. 설계 원칙

### 2.1 기존 계약 보존

다음은 호환 계약으로 유지한다.

- `pie` CLI
- `urs` alias
- 기존 JSON/YAML schema
- Review Run directory
- `.pie/pr-<number>` 산출물
- Candidate Rule의 사람 승인
- deterministic Gate
- read-only GitHub intake
- 기존 exit code

기존 계약 변경이 필요한 경우 별도 schema version과 migration을 제공한다.

### 2.2 파일은 권위 원본, Ledger는 관계 인덱스

```text
Filesystem Artifact
= 재현·감사 가능한 권위 원본

SQLite Ledger
= 검색·관계·상태·계보 인덱스
```

Ledger가 삭제되더라도 원본 artifact에서 재구축할 수 있어야 한다.

### 2.3 판정은 가능한 한 결정적이어야 한다

- hash, path, schema, test result, policy expression은 deterministic evaluator가 처리한다.
- AI는 분류·설명·가설·리뷰 보조에 사용할 수 있다.
- AI narrative는 deterministic Gate를 덮어쓰지 못한다.
- 증거가 부족하면 `FAIL`로 추정하지 않고 `INSUFFICIENT_EVIDENCE`로 분리한다.

### 2.4 규칙은 버전이 있는 가설이다

Rule은 승인되었다는 이유만으로 영구 진리가 되지 않는다.

필수 lifecycle:

```text
CANDIDATE
→ SHADOW
→ APPROVED
→ ENFORCED
→ RETIRED
```

초기 버전에서는 기존 `candidate`, `approved`, `rejected`, `retired`를 유지하면서 evaluation metadata를 추가한다.

### 2.5 자동화 신뢰는 작업 유형별로 획득한다

전체 PIE 또는 특정 AI 모델에 단일 신뢰 점수를 주지 않는다.

신뢰 단위:

```text
Task Class
+ Policy Version
+ Evaluator Version
+ Evidence Type
+ Repository Profile
```

예:

- Markdown local-link 검증은 자동 승인 가능
- authentication 변경은 사람 승인 필수
- schema migration은 replay evidence 필수
- 검증기 자체 변경은 이중 검토 필수

## 3. 목표 아키텍처

```text
┌───────────────────────────────────────────────────────┐
│                    Interface Layer                    │
│ CLI (`pie`, `urs`) / future API / report exporters   │
└──────────────────────────┬────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────┐
│                   Application Layer                   │
│ Analyze PR │ Run Review │ Approve Rule │ Reground    │
└───────────────┬───────────────────────┬───────────────┘
                │                       │
┌───────────────▼──────────────┐  ┌─────▼────────────────┐
│         Domain Layer         │  │  Integration Ports   │
│ Run / Claim / Evidence       │  │ Git / GitHub / CI    │
│ Finding / Defect / Rule      │  │ Artifact / BuildMap  │
│ Decision / Dependency Edge   │  └─────┬────────────────┘
└───────────────┬──────────────┘        │
                │                       │
┌───────────────▼───────────────────────▼───────────────┐
│                 Infrastructure Layer                  │
│ File Artifact Store │ SQLite Ledger │ gh subprocess  │
└───────────────────────────────────────────────────────┘
```

## 4. 목표 모듈 경계

첫 단계에서는 namespace rename을 수행하지 않는다.

```text
src/review_system/
├─ cli.py
├─ application/
│  ├─ analyze_pr.py
│  ├─ analyze_change.py
│  ├─ run_review.py
│  ├─ approve_rule.py
│  ├─ evaluate_policy.py
│  └─ reground.py
├─ domain/
│  ├─ runs.py
│  ├─ claims.py
│  ├─ evidence.py
│  ├─ findings.py
│  ├─ defects.py
│  ├─ policies.py
│  ├─ decisions.py
│  └─ dependencies.py
├─ infrastructure/
│  ├─ artifact_store.py
│  ├─ ledger.py
│  ├─ migrations/
│  └─ github/
│     ├─ client.py
│     ├─ collector.py
│     ├─ repository_binding.py
│     ├─ source_document.py
│     └─ validation.py
└─ compatibility/
   └─ urs.py
```

이 구조는 최종 파일 목록이 아니라 책임 방향을 고정하는 목표다. 실제 추출은 테스트 보호 아래 작은 PR로 진행한다.

## 5. 목표 도메인 모델

### 5.1 Run

```text
Run
- run_id
- project_id
- task_class
- mode
- source_revision
- policy_version
- evaluator_versions
- started_at
- completed_at
- status
- artifact_root
- run_sha256
```

기존 Review Run과 PR 분석을 공통 상위 실행 개념으로 연결한다. 기존 파일 schema는 유지하고 Ledger projection에서 공통 필드를 정규화한다.

### 5.2 Artifact

```text
Artifact
- artifact_id
- run_id
- artifact_type
- relative_path
- sha256
- media_type
- size_bytes
- created_at
- source_identifier
```

원문은 파일에 남고 Ledger에는 metadata만 저장한다.

### 5.3 Claim

Claim은 보고서나 판정이 주장하는 사실을 독립 객체로 만든다.

```text
Claim
- claim_id
- run_id
- claim_type
- statement
- scope
- status
- policy_version
```

예:

- `required tests passed`
- `protected baseline is intact`
- `PR changed files are complete`
- `rule RC-17 improves recall without regression`

### 5.4 Evidence

```text
Evidence
- evidence_id
- run_id
- evidence_level
- evidence_type
- summary
- result
- artifact_id
- locator
- producer
- producer_version
- collected_at
```

연결:

```text
ClaimEvidence
- claim_id
- evidence_id
- relation
- strength
```

한 Evidence가 여러 Claim을 지지하거나 반박할 수 있다.

### 5.5 Finding과 Defect

```text
Finding
= 특정 Run에서 관찰된 문제

Defect
= 여러 Run에 걸쳐 동일 근본 원인으로 식별되는 장기 객체
```

Defect:

```text
- defect_id
- signature
- category
- root_cause
- lifecycle_status
- first_seen_run_id
- last_seen_run_id
- reproducer_artifact_id
- owner
- resolution
```

연결:

```text
FindingDefect
- finding_id
- defect_id
- match_method
- confidence
- approved_by
```

자동 유사도는 제안만 하며 동일 Defect 확정은 사람 또는 결정적 signature가 수행한다.

### 5.6 Rule과 Policy Version

Rule에 다음 metadata를 추가한다.

```text
- derived_from_defects
- evaluation_dataset
- evaluation_result
- introduced_in_policy_version
- supersedes
- review_due_at
- retirement_condition
```

Policy Version:

```text
- policy_version
- parent_version
- rules_sha256
- status
- approved_by
- approved_at
- evaluation_run_id
```

### 5.7 Decision

```text
Decision
- decision_id
- run_id
- decision_type
- outcome
- reasons
- policy_version
- decided_by
- decided_at
```

Decision은 Claim과 Evidence를 참조한다. Markdown narrative만으로 PASS를 선언할 수 없다.

### 5.8 Dependency Edge와 Reground

기존 Graph edge에 직접 모든 운영 metadata를 넣기보다 Ledger projection으로 확장한다.

```text
DependencyEdgeState
- source_identifier
- relation_type
- target_identifier
- source_sha256
- target_sha256
- verified_at
- verified_run_id
- status: CURRENT | STALE | UNKNOWN
- stale_reason
```

## 6. Evidence Ledger

초기 저장소는 Python 표준 라이브러리 `sqlite3`를 사용한다.

예상 테이블:

```text
schema_migrations
runs
artifacts
claims
evidence
claim_evidence
findings
defects
finding_defects
rule_snapshots
policy_versions
decisions
dependency_edge_state
```

원칙:

1. foreign key 활성화
2. WAL은 필요성이 검증된 후 도입
3. timestamp는 UTC ISO-8601
4. artifact path는 repository 또는 run root 기준 상대 경로
5. content hash는 SHA-256
6. 원문 blob을 SQLite에 저장하지 않음
7. migration은 순방향·재실행 안전 검증
8. import는 idempotent
9. schema version을 CLI에서 조회 가능
10. backup 없이 destructive migration 금지

예상 위치:

```text
.pie/ledger.sqlite
```

프로젝트 전역 Ledger와 개별 Run artifact를 연결한다.

## 7. Evaluation Lab

### 7.1 목적

Rule을 승인하기 전에 현재 정책과 후보 정책을 동일 데이터셋에서 비교한다.

```text
Baseline Policy
        ├─ Evaluation Dataset
Challenger Policy
        └─ 동일 입력·동일 label
```

### 7.2 데이터 분리

```text
evaluation/
├─ development/
├─ validation/
└─ holdout/
```

- development: 규칙 설계에 사용
- validation: 조정 중 반복 사용
- holdout: 승인 직전에만 사용

### 7.3 핵심 지표

- True Positive
- True Negative
- False Positive
- False Negative
- Precision
- Recall
- Abstain Rate
- Coverage
- Manual Review Rate
- Repeatability
- Runtime

정확도 100%는 데이터셋 범위를 함께 기록해야 한다.

### 7.4 승인 Gate

후보 Rule은 최소한 다음을 만족해야 한다.

```text
schema valid
AND deterministic repeatability proven
AND holdout regression == 0 for protected cases
AND required metric threshold met
AND evaluation evidence attached
AND human approval present
```

## 8. Reground Engine

Reground는 모든 문서를 주기적으로 다시 읽는 기능이 아니다.

변경된 source hash와 기존 verification state를 비교하여 영향을 받은 지식만 stale로 만든다.

트리거:

- repository revision 변경
- source artifact hash 변경
- target artifact hash 변경
- schema version 변경
- policy version 변경
- test 삭제·이름 변경
- 문서에 기록된 command 실패
- review due date 도래
- 서로 모순되는 Claim 발생

출력:

```text
- stale artifacts
- stale claims
- impacted tests
- impacted policies
- required rechecks
- unresolved conflicts
```

초기에는 기존 `analyze-change` 결과에 advisory section으로 추가한다. 자동 차단은 별도 성숙도 조건 이후에만 허용한다.

## 9. Trust Gate

### 9.1 Hard Gate

다음은 점수로 상쇄하지 않는다.

- protected path 변경
- evidence integrity 실패
- 필수 scenario 누락
- 인증·권한·migration 고위험 변경
- 검증기 자체 변경
- policy evaluation 누락
- repository/head mismatch
- rollback 또는 replay evidence 누락

### 9.2 Risk Band

| Band | 예 | 기본 처리 |
|---|---|---|
| R0 | generated report, formatting | 자동 처리 가능 |
| R1 | 검증된 반복 패턴 | 조건부 자동 승인 |
| R2 | 일반 코드·정책 변경 | 독립 리뷰 |
| R3 | 보안·DB·권한·배포 | 사람 승인 필수 |
| R4 | PIE verifier·baseline·policy 변경 | 이중 독립 리뷰 |

Trust Gate는 Evidence Ledger와 Evaluation Lab이 구축된 이후 구현한다.

## 10. BuildMap Integration

BuildMap은 검증 원문 저장소가 아니다.

권위 분리:

| 정보 | 권위 소스 |
|---|---|
| 코드·파일 | Git repository |
| 실행 증거 | PIE artifact store |
| 관계·상태 | PIE Ledger |
| 정책 | PIE policy registry |
| 결정 이유·변경 흐름 | BuildMap |

초기 integration은 JSON export다.

```text
pie export-buildmap --run <RUN-ID>
```

export contract:

- run identifier
- source revision
- decision
- decision reasons
- referenced Claim IDs
- referenced Evidence IDs
- related Defect IDs
- policy version
- artifact links

BuildMap API 직접 호출은 export contract가 안정된 후 도입한다.

## 11. Event 처리

현재 외부 Event Bus를 도입하지 않는다.

초기 구조:

```text
Application Use Case
→ InProcess Event Publisher
→ Ledger Projection / Report / Export Handler
```

도메인 이벤트 예:

- `RunCompleted`
- `FindingRecorded`
- `DefectLinked`
- `RuleCandidateCreated`
- `PolicyApproved`
- `ArtifactMarkedStale`

외부 queue는 다음 조건에서만 검토한다.

- process가 분리됨
- 작업이 장시간 실행됨
- retry와 crash recovery가 필요함
- 여러 consumer가 독립 배포됨

## 12. 의존성 정책

초기 목표 상태에서도 다음을 새로 요구하지 않는다.

- ORM
- web framework
- graph database
- message broker
- OPA
- OpenTelemetry
- MLflow

우선 표준 라이브러리와 현재 의존성을 사용한다.

새 의존성 추가 조건:

1. 표준 라이브러리 구현의 복잡성 또는 위험이 더 큼
2. 구체적인 use case가 있음
3. lock과 보안 검토가 가능함
4. wheel과 Python matrix를 유지함
5. 대체·제거 전략이 있음

## 13. 목표 완료 조건

PIE가 목표 상태에 도달했다고 판단하려면 다음이 가능해야 한다.

1. 임의 Run의 모든 판정 Claim을 Evidence까지 추적
2. 동일 Defect의 발생·수정·재발 이력 조회
3. Rule이 어떤 Defect와 평가에서 파생됐는지 조회
4. baseline/challenger 정책 비교 재실행
5. 변경으로 stale해진 문서·테스트·정책 식별
6. 작업 유형별 자동화 허용 범위 설명
7. BuildMap에 결정 근거를 중복 없이 export
8. Ledger 삭제 후 artifact에서 재구축
9. 기존 v0.3.0 CLI와 산출물 호환 유지
10. 새 계층이 기존 deterministic Gate를 약화하지 않음
