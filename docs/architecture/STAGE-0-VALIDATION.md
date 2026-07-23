# PIE Stage 0 — Design, Review, Implementation, Validation

기준일: 2026-07-23  
기준선: `main@c8578aa2c8096b3f0fa7652248c078702a94d023`  
작업 브랜치: `agent/stage-0-architecture-baseline`  
최종 검증 대상: `e3f82ebed9084b2285470f9ae45ca6a8f22862b1`

## 1. 목적

Stage 0은 PIE v0.3.0의 실제 구조를 고정하고, 기존 검증 코어를 보존하면서 Project Intelligence Control Plane으로 확장할 단계와 경계를 정의한다.

수행 순서:

```text
상세 설계
→ 설계 리뷰
→ 구현
→ 구현 리뷰
→ 실패 진단
→ 최소 보완
→ 전체 검증
```

원래 Stage 0 범위는 문서화뿐이었으나, 전체 CI 검증에서 Python 3.11 지원 계약을 위반하는 기존 경로 glob 결함이 발견됐다. 검증을 통과한 척하지 않고 근본 원인을 수정하고 회귀 테스트를 추가했다.

## 2. 기준선 확인

| 항목 | 결과 |
|---|---|
| Repository | `gycha0109-beep/Project_Intelligence_Engine` |
| Default branch | `main` |
| Baseline commit | `c8578aa2c8096b3f0fa7652248c078702a94d023` |
| Product version | `0.3.0` |
| Runtime contract | Python `>=3.11` |
| Runtime dependencies | PyYAML, jsonschema |
| CLI entrypoints | `pie`, `urs` → `review_system.cli:main` |
| CLI subcommands | 29 |
| Stored v0.3.0 report | 79 tests PASS |
| Current discovered suite before fix | 96 tests |
| Current suite after new regression tests | 98 tests |

기존 문서의 79개는 v0.3.0 구현 시점의 저장된 검증 결과다. 현재 repository의 실제 unittest discovery 결과는 96개였으며, Stage 0에서 호환성 테스트 2개를 추가해 98개가 됐다.

## 3. 설계 산출물

| 문서 | 역할 |
|---|---|
| `CURRENT-STATE.md` | 실제 v0.3.0 코드·계약·저장·검증 구조 |
| `TARGET-STATE.md` | 목표 Control Plane과 도메인·저장 원칙 |
| `GAP-ANALYSIS.md` | READY·EXTEND·EXTRACT·NEW·DEFER 판정 |
| `MIGRATION-PLAN.md` | 선행 조건과 완료 Gate가 있는 단계별 이행 계획 |
| `README.md` | 아키텍처 문서 권위와 진입점 |
| `STAGE-0-VALIDATION.md` | 설계·리뷰·구현·검증 기록 |

## 4. 설계 리뷰 결과

### DR-01 — Greenfield 재작성 위험

**발견**

새 플랫폼 개념을 그대로 구현하면 현재 URS, Gate, Graph, Rule Learning과 GitHub Intake를 중복 구축할 가능성이 있었다.

**결정**

- PIE v0.3.0을 확장 기준선으로 유지
- 기존 CLI·schema·artifact·Gate 계약 보존
- 새 기능은 application boundary와 projection 계층으로 추가

**상태**: CLOSED

### DR-02 — Ledger 선구현 결합 위험

**발견**

`cli.py`가 orchestration까지 담당하는 상태에서 SQLite를 붙이면 Ledger가 CLI에 직접 결합된다.

**결정**

- Stage 1: Application Boundary Extraction
- Stage 2: GitHub Integration Extraction
- Ledger는 위 경계가 안정된 뒤 구현

**상태**: CLOSED

### DR-03 — 권위 원본 충돌

**발견**

Ledger가 기존 파일 artifact를 대체하면 archive·hash·재현 계약이 약해진다.

**결정**

```text
Filesystem Artifact = 권위 원본
SQLite Ledger        = 재구축 가능한 관계·검색·상태 index
```

**상태**: CLOSED

### DR-04 — 조기 과설계

**보류 항목**

