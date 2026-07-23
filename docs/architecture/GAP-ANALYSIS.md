# PIE Stage 0 — Gap Analysis

기준일: 2026-07-23  
현재 기준선: PIE `0.3.0` / commit `c8578aa2c8096b3f0fa7652248c078702a94d023`

## 1. 판정 방식

각 영역을 다음 상태로 분류한다.

| 상태 | 의미 |
|---|---|
| `READY` | 후속 기능이 현재 계약을 그대로 사용할 수 있음 |
| `EXTEND` | 기반은 있으나 metadata·관계·use case 확장이 필요 |
| `EXTRACT` | 기능은 있으나 책임 분리가 먼저 필요 |
| `NEW` | 독립 구현이 없음 |
| `DEFER` | 현재 도입하면 과설계 또는 선행 조건 미충족 |

우선순위:

| 우선순위 | 의미 |
|---|---|
| P0 | 다음 Stage 진입 전에 해결 |
| P1 | PIE Core milestone에 포함 |
| P2 | Core 안정 후 구현 |
| P3 | 운영 규모가 생긴 뒤 검토 |

## 2. 요약 Matrix

| 영역 | 현재 자산 | 상태 | 우선순위 | 다음 조치 |
|---|---|---|---|---|
| Review Lifecycle | INTAKE~ARCHIVE 계약 | READY | - | 보존 |
| Finding Schema | severity/confidence/status/evidence | READY | - | Ledger projection 추가 |
| Evidence Policy | E0~E5 | EXTEND | P1 | 독립 ID·Claim 관계 |
| Deterministic Gate | policy expression과 hard decision | READY | - | policy snapshot 연결 |
| Protected Baseline | SHA-256, path/symlink guard | READY | - | artifact 등록 |
| Review Run | 파일 기반 run directory | EXTEND | P1 | 공통 Run projection |
| GitHub Intake | PR metadata·discussion·diff·hash | READY | - | application boundary 추출 |
| Project Graph | file/symbol/reference graph | EXTEND | P2 | verification/stale state |
| Impact Analysis | BFS·Rule·Pack·Test 추천 | EXTEND | P2 | Reground 결과 병합 |
| Rule Candidate | co-change discovery | EXTEND | P1 | Defect·evaluation 연결 |
| Rule Approval | 사람 승인과 audit | EXTEND | P1 | evaluation evidence 필수화 |
| CLI | 29개 command와 orchestration | EXTRACT | P0 | application use case 분리 |
| GitHub Connector | 기능 완성, 단일 대형 모듈 | EXTRACT | P0 | 내부 책임 분리 |
| Claim Model | 없음 | NEW | P1 | schema와 Ledger 도입 |
| Evidence Ledger | 없음 | NEW | P1 | SQLite index |
| Defect Registry | 없음 | NEW | P1 | Finding과 장기 결함 분리 |
| Evaluation Lab | 없음 | NEW | P1 | baseline/challenger runner |
| Reground State | 없음 | NEW | P2 | edge verification state |
| Trust Maturity | 없음 | NEW | P2 | task-class risk band |
| BuildMap Export | 없음 | NEW | P2 | 안정된 JSON contract |
| External Event Bus | 없음 | DEFER | P3 | multi-process 조건 후 검토 |
| Web UI | 없음 | DEFER | P3 | CLI와 schema 안정 후 검토 |

## 3. P0 — Application Boundary

### 3.1 현재

`cli.py`는 다음을 함께 수행한다.

- parser 정의
- 입력 파일 해석
- domain 함수 호출 순서 결정
- repository context 검증
- output path 결정
- artifact 저장
- 사용자 출력
- exit code 결정

### 3.2 문제

Evidence Ledger, Defect Registry와 Evaluation 명령을 같은 방식으로 추가하면 CLI가 전체 application service가 된다.

영향:

- use case를 CLI 밖에서 재사용하기 어려움
- unit test가 argument parsing과 business flow를 함께 검증
- future API 또는 BuildMap adapter가 CLI 함수를 재호출할 가능성
- transaction boundary와 failure cleanup이 불명확

### 3.3 필요한 변경

```text
cli.py
→ parse arguments
→ construct request DTO
→ call application use case
→ render result / exit code
```

초기 추출 대상:

1. `AnalyzePullRequest`
2. `IndexProject`
3. `AnalyzeChange`
4. `ApproveRule`
5. `CalculateGate`

### 3.4 완료 조건

- 기존 command syntax 동일
- 기존 stdout 핵심 문구 동일
- 기존 exit code 동일
- JSON/YAML/Markdown 결과 동일
- 79개 기준 테스트 회귀 없음

## 4. P0 — GitHub Connector Responsibility Split

### 4.1 현재

`github_connector.py`가 약 572줄 규모로 다음을 포함한다.

