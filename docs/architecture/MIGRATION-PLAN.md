# PIE Stage 0 — Migration Plan

기준일: 2026-07-23  
출발 기준선: PIE `0.3.0` / `main@c8578aa2c8096b3f0fa7652248c078702a94d023`

## 1. 목적

이 계획은 현재 PIE를 중단하거나 재작성하지 않고 Project Intelligence Control Plane으로 점진적으로 확장하는 순서를 정의한다.

핵심 원칙:

1. 한 Stage는 하나의 구조적 위험만 해결한다.
2. 기존 CLI·schema·artifact 계약은 기본적으로 보존한다.
3. 기능 변경과 리팩터링을 같은 PR에 섞지 않는다.
4. 각 Stage는 상세 설계 → 사전 리뷰 → 구현 → 독립 리뷰 → 검증 순서를 따른다.
5. 모든 Stage는 rollback 가능한 작은 PR로 분리한다.
6. 후속 Stage는 선행 Stage의 완료 조건을 증거로 확인한 뒤 시작한다.

## 2. 공통 작업 절차

모든 Stage에서 다음 절차를 사용한다.

```text
A. BASELINE
- authoritative main SHA 고정
- current tests/commands 고정
- protected contracts 식별

B. DESIGN
- 목적·비목표
- 변경 파일
- data contract
- failure path
- migration/rollback
- validation matrix

C. DESIGN REVIEW
- 기존 계약 충돌
- 과설계
- 보안·무결성
- data loss
- test oracle 완전성

D. IMPLEMENT
- 작은 commit
- 기능과 문서 동시 갱신
- backward compatibility 유지

E. IMPLEMENTATION REVIEW
- diff 기반 독립 검토
- scope creep
- hidden coupling
- error path
- stale asset

F. VERIFY
- compile
- unit/regression
- CLI contract
- package asset drift
- wheel
- targeted failure tests

G. REPORT
- 완료
- 문제
- 다음 작업
- 상세 기록은 repository docs에 누적
```

## 3. Stage 0 — Architecture Baseline

### 목표

현재 구현과 목표 구조 사이의 권위 기준선을 문서로 고정한다.

### 변경 범위

```text
docs/architecture/
├─ CURRENT-STATE.md
├─ TARGET-STATE.md
├─ GAP-ANALYSIS.md
├─ MIGRATION-PLAN.md
└─ STAGE-0-VALIDATION.md
```

선택적 root README 정리:

- architecture 문서 링크
- 깨진 trailing text 제거

### 비목표

- package namespace 변경
- application layer 추출
- SQLite 추가
- schema 변경
- CLI command 추가
- external dependency 추가

### 검증

- 기준 commit과 version 일치
- CLI command 수 parser 대조
- source module inventory 대조
- schema·asset sync 경계 대조
- 문서 간 용어 일관성
- Markdown link 유효성
- PR CI

### 완료 조건

- current/target/gap/migration 문서 존재
- 후속 Stage 순서와 dependency 명시
- 잘못된 수치·경로·버전 없음
- Stage 1 범위가 구현 가능한 수준으로 정의됨

## 4. Stage 1 — Application Boundary Extraction

예상 버전: `0.3.x` 내부 리팩터링 또는 `0.4.0` 준비 단계

### 목표

CLI와 application use case를 분리한다.

### 1차 대상

```text
AnalyzePullRequest
IndexProject
AnalyzeChange
ApproveRule
CalculateGate
```

### 설계

```python
@dataclass(frozen=True)
class AnalyzePullRequestRequest:
    pull_request: str
    repository_root: Path
    repository: str | None
    ...

@dataclass(frozen=True)
class AnalyzePullRequestResult:
    source_path: Path
    impact_path: Path
    report_path: Path
    diff_path: Path | None
    summary: dict
```

CLI는 request 생성·result 출력만 담당한다.

### 변경 규칙

- 기존 domain 함수는 가능한 한 그대로 호출
- 첫 PR에서 namespace rename 금지
- output format 변경 금지
- new dependency 금지
- `review_system.cli` import compatibility 유지

### 테스트

- 기존 CLI test 그대로 통과
- use case direct unit test 추가
- filesystem failure cleanup
- output collision
- mismatch/dirty/head failure path
- CLI와 direct use case 결과 동등성

### Exit Criteria

- `cmd_analyze_pr` orchestration 대폭 축소
- use case가 CLI 없이 호출 가능
- 기존 79개 이상 회귀 통과
- wheel smoke 통과

## 5. Stage 2 — GitHub Integration Extraction

Stage 1과 같은 PR에 넣지 않는다.

### 목표

`github_connector.py` 책임을 내부 모듈로 분리하면서 public behavior를 보존한다.

