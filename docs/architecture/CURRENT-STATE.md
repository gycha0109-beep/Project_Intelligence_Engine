# PIE Stage 0 — Current State

기준일: 2026-07-23  
권위 기준 브랜치: `main`  
권위 기준 커밋: `c8578aa2c8096b3f0fa7652248c078702a94d023`  
제품 버전: `0.3.0`

## 1. 목적

이 문서는 Project Intelligence Engine(PIE)의 현재 구현을 후속 리팩터링 이전 상태로 고정한다. 문서의 목적은 새 플랫폼을 가정해 기존 구현을 재해석하는 것이 아니라, 현재 저장소에서 실제로 존재하는 계약·실행 경로·저장 방식·검증 경계를 명시하는 것이다.

Stage 0에서는 제품 코드와 외부 계약을 변경하지 않는다.

## 2. 현재 제품 정의

PIE v0.3.0은 Universal Review System(URS)의 검토 통제 계층 위에 다음 기능을 추가한 Python CLI 패키지다.

1. 프로젝트별 Profile과 Review Pack 선택
2. Finding·Evidence·Gate 기반 검토 실행
3. 보호 경로 snapshot과 manifest 무결성 검증
4. 정적 Project Graph 생성
5. 변경 영향 및 병렬 변경 충돌 후보 분석
6. 변경 이력 기반 Rule Candidate 발견과 사람 승인
7. GitHub PR read-only 수집과 변경 영향 분석
8. JSON·YAML·Markdown·ZIP 기반 재현 가능한 산출물 보존

현재 구조는 단일 프로세스 CLI이며 외부 서버, 메시지 브로커, 데이터베이스 또는 웹 UI를 요구하지 않는다.

## 3. 실행 표면

패키지 진입점은 두 개지만 동일한 함수를 사용한다.

```toml
pie = "review_system.cli:main"
urs = "review_system.cli:main"
```

`pie`는 제품 기본 명령이며 `urs`는 기존 계약 호환 별칭이다.

### 3.1 현재 CLI 명령 29개

| 영역 | 명령 |
|---|---|
| 버전·검증 | `version`, `validate-profile`, `resolve-profile`, `validate-findings`, `validate-run`, `validate-run-dir` |
| Review Run | `init-run`, `sync-run`, `merge-findings`, `calculate-gate`, `calculate-gate-dir`, `archive-run`, `verify-manifest` |
| 보호 기준선·Pack | `select-packs`, `snapshot-protected`, `verify-protected` |
| Intelligence | `validate-graph`, `validate-intelligence-config`, `validate-rules`, `index-project`, `analyze-change`, `compare-changes`, `capture-state` |
| Rule Learning | `discover-rule-candidates`, `approve-rule` |
| GitHub Intake | `validate-github-source`, `init-project`, `github-doctor`, `analyze-pr` |

위 표는 `build_parser()`에 선언된 subcommand를 기능별로 분류한 것이다. 후속 단계에서는 CLI manifest를 코드에서 생성해 문서와 구현의 수동 집계 불일치를 제거한다.

## 4. 소스 모듈 구조

현재 Python namespace는 `src/review_system`이다.