- executable resolution
- subprocess execution
- retry
- auth/repository doctor
- PR target parsing
- repository URL parsing
- PR metadata collection
- paginated REST collection
- diff collection
- normalization
- source hash
- source validation

### 4.2 문제

기능 오류가 있다는 뜻은 아니다. 변경 이유가 서로 다른 책임이 한 파일에 모여 있어 후속 확장 시 회귀 범위가 커진다.

예:

- GitHub Enterprise URL 변경
- retry policy 변경
- source schema 변경
- local repository binding 변경
- discussion pagination 변경

각 변경이 동일 모듈 전체를 건드린다.

### 4.3 목표 분리

```text
infrastructure/github/
├─ command_runner.py
├─ target.py
├─ repository_binding.py
├─ collector.py
├─ source_document.py
└─ validation.py
```

### 4.4 완료 조건

- exact source hash 결과 유지
- diff byte 보존 유지
- shell 미사용 유지
- retry와 pagination 테스트 유지
- import compatibility shim 제공

## 5. P1 — Claim Model

### 5.1 현재

다음은 모두 서로 다른 의미지만 독립 객체가 아니다.

- Finding의 문제 주장
- Gate의 판정 근거
- report의 “tests passed” 문장
- graph의 “hash valid” 판정
- PR source의 “changed files complete” 판정

### 5.2 문제

Markdown 또는 중첩 JSON을 읽지 않고 특정 판정이 어떤 Evidence에 의존했는지 조회할 수 없다.

### 5.3 필요한 모델

- Claim ID
- type
- statement
- scope
- status
- run
- policy version
- supporting/contradicting Evidence 관계

### 5.4 완료 조건

- Gate reason이 Claim ID를 참조
- report 주요 결론이 Claim으로 projection
- Evidence 없는 PASS Claim 검출
- Claim export/import idempotent

## 6. P1 — Evidence Ledger

### 6.1 현재

Artifact는 run directory 또는 `.pie/pr-*`에 존재한다. 파일 단위 integrity는 강하지만 실행 간 relation은 없다.

### 6.2 필요한 기능

- Run 검색
- source revision 검색
- artifact hash 검색
- Claim–Evidence join
- Finding–Defect join
- Rule–Evaluation join
- Decision history
- stale state

### 6.3 저장 전략

`sqlite3`를 사용한 metadata index.

하지 않는 것:

- artifact 원문 blob 저장
- 기존 파일 제거
- 중앙 서버 필수화
- repository 밖의 global user database

### 6.4 위험

| 위험 | 방어 |
|---|---|
| DB와 파일 불일치 | file hash와 import reconciliation |
| migration 실패 | schema_migrations와 transaction |
| 중복 import | stable natural key와 upsert |
| path 이동 | artifact root + relative path + hash |
| DB 손상 | rebuild command와 backup |

## 7. P1 — Defect Registry

### 7.1 현재

Finding은 Run에 종속된다. CRLF hash 결함처럼 여러 실행과 버전에 영향을 준 문제를 장기 객체로 식별하지 않는다.

### 7.2 필요한 기능

- 동일 근본 원인의 Finding 연결
- first/last seen
- reproducer
- resolution
- recurrence
- derived Rule Candidate
- affected policy/evaluator version

### 7.3 Seed Defect 후보

실전 PIE 검증에서 이미 확인된 다음 사례를 초기 fixture로 사용할 수 있다.

1. Markdown 상대 경로 분석 실패
2. preset과 실제 repository 구조 불일치
3. migration·traceability 추천 누락
4. test-resource SQL 과추천
5. helper 파일 과추천
6. Windows CRLF로 diff hash 불일치
7. protected SQL path 오설정

### 7.4 완료 조건

- 각 seed Defect에 재현 또는 고정 근거 존재
- Finding과 Defect가 혼동되지 않음
- resolved Defect 재발 조회 가능
- Defect 없이 Rule을 승인할 수는 있으나 provenance 없음 경고

## 8. P1 — Rule Evaluation

### 8.1 현재

Rule Candidate는 support/confidence 임계값을 통과하고 사람 승인을 받으면 Approved Rule로 이동한다.

### 8.2 Gap

현재 confidence는 공동 변경 association이며 탐지 precision 또는 recall이 아니다.

승인 과정에 다음이 필수 조건이 아니다.

- labeled examples
- protected negative cases
- baseline/challenger comparison
- regression count
- repeatability

### 8.3 필요한 기능

```text
Evaluation Dataset
+ Baseline Policy
+ Challenger Policy
→ Metrics and Case Diff
→ Approval Evidence
```

### 8.4 초기 데이터

Journey Connect merge PR 12개 검증 결과를 초기 evaluation dataset으로 변환한다.

