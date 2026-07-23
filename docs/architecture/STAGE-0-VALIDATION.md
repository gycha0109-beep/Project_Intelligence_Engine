# PIE Stage 0 — Design, Review, Implementation, Validation

기준일: 2026-07-23  
기준선: `main@c8578aa2c8096b3f0fa7652248c078702a94d023`  
작업 브랜치: `agent/stage-0-architecture-baseline`

## 1. 목적

Stage 0의 수행 절차와 검증 근거를 보존한다.

```text
상세 설계
→ 설계 리뷰
→ 문서 구현
→ 구현 리뷰
→ 정적 검증
→ GitHub PR CI
```

제품 코드, schema, package version, CLI behavior는 변경하지 않는다.

## 2. 기준선 확인

| 항목 | 확인 결과 |
|---|---|
| Repository | `gycha0109-beep/Project_Intelligence_Engine` |
| Default branch | `main` |
| Baseline commit | `c8578aa2c8096b3f0fa7652248c078702a94d023` |
| Version | `0.3.0` |
| Runtime | Python `>=3.11` |
| Runtime dependencies | PyYAML, jsonschema |
| CLI entrypoints | `pie`, `urs` → `review_system.cli:main` |
| Reported regression baseline | 79 tests PASS |
| Baseline PR workflow evidence | GitHub connector 조회에서 확인되지 않음 |

## 3. 설계 산출물

| 문서 | 역할 |
|---|---|
| `CURRENT-STATE.md` | 실제 v0.3.0 구현·계약·저장·검증 구조 |
| `TARGET-STATE.md` | 목표 Control Plane, 도메인 모델, 안전 원칙 |
| `GAP-ANALYSIS.md` | 보존·추출·확장·신규·보류 영역 |
| `MIGRATION-PLAN.md` | 선행 조건과 검증 Gate를 포함한 단계별 이행 순서 |
| `README.md` | 문서 권위·진입점·다음 Stage |

## 4. 설계 리뷰

### DR-01 — Greenfield 재작성 위험

**발견**

초기 아이디어를 그대로 적용하면 기존 URS, Gate, Graph, GitHub Intake를 새 플랫폼으로 다시 만들 가능성이 있었다.

**조치**

- 기존 v0.3.0 계약을 호환 기준선으로 고정
- 파일 artifact를 권위 원본으로 유지
- 새 기능은 projection과 관계 계층으로 추가

**상태**: CLOSED

### DR-02 — Ledger 선구현에 따른 결합 위험

**발견**

현재 `cli.py`가 application orchestration을 담당하는 상태에서 SQLite를 직접 붙이면 새 저장 계층이 CLI와 강결합된다.

**조치**

- Stage 1을 `Application Boundary Extraction`으로 지정
- Evidence Ledger는 application boundary 이후로 이동

**상태**: CLOSED

### DR-03 — 외부 Event Bus 과설계

**발견**

현재 PIE는 단일 프로세스 CLI이며 worker service나 장시간 queue가 없다.

**조치**

- 외부 broker를 P3로 보류
- 필요한 경우 in-process event interface만 먼저 도입

**상태**: CLOSED

### DR-04 — File과 DB 권위 충돌

**발견**

Ledger가 artifact 원문을 대체하면 현재의 재현성과 archive 계약을 약화할 수 있다.

**조치**

```text
Filesystem = 권위 원본
SQLite = 관계·검색·상태 index
```

Ledger rebuild를 필수 완료 조건으로 정의했다.

**상태**: CLOSED

### DR-05 — Namespace rename 조기 수행

**발견**

`review_system`을 즉시 `pie`로 변경하면 `urs` 호환, package data, import test와 installed CLI가 동시에 흔들린다.

**조치**

- 첫 단계 namespace rename 금지
- 내부 application/domain/infrastructure 경계부터 추출

**상태**: CLOSED

### DR-06 — Trust Engine 선행 조건 누락

**발견**

Evidence Ledger와 Evaluation 없이 trust score를 구현하면 검증되지 않은 점수 체계가 된다.

**조치**

- Trust Gate를 Ledger·Defect·Evaluation·Reground 이후로 이동
- 단일 AI 신뢰도 대신 task-class 기준을 사용

**상태**: CLOSED

### DR-07 — Rule confidence 의미 혼동

**발견**

현재 Rule Candidate의 confidence는 co-change association이며 defect detection precision이 아니다.

**조치**

- Evaluation Lab을 별도 Stage로 정의
- baseline/challenger와 holdout을 승인 근거로 사용

**상태**: CLOSED

## 5. 구현 범위

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

변경 내용:

- architecture baseline 링크 추가
- UTF-16/NUL 형태로 남아 있던 깨진 trailing repository title 제거
- 기존 설치·사용·안전 경계 보존

### 변경하지 않음

- `src/`
- `tests/`
- `core/`
- `schemas/`
- `packs/`
- `profiles/`
- `.github/workflows/`
- `VERSION`
- `pyproject.toml`

## 6. 구현 리뷰

### IR-01 — CLI 명령 수 오기

**발견**