- 외부 Event Bus
- Web UI
- graph database
- namespace 전면 rename
- multi-agent runtime
- 단일 AI trust score

현재 단일 프로세스 CLI에서 필요한 것은 in-process 경계와 안정된 데이터 계약이다.

**상태**: CLOSED

### DR-05 — Rule confidence 의미 혼동

현재 Rule Candidate의 `confidence`는 공동 변경 association이다. defect detection precision·recall이 아니다.

**결정**

Rule Evaluation을 별도 Stage로 두고 baseline/challenger, labeled dataset, holdout과 repeatability를 승인 근거로 사용한다.

**상태**: CLOSED

## 5. 초기 구현

### 생성

```text
docs/architecture/README.md
docs/architecture/CURRENT-STATE.md
docs/architecture/TARGET-STATE.md
docs/architecture/GAP-ANALYSIS.md
docs/architecture/MIGRATION-PLAN.md
docs/architecture/STAGE-0-VALIDATION.md
```

### 수정

```text
README.md
```

- architecture baseline 링크 추가
- NUL/UTF-16 형태의 깨진 후행 repository title 제거
- 기존 설치·사용·안전 설명 보존

## 6. 구현 리뷰 결과

### IR-01 — CLI 명령 수 오기

초안의 24개·28개 집계를 `build_parser()`와 대조해 29개로 교정했다.

후속 개선:

- CLI manifest 자동 생성
- 문서 수동 집계 제거

**상태**: CLOSED

### IR-02 — 버전 문서 간 충돌

v0.2 설계 문서는 GitHub PR 수집을 제외 범위로 기록하지만 v0.3에서 이미 구현됐다.

**조치**

`docs/architecture/README.md`에 현재 architecture baseline 우선 규칙을 명시했다. 이전 버전 문서는 역사 기록으로 유지한다.

**상태**: CLOSED

### IR-03 — Stage 분할 부족

Application 추출과 GitHub connector 분리를 한 Stage에 넣으면 source hash 회귀 원인 격리가 어려웠다.

**조치**

두 Stage로 분리했다.

**상태**: CLOSED

### IR-04 — 최초 Ledger schema 과대 설계

Finding·Defect·Policy·Reground를 첫 migration에 모두 넣지 않는다.

최초 Ledger 범위:

```text
schema_migrations
runs
artifacts
claims
evidence
claim_evidence
decisions
policy_snapshots
```

**상태**: CLOSED

## 7. CI에서 발견된 기준선 결함

### DEF-STAGE0-001 — Python 3.11 trailing recursive glob incompatibility

**증상**

Python 3.11 matrix에서 96개 테스트 중 6개 실패:

1. protected baseline 수정·추가·삭제 미탐지
2. `src/**` project graph가 파일 0개로 생성
3. Python import edge 누락
4. TypeScript import edge 누락
5. Markdown documents edge 누락
6. PR impact dependent file 누락

Python 3.13과 3.14에서는 동일 테스트가 통과했다.

**근본 원인**

`pathlib.Path.glob()`의 버전별 trailing `/**` 동작 차이다.

```text
src/**
protected/**
docs/**
```

Python 3.11에서는 위 패턴이 디렉터리는 반환하지만 기대한 descendant file을 모두 반환하지 않았다. 결과적으로 Graph와 protected snapshot이 비어 있거나 불완전했다.

**수정**

공통 helper를 추가했다.

```text
src/review_system/path_globs.py
```

trailing recursive pattern을 다음 두 패턴으로 확장한다.

```text
src/**
src/**/*
```

적용 위치:

- `baseline.collect_protected_files`
- `intelligence_graph._iter_files`

기존 `seen` set이 중복 파일을 제거하며, 원래 패턴도 유지하므로 symlink directory 차단 경로를 약화하지 않는다.

**회귀 테스트**

```text
tests/test_path_globs.py
```

- trailing `/**`가 explicit descendant pattern을 추가하는지 검증
- `**/*`와 같은 비대상 패턴은 변경하지 않는지 검증
- 기존 graph·baseline·PR end-to-end 테스트가 Python 3.11 실제 동작을 검증