### 순서

1. characterisation tests 보강
2. target parser 추출
3. command runner/retry 추출
4. repository binding 추출
5. collector 추출
6. source document/hash 추출
7. compatibility export 유지

### 보호 계약

- source JSON canonical form
- `source_sha256`
- diff byte hash
- retry 대상과 횟수
- API pagination
- fail-closed mismatch
- no shell

### Exit Criteria

- old import path 작동
- source hash fixture 동일
- CLI output 동일
- connector module별 focused tests 존재

## 6. Stage 3 — Run and Artifact Identity

### 목표

Ledger 전에 모든 기존 산출물에 안정적인 identity 규칙을 정의한다.

### 설계 대상

- Run ID generation
- Artifact ID generation
- source revision normalization
- relative path policy
- SHA-256 canonicalization
- Review Run과 PR Run의 공통 projection

### ID 제안

Random UUID만 사용하지 않고 import 재실행에 안정적인 key를 함께 둔다.

```text
run_key = project_id + run_type + source_revision + source_identifier
artifact_key = run_key + relative_path + sha256
```

외부 표시 ID와 내부 natural key를 분리한다.

### 위험

- 동일 PR 재실행을 동일 Run으로 볼지 별도 attempt로 볼지
- amended commit
- artifact 경로 이동
- degraded analysis override

### 결정

```text
Run = logical source execution
Attempt = 같은 Run의 실제 실행 시도
```

Ledger 첫 버전에 Attempt를 생략할 수 있으나 schema 확장 여지는 유지한다.

## 7. Stage 4 — Evidence Ledger Foundation

예상 milestone: PIE `0.4.0`

### 목표

기존 artifact를 대체하지 않는 SQLite 관계 인덱스를 추가한다.

### 최초 schema

```sql
schema_migrations
runs
artifacts
claims
evidence
claim_evidence
decisions
policy_snapshots
```

Finding·Defect는 다음 Stage에서 추가할 수 있다. 첫 migration을 과도하게 확장하지 않는다.

### 신규 CLI 후보

```text
pie ledger-init
pie ledger-import-run <path>
pie ledger-import-pr <path>
pie ledger-verify
pie ledger-rebuild
pie show-run <run-id>
```

명령 이름은 상세 설계에서 확정한다.

### 기능

- Review Run import
- PR analysis import
- artifact hash 검증
- Claim projection
- Decision projection
- idempotent re-import
- rebuild

### 테스트

- empty DB initialization
- migration replay
- foreign key violation
- duplicate import
- changed artifact detection
- missing artifact
- path traversal
- corrupted DB/rebuild behavior
- Windows path normalization

### Exit Criteria

- 기존 artifact에서 Ledger 재구축 가능
- Ledger 삭제가 원본 손실을 만들지 않음
- 주요 PASS/FAIL Claim을 Evidence까지 조회
- current CLI behavior 회귀 없음

## 8. Stage 5 — Defect Registry

예상 milestone: `0.5.0` 또는 `0.4.x`

### 목표

Run-local Finding과 cross-run Defect를 분리한다.

### schema

```text
findings
defects
finding_defects
defect_events
defect_artifacts
```

### lifecycle

```text
OBSERVED
→ REPRODUCED
→ CLASSIFIED
→ RULE_CANDIDATE
→ MITIGATED
→ VERIFIED
→ CLOSED
→ REOPENED
```

### Seed Migration

실전 7개 결함을 fixture로 등록하되 역사적 기록이라는 metadata를 포함한다.

### 신규 CLI 후보

```text
pie defect-create
pie defect-link-finding
pie defect-show
pie defect-list
pie defect-close
pie defect-reopen
```

### 안전 규칙

- similarity 자동 연결은 proposal
- root cause 없는 defect 허용
- CLOSED는 resolution Evidence 필요
- 재발 시 기존 Defect REOPEN 또는 새 Defect 선택을 기록

## 9. Stage 6 — Evaluation Lab

### 목표

Rule 승인 전 baseline/challenger 비교를 실행한다.

### 초기 범위

AI judge 없이 deterministic PIE output과 human labels만 비교한다.

### dataset contract

```text
case_id
repository
source_revision
input_artifacts
expected_changed_scope
expected_packs
expected_tests
expected_protected_result
labels
provenance
split
```

### runner

```text
Dataset
→ Baseline Policy
→ Challenger Policy
→ normalized outcomes
→ case diff
→ metrics
→ signed evaluation report
```

### Rule Approval 변경

첫 단계에서는 기존 `approve-rule`을 깨지 않고 warning을 추가한다.

후속 schema version에서 evaluation reference를 required로 승격한다.

### Exit Criteria