| 모듈 | 현재 책임 |
|---|---|
| `baseline.py` | 보호 경로 수집, SHA-256 snapshot 생성·비교, path/symlink 방어 |
| `cli.py` | argument parsing, use-case orchestration, 출력과 exit code 결정 |
| `gate.py` | 제한된 expression 평가, Finding 지표 파생, Gate 결정 |
| `github_connector.py` | `gh` 실행, 인증·대상·repository 검증, PR 수집·정규화·hash 검증 |
| `intelligence_config.py` | Intelligence config와 Rule 검증, 경로 정규화·매칭 |
| `intelligence_graph.py` | 정적 파일·심볼·참조 graph 생성 및 graph hash |
| `intelligence_impact.py` | 변경 영향 BFS, Rule 매칭, Review Pack·Test 추천, 병렬 변경 비교 |
| `intelligence_learning.py` | co-change Rule Candidate 발견·병합·승인 |
| `intelligence_report.py` | impact·comparison·PR Markdown 보고서 생성 |
| `intelligence_state.py` | Git revision, worktree, graph·rule·active change 상태 snapshot |
| `io.py` | JSON/YAML 입출력, atomic pair write |
| `merge.py` | Finding 병합과 충돌 분리 |
| `packs.py` | Review Pack 선택·버전 lock |
| `paths.py` | package asset 경로 해석 |
| `profile.py` | Profile 상속·검증·repository root 해석 |
| `project_init.py` | preset 기반 `.review` 초기화와 `.gitignore` 보완 |
| `run.py` | Review Run 초기화·동기화·검증·Gate·manifest·archive |
| `validation.py` | JSON Schema 및 추가 정책 검증 |
| `version.py` | 설치 metadata 또는 packaged VERSION 해석 |

### 4.1 현재 결합 상태

`cli.py`가 parser와 application orchestration을 함께 담당한다. `analyze-pr`은 다음 작업을 한 함수에서 연결한다.

```text
입력 검증
→ GitHub 수집
→ local/remote repository 검증
→ local HEAD/PR HEAD 검증
→ dirty worktree 검증
→ Project State 수집
→ Graph 재생성
→ Approved Rule 로드
→ Impact 분석
→ JSON/Markdown/Diff 저장
```

이 흐름은 동작 경계가 명확하지만 application use case와 CLI adapter가 분리되지 않았다.

`github_connector.py`도 command runner, target parser, retry, collection, normalization, hash와 source validation을 단일 모듈에서 담당한다.

## 5. 현재 도메인 계약

### 5.1 Finding

Finding은 한 Review Run 안에서 관찰된 문제를 표현한다.

주요 필드:

- `id`, `title`, `category`
- `severity`: `P0`, `P1`, `P2`, `P3`, `INFO`
- `confidence`: `HYPOTHESIS`, `SUPPORTED`, `CONFIRMED`, `RESOLVED`, `REJECTED`
- `status`: `OPEN`, `ACCEPTED`, `FIXED`, `CLOSED`, `REJECTED`
- `scope`
- `evidence[]`
- `reproduction`
- `impact`
- `recommended_action`
- `verification[]`
- `acceptance`

Finding은 실행 단위 객체이며 여러 실행에 걸친 동일 근본 결함의 정체성을 제공하지 않는다.

### 5.2 Evidence

Evidence는 Finding 내부 배열로 보존된다.

| 레벨 | 의미 |
|---|---|
| E0 | 의견 또는 근거 없는 가설 |
| E1 | 코드·설정·문서 근거 |
| E2 | 실행 경로 또는 데이터 흐름 증명 |
| E3 | 집중 자동 테스트 또는 결정적 수동 재현 |
| E4 | 실제 또는 대표 기술 스택 재현 |
| E5 | 수정 후 필수 전체 회귀 증거 |

현재 Evidence는 강한 품질 정책을 가지지만 독립 ID와 전역 관계가 없다. 동일 Evidence가 여러 Claim 또는 Finding을 지지하는 관계를 직접 조회할 수 없다.

### 5.3 Review Run

Review Run은 `run_id`, `project_id`, `mode`, metrics를 중심으로 검토 실행을 표현한다. 파일 기반 Run directory가 실행 원본이다.

대표 파일:

```text
review-run.yml
findings.json
review-input.md
verification-log.md
accepted-risks.md
gate-result.json
protected-baseline.json
initial-manifest.sha256
manifest.sha256
```

### 5.4 Gate

Gate는 deterministic policy expression으로 계산한다.

강도 순서:

```text
FAIL > HOLD > CONDITIONAL_PASS > PASS
```

현재 기본 정책은 확인된 blocker, baseline test 실패, protected baseline 변경, integration evidence 누락, migration replay 미검증, fixed-but-unverified blocker, residual risk 등을 판정에 반영한다.

### 5.5 Project Rule