주의:

- 동일 사례로 규칙 설계와 최종 평가를 동시에 하지 않음
- 다른 저장소에 100% 정확도를 일반화하지 않음
- review/comment 양성 표본 부족을 명시

## 9. P2 — Reground

### 9.1 현재

Graph는 현재 checkout의 구조를 해시한다. 그러나 과거 검증 관계가 현재도 유효한지 상태를 보존하지 않는다.

### 9.2 필요한 기능

- relation verification timestamp
- source/target hash
- verified policy/evaluator version
- stale reason
- required recheck

### 9.3 최소 구현

기존 graph schema를 즉시 깨지 않는다.

Ledger에 `dependency_edge_state` projection을 만들고 `analyze-change` 결과에 stale advisory를 추가한다.

### 9.4 자동 차단 조건

초기에는 stale을 warning으로만 사용한다. 다음이 검증되면 hard gate 후보가 된다.

- stale detector precision
- required document/test contract
- false positive cost
- 명시적 repository policy

## 10. P2 — Trust Model

Trust Model은 Evidence Ledger와 Evaluation이 없으면 구현할 수 없다.

필요 선행 조건:

1. task class 정의
2. policy version
3. evaluator version
4. labeled evaluation
5. hard gate 분리
6. human override audit

단일 “AI 신뢰도 점수”는 도입하지 않는다.

## 11. P2 — BuildMap Integration

### 11.1 현재

BuildMap과 PIE는 개념적으로 연결되지만 machine-readable contract가 없다.

### 11.2 Gap

직접 API 연동부터 만들면 PIE artifact와 BuildMap decision data가 중복될 수 있다.

### 11.3 최소 구현

- JSON Schema 기반 export
- Run·Claim·Evidence·Decision stable ID
- artifact raw content 제외
- retry-safe export identifier

## 12. P3 — Event Bus

현재 단일 CLI 프로세스에서 외부 broker는 필요 없다.

도입 시 발생하는 비용:

- delivery semantics
- duplicate handling
- broker installation
- local/offline 실행 저하
- test complexity
- artifact transaction 분리

현재 대안:

- in-process domain event interface
- ordered handler execution
- idempotent projection

## 13. P3 — Web UI

UI는 상태 모델이 안정된 뒤 만든다.

선행 조건:

- Ledger schema 안정
- query use case 검증
- Defect lifecycle 운영 경험
- evaluation report format 안정
- BuildMap 역할 경계 확정

## 14. 문서와 구현 Drift

### 14.1 확인된 위험

- CLI command 수를 사람이 수동 집계
- README 버전·명령 목록 수동 유지
- root asset과 packaged asset 복제
- 테스트 수치가 검증 보고서에 고정
- 이전 설계 문서의 제외 범위가 후속 버전에서 변경됨

예: v0.2 설계 문서는 GitHub PR 실시간 수집을 제외 범위로 기록하지만 v0.3에서 구현되었다.

### 14.2 개선

- CLI manifest 자동 생성
- schema inventory command
- package asset drift check 유지
- architecture current-state 문서에 baseline commit 명시
- 문서 assertion test 도입 여부 검토
- superseded 문서에 상태 header 추가

## 15. 보안·무결성 Gap

현재 방어는 강하지만 Ledger 도입 시 추가해야 한다.

- SQLite file permission 안내
- symlinked Ledger 차단 여부
- artifact path escape 차단
- imported artifact hash 재검증
- secret-bearing GitHub discussion의 보존 정책
- BuildMap export redaction
- migration backup과 rollback

## 16. 성능 Gap

현재 graph와 GitHub collection은 단일 CLI 실행에 최적화되어 있다.

Ledger 이후 측정할 항목:

- import 시간
- graph build 시간
- PR collection 시간
- SQLite query 시간
- artifact reconciliation 시간
- evaluation dataset 실행 시간

성능 최적화는 측정 전 도입하지 않는다.

## 17. 종합 판정

### 보존할 것

- Review Lifecycle
- Evidence Level
- Finding contract
- Gate
- protected baseline
- graph와 impact
- Rule Candidate와 명시적 승인
- GitHub source hash
- 파일 기반 artifact

### 먼저 분리할 것

- CLI application orchestration
- GitHub connector 내부 책임

### 새로 만들 것

- Claim
- Ledger
- Defect
- Evaluation
- Reground state
- BuildMap export

### 지금 만들지 않을 것

- external event bus
- graph database
- web UI
- multi-agent runtime
- organization multi-tenancy

최우선 결론:

> Stage 1은 기능 추가보다 Application Boundary Extraction이어야 한다. 그 경계 없이 Ledger를 추가하면 새 저장 계층이 CLI와 기존 모듈에 직접 결합되어 후속 변경 비용이 커진다.