**상태**: RESOLVED

## 8. 진단 절차와 정리

GitHub Actions log 출력이 커넥터 표시 한계로 잘렸기 때문에 Python 3.11 unittest 원문을 일시적으로 workflow artifact로 수집했다.

진단 후:

- 원인 확인
- 최소 수정 적용
- 회귀 테스트 추가
- 임시 artifact upload step 제거
- `.github/workflows/ci.yml`을 기준선과 동일한 내용으로 복원

최종 diff에는 진단용 workflow 변경이 남아 있지 않다.

## 9. 최종 변경 범위

기준 비교:

```text
c8578aa2c8096b3f0fa7652248c078702a94d023
...
e3f82ebed9084b2285470f9ae45ca6a8f22862b1
```

최종 변경 파일 11개:

```text
README.md
docs/architecture/CURRENT-STATE.md
docs/architecture/GAP-ANALYSIS.md
docs/architecture/MIGRATION-PLAN.md
docs/architecture/README.md
docs/architecture/STAGE-0-VALIDATION.md
docs/architecture/TARGET-STATE.md
src/review_system/baseline.py
src/review_system/intelligence_graph.py
src/review_system/path_globs.py
tests/test_path_globs.py
```

변경 없음:

- public schema
- package version
- runtime dependency
- CLI command와 syntax
- Gate policy
- GitHub source schema와 hash contract
- Review Pack
- preset
- workflow 최종 내용

## 10. 최종 검증

GitHub Actions run: `29987144496`

각 matrix에서 다음 전체 단계를 실행했다.

```text
pip install -e .
python scripts/sync_package_assets.py
python -m unittest discover -s tests -v
urs version
urs validate-profile journey-connect
urs validate-profile bejewely
urs validate-profile buildmap
urs validate-profile generic-webapp
urs validate-findings examples/findings.sample.json
pip wheel . --no-deps --wheel-dir dist-ci
```

### 결과

| Python | 98 tests | Asset sync | CLI smoke | Profile/Finding validation | Wheel |
|---|---:|---:|---:|---:|---:|
| 3.11 | PASS | PASS | PASS | PASS | PASS |
| 3.13 | PASS | PASS | PASS | PASS | PASS |
| 3.14 | PASS | PASS | PASS | PASS | PASS |

### 무결성 확인

- Python 3.11 재현 실패 6개 모두 해소
- Python 3.13·3.14 회귀 없음
- 임시 workflow 진단 변경 제거
- changed files가 문서 7개, source 3개, test 1개로 제한됨
- dependency·schema·version 변경 없음

## 11. 실행 환경 제한

현재 작업 환경에서는 `github.com` DNS 접근이 차단되어 local clone 기반 전체 실행이 불가능했다.

대체 절차:

- GitHub connector로 기준선·파일·commit 직접 확인
- GitHub Actions artifact로 실패 원문 수집
- 원격 CI matrix를 권위 실행 증거로 사용
- branch compare로 최종 범위 확인

이 제한 때문에 검증을 생략하지 않았으며, 실제 repository runner에서 전체 패키지 경로를 실행했다.

## 12. 최종 Gate

```text
DESIGN REVIEW:          PASS
IMPLEMENTATION REVIEW:  PASS
SCOPE INTEGRITY:        PASS
PYTHON 3.11:            PASS
PYTHON 3.13:            PASS
PYTHON 3.14:            PASS
CLI / ASSET / WHEEL:    PASS
FINAL STAGE 0:          PASS
```

## 13. 다음 작업

Stage 1:

```text
Application Boundary Extraction
```

첫 상세 설계 대상:

1. `cmd_analyze_pr` characterisation test 보강
2. request/result DTO
3. `application/analyze_pr.py` use case 추출
4. CLI adapter 축소
5. source JSON·diff·impact·report의 exact compatibility
6. mismatch·dirty worktree·head mismatch failure path
7. output collision과 partial-write cleanup

Stage 1에서도 동일하게 상세 설계 → 리뷰 → 구현 → 리뷰 → 전체 matrix 검증 순서를 적용한다.