Rule 상태는 `candidate`, `approved`, `rejected`, `retired`를 허용한다.

현재 흐름:

```text
Historical Change Sets
→ Co-change Candidate Discovery
→ Candidate File
→ Explicit Human Approval
→ Approved Rule File
→ Impact Analysis
```

승인 시 승인자·시각·후보 ID와 선택적 rationale을 기록한다. 그러나 Defect, 회귀 fixture, baseline/challenger evaluation result는 필수 연결 대상이 아니다.

## 6. Project Intelligence 구조

### 6.1 Graph

Graph는 정적 repository 상태에서 다음을 생성한다.

- 파일 node
- 언어별 symbol node
- import·reference·Markdown link 등 edge
- component 매핑
- warnings
- stats
- `graph_sha256`

지원 분석:

- Python AST
- JavaScript/TypeScript import·declaration
- Java/Kotlin package·import·declaration
- SQL object definition·reference
- Markdown local link

Graph 관계는 구조 근거이며 런타임 동작 증명이 아니다.

### 6.2 Impact

Impact 분석은 direct changed files에서 graph dependent를 제한 깊이로 탐색하고 다음을 합성한다.

- 직접 변경
- dependent files
- components
- selected Review Packs와 선택 근거
- approved rules
- recommended tests
- limitations

### 6.3 Learning

Learning은 change set별 경로 또는 component 공동 변경을 비대칭 association으로 계산한다.

현재 지표:

- `sample_count`
- `source_change_count`
- `history_size`
- `confidence`
- `support`

이 값은 인과 확률이나 결함 탐지 성능이 아니다.

## 7. GitHub PR Intake

`analyze-pr`은 인증된 GitHub CLI 세션을 재사용하며 token을 설정 파일에 저장하지 않는다.

수집 대상:

- repository metadata
- PR metadata
- changed files
- commits
- CI checks
- issue comments
- reviews
- inline review comments
- diff(수집 가능한 경우)

기본 산출물:

```text
.pie/pr-<number>/
├─ github-source.json
├─ pull-request.diff
├─ impact.json
└─ REPORT.md
```

무결성 경계:

- canonical JSON 기반 `source_sha256`
- impact의 `source_evidence_sha256`
- diff byte SHA-256
- local/remote repository mismatch 기본 차단
- local HEAD/PR head mismatch 기본 차단
- scoped dirty worktree 기본 차단
- diff 실패 시 metadata 분석은 warning과 함께 유지

## 8. 저장 모델

현재 권위 원본은 파일이다.

| 데이터 | 저장 위치 |
|---|---|
| Review Run | 지정한 run directory |
| PR 분석 | `.pie/pr-<number>` |
| Project Graph | `.review/intelligence/graph.json` 또는 사용자 지정 경로 |
| Candidate Rule | `.review/intelligence/candidate-rules.yml` |
| Approved Rule | `.review/intelligence/approved-rules.yml` |
| Project State | 사용자 지정 JSON |
| Archive | ZIP |

장점:

- 이식 가능
- 사람이 직접 확인 가능
- Git과 ZIP으로 보존 가능
- DB 장애나 schema migration이 없음

한계:

- 실행 간 join 불가
- Finding 재발 추적 불가
- Claim–Evidence 관계 조회 불가
- Rule 효과의 종단 비교 불가
- stale 문서·정책·증거 상태 조회 불가
- 동일 artifact 중복과 계보를 조회하기 어려움

## 9. Schema와 정책 자산

### 9.1 독립 root 자산

- `core/finding-schema.json`
- `core/project-profile-schema.json`
- `core/review-run-schema.json`
- `schemas/intelligence-config.schema.json`
- `schemas/project-rule.schema.json`
- `core/default-gate-policy.yml`
- Evidence·Confidence·Severity·Lifecycle Markdown 정책
- Review Pack과 stack/profile preset

### 9.2 packaged asset 복제