- 12개 Journey Connect PR import
- development/validation/holdout 분리
- metric 재현성
- baseline/challenger diff
- protected negative regression 0
- evaluation artifact hash

## 10. Stage 7 — Policy Registry

### 목표

Rule 파일의 집합을 versioned Policy로 관리한다.

### 기능

- parent policy
- ruleset hash
- evaluation reference
- approval
- status
- supersede/retire
- effective date

### 신규 CLI 후보

```text
pie policy-build
pie policy-evaluate
pie policy-approve
pie policy-compare
pie policy-retire
```

### 호환

기존 `approved-rules.yml`은 default active policy의 materialized view로 유지할 수 있다.

## 11. Stage 8 — Reground Foundation

### 목표

기존 Graph와 Ledger를 연결해 stale state를 산출한다.

### 1차 범위

- source/target hash 비교
- last verified run
- stale reason
- advisory report

### 하지 않는 것

- 모든 문서 의미 자동 판정
- stale 즉시 merge block
- background scheduler

### Exit Criteria

- known changed dependency fixture에서 stale 탐지
- unchanged relation은 CURRENT
- hash normalization 회귀 없음
- impacted recheck 목록 생성

## 12. Stage 9 — BuildMap Export

### 목표

PIE의 결정 근거를 BuildMap이 중복 저장 없이 참조하도록 한다.

### 산출물

```text
schemas/buildmap-export.schema.json
pie export-buildmap
```

### 계약

- raw GitHub discussion 기본 제외
- sensitive artifact 내용 제외
- stable source identifier
- idempotent export ID
- redaction metadata

### Exit Criteria

- sample Run export schema valid
- BuildMap 측 import 가능
- PIE 원본과 export hash 연결

## 13. Stage 10 — Trust Gate

### 선행 조건

- Ledger 운영 경험
- Defect Registry
- Policy Evaluation
- Reground false-positive 측정
- task class 정의

### 목표

저위험·고성숙 작업만 조건부 자동 승인한다.

### 단계

1. report-only risk band
2. human-confirmed decision comparison
3. R0 auto-pass pilot
4. R1 conditional auto-approval
5. override audit

R2 이상 자동 승인은 별도 안전 검토 없이는 허용하지 않는다.

## 14. Stage 11 이후 — 조건부 확장

아래는 수요가 확인된 뒤만 진행한다.

- external event bus
- long-running worker
- multi-agent roles
- web dashboard
- central organization service
- multi-tenant policy distribution
- OpenTelemetry
- OPA

## 15. PR 분할 원칙

각 Stage 안에서도 다음처럼 PR을 분리한다.

```text
PR A: contract and tests
PR B: internal implementation
PR C: migration/import
PR D: docs and operational report
```

작은 단계는 A+B를 합칠 수 있으나 다음은 합치지 않는다.

- namespace rename + new feature
- DB migration + UI
- policy semantic change + connector refactor
- evaluation labels + rule implementation
- generated asset update 누락

## 16. Branch와 Version 정책

권장 branch:

```text
agent/stage-<n>-<scope>
```

Version:

- 내부 동작 보존 리팩터링: patch 또는 unreleased change
- 새 Ledger/public CLI: minor
- 기존 schema/CLI 호환 파괴: major 검토

## 17. 공통 검증 Matrix

| 검증 | 모든 Stage | DB Stage | Policy Stage | GitHub Stage |
|---|---:|---:|---:|---:|
| `compileall` | O | O | O | O |
| full unittest | O | O | O | O |
| CLI smoke | O | O | O | O |
| asset sync | O | O | O | O |
| wheel build | O | O | O | O |
| schema validation | O | O | O | O |
| migration replay | - | O | O | - |
| idempotent import | - | O | O | - |
| baseline/challenger | - | - | O | - |
| source hash fixture | - | - | - | O |
| live GitHub smoke | 필요 시 | - | - | O |

## 18. 중단 조건

다음 중 하나가 발생하면 다음 Stage로 진행하지 않는다.

- 기존 artifact hash 계약 회귀
- protected path 방어 약화
- CLI exit code 변경 미문서화
- schema migration으로 원본 복구 불가
- evaluation 데이터 누수
- false positive 증가 원인 미확인
- root/package asset drift
- CI matrix 실패
- 문서와 구현의 권위 기준 불명확

## 19. 현재 다음 작업

Stage 0 종료 후 바로 착수할 작업은 Stage 1이다.

구체적 시작점:

1. `cmd_analyze_pr` characterisation test 보강
2. request/result DTO 설계
3. `application/analyze_pr.py` 추출
4. CLI adapter 축소
5. exact output·hash·failure path 회귀 검증

Evidence Ledger 구현은 Stage 1 경계가 안정된 뒤 시작한다.