Current State 초안에서 CLI 명령을 24개 및 28개로 잘못 집계했다.

**원인**

기능 그룹을 수동 집계하면서 GitHub Intake와 검증 명령 일부를 누락했다.

**검증**

`src/review_system/cli.py`의 `build_parser()`에서 `sub.add_parser(...)`를 대조했다.

**수정**

- 현재 command 수를 29개로 교정
- 기능별 표에 29개 전체 반영
- 후속 Stage에서 CLI manifest 자동 생성을 개선 과제로 등록

**상태**: CLOSED

### IR-02 — README 후행 인코딩 오염

**발견**

기존 README 마지막에 NUL 문자가 섞인 repository title이 추가되어 있었다.

**수정**

- UTF-8 정상 Markdown으로 전체 README 정리
- 기존 v0.3.0 사용 계약 보존

**상태**: CLOSED

### IR-03 — 이전 설계 문서와 현재 구현 충돌

**발견**

v0.2 설계 문서는 GitHub PR 수집을 제외 범위로 기록하지만 v0.3에서 이미 구현됐다.

**수정**

- `docs/architecture/README.md`에 현재 architecture baseline 우선 규칙 명시
- 이전 문서는 역사 기록으로 분류

**상태**: CLOSED

### IR-04 — Stage 분할 불충분

**발견**

Application 추출과 GitHub connector 분리를 같은 Stage에 넣으면 diff가 커지고 source hash 회귀 원인 격리가 어렵다.

**수정**

- Stage 1: Application Boundary Extraction
- Stage 2: GitHub Integration Extraction

으로 분리했다.

**상태**: CLOSED

### IR-05 — DB 초기 schema 과대 설계

**발견**

Ledger 최초 migration에 Run, Artifact, Claim, Evidence, Finding, Defect, Rule, Reground를 모두 넣으면 첫 schema가 검증되기 전에 고정된다.

**수정**

최초 Ledger schema를 다음으로 제한했다.

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

Defect는 다음 Stage로 분리했다.

**상태**: CLOSED

## 7. 정적 검증

### 7.1 원본 대조

| 검증 항목 | 원본 | 결과 |
|---|---|---|
| 제품명·버전 | `README.md`, `VERSION`, `pyproject.toml` | PASS |
| entrypoint | `pyproject.toml` | PASS |
| CLI 명령 29개 | `src/review_system/cli.py::build_parser` | PASS |
| source module 책임 | `src/review_system/*.py` | PASS |
| GitHub PR flow | `cmd_analyze_pr`, `github_connector.py` | PASS |
| Rule Candidate flow | `intelligence_learning.py` | PASS |
| schema inventory | `core/*.json`, `schemas/*.json` | PASS |
| packaged asset sync | `scripts/sync_package_assets.py` | PASS |
| CI matrix | `.github/workflows/ci.yml` | PASS |
| reported 79-test baseline | `docs/PIE-v0.3.0-IMPLEMENTATION-REVIEW-KO.md` | PASS |

### 7.2 문서 간 일관성

| 규칙 | 결과 |
|---|---|
| Stage 1이 Application Boundary임 | PASS |
| Ledger가 Stage 1 이후임 | PASS |
| Event Bus와 UI가 보류됨 | PASS |
| namespace rename이 첫 단계에서 금지됨 | PASS |
| Filesystem이 권위 원본임 | PASS |
| BuildMap은 export부터 시작함 | PASS |
| Trust Gate가 Evaluation 이후임 | PASS |
| 기존 v0.3.0 계약 보존이 모든 문서에 반영됨 | PASS |

### 7.3 변경 범위 검증

비교 기준:

```text
c8578aa2c8096b3f0fa7652248c078702a94d023
...
agent/stage-0-architecture-baseline
```

검증 결과:

- architecture Markdown 6개 생성
- root README 1개 수정
- 제품 코드 변경 0
- test 변경 0
- workflow 변경 0
- dependency 변경 0
- schema 변경 0

**결과**: PASS

## 8. 실행 검증 제한

작업 실행 환경에서 `github.com` DNS 접근이 차단되어 local clone과 직접 Python test 실행은 수행할 수 없었다.

대체 검증:

- GitHub connector로 baseline commit과 파일을 직접 조회
- branch 파일을 다시 fetch하여 반영 내용 확인
- commit compare로 변경 범위 확인
- PR 생성 후 repository CI를 권위 실행 검증으로 사용

이 제한은 숨기지 않으며, 원격 CI가 실패하면 Stage 0은 완료로 판정하지 않는다.

## 9. 현재 Gate

```text
STATIC REVIEW: PASS
SCOPE INTEGRITY: PASS
REMOTE CI: PENDING
FINAL STAGE 0: HOLD
```

원격 PR CI 통과 후 Final Stage 0을 PASS로 갱신한다.

## 10. 다음 작업

Stage 0 PASS 이후:

```text
Stage 1 — Application Boundary Extraction
```

첫 상세 설계 대상:

- `cmd_analyze_pr` characterisation test
- request/result DTO
- application use case
- exact artifact/hash/output compatibility
- failure cleanup과 rollback