배포 wheel이 root 자산을 포함할 수 있도록 `scripts/sync_package_assets.py`가 다음 root 디렉터리를 `src/review_system/assets`로 복제한다.

```text
core
packs
templates
schemas
intelligence
profiles/stacks
profiles/examples
bootstrap/.review/intelligence
VERSION
```

현재 운영 모델:

```text
root assets = 편집 권위 원본
packaged assets = 생성된 배포 복제본
```

`test_asset_sync.py`가 drift를 검증하며 CI도 package asset sync 후 전체 테스트를 실행한다.

위 구조는 배포 단순성이 높지만, 사람이 generated asset을 직접 수정하면 양쪽이 갈라질 수 있다. 생성 경계와 수정 금지 표시는 더 명시적으로 문서화할 필요가 있다.

## 10. 패키징과 의존성

- Python: `>=3.11`
- Build backend: setuptools
- 런타임 의존성:
  - `PyYAML>=6.0.3`
  - `jsonschema>=4.26.0`
- package entrypoints: `pie`, `urs`
- package data: `src/review_system/assets/**/*`

현재 외부 DB·ORM·웹 프레임워크·메시지 브로커 의존성은 없다.

## 11. 테스트와 CI 기준선

현재 보고된 v0.3.0 회귀 기준선:

```text
Ran 79 tests
OK
```

테스트 영역:

- asset sync
- protected baseline
- CLI
- Gate
- GitHub connector
- Project Graph
- Impact
- Rule Learning
- report
- Finding merge
- Pack routing
- Profile inheritance와 path traversal
- project initialization과 PR end-to-end
- Review Run
- archive와 manifest
- schema 및 policy validation

CI workflow:

- push와 pull request에서 실행
- Python 3.11, 3.13, 3.14 matrix
- editable install
- package asset sync
- unittest discovery
- CLI/profile/finding smoke
- wheel build

Stage 0 원격 감사 시 기준 커밋에 연결된 PR workflow run과 combined status는 GitHub 커넥터에서 확인되지 않았다. 따라서 79개 PASS는 저장소에 보존된 v0.3.0 검증 보고서를 현재 근거로 사용하며, Stage 0 PR에서 원격 CI를 다시 관찰한다.

## 12. 현재 강점

1. 결정적 Gate와 AI 서술의 분리
2. Evidence 수준과 Confidence의 분리
3. P0/P1 안전 정책
4. protected path·manifest·source hash 무결성
5. path traversal·symlink·repository mismatch 방어
6. Candidate Rule 자동 승인 금지
7. 정적 추론의 한계를 보고서에 명시
8. read-only GitHub integration
9. 작은 런타임 의존성
10. 파일 기반 산출물의 높은 재현성

## 13. 현재 구조적 제약

1. CLI adapter와 application orchestration이 결합되어 있다.
2. Run 간 데이터를 연결하는 Ledger가 없다.
3. Claim이 독립 도메인 객체가 아니다.
4. Finding을 장기 결함으로 묶는 Defect Registry가 없다.
5. Rule 승격 전 baseline/challenger 평가가 없다.
6. Graph edge에 verified-at·source hash·stale state가 없다.
7. BuildMap과의 공식 export contract가 없다.
8. `review_system` namespace가 URS 호환 코어와 PIE application을 동시에 표현한다.
9. root asset과 package asset의 생성 경계가 코드 구조만 보고는 즉시 드러나지 않는다.
10. 문서에 수동으로 기록된 명령·테스트 수치가 구현과 어긋날 수 있다.

## 14. Stage 0 판정

현재 PIE는 재작성 대상이 아니다. 이미 다음 기반을 보유한다.

```text
Review Lifecycle
+ Evidence Policy
+ Deterministic Gate
+ Protected Baseline
+ Project Graph
+ Impact Analysis
+ Rule Candidate/Approval
+ GitHub Evidence Intake
+ Reproducible File Archive
```

후속 설계는 이 자산을 보존하고, 파일 기반 권위 원본 위에 조회·관계·평가 계층을 추가하는 방식으로 진행한다.
