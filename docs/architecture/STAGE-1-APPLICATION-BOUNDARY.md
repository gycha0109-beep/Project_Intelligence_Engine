# PIE Stage 1A — AnalyzePullRequest Application Boundary

기준일: 2026-07-23  
선행 기준선: PR #1 HEAD `351c7283730f47876a98b29ef8089445e7b74b74`  
작업 브랜치: `agent/stage-1-application-boundary`  
Stacked PR: `#2`  
상태: `PASS`

## 1. 목적

Stage 1의 첫 increment는 `cmd_analyze_pr`에 결합된 application orchestration을 CLI adapter에서 분리한다.

```text
argparse Namespace
→ AnalyzePullRequestRequest
→ analyze_pull_request use case
→ AnalyzePullRequestResult
→ CLI summary / exit code
```

기존 GitHub 수집, graph, impact, source hash, artifact와 failure-path 계약은 변경하지 않는다.

## 2. 최종 범위

### 생성

```text
src/review_system/application/__init__.py
src/review_system/application/analyze_pr.py
tests/test_application_analyze_pr.py
docs/architecture/STAGE-1-APPLICATION-BOUNDARY.md
```

### 수정

```text
src/review_system/cli.py
docs/architecture/README.md
```

### 변경하지 않음

- `github_connector.py` 내부 구조
- source JSON schema와 canonical hash
- Review Run·Finding·Gate schema
- CLI option·exit code
- graph rebuild 정책
- package version
- runtime dependency
- preset·pack·workflow
- 다른 application use case

## 3. 보호 계약

| 계약 | 유지 결과 |
|---|---|
| CLI | `pie analyze-pr`, `urs analyze-pr`와 기존 option 유지 |
| Exit code | 성공 `0`, 입력·실행 오류 `2` 유지 |
| GitHub intake | 인증된 `gh` session 기반 read-only 수집 유지 |
| Repository binding | mismatch/unverified 기본 fail-closed 유지 |
| Head binding | PR HEAD 불일치 기본 fail-closed 유지 |
| Dirty worktree | analysis scope 변경 기본 fail-closed 유지 |
| Graph | verified local head에서 항상 재생성 유지 |
| Rule | approved rule만 impact에 반영 |
| Source hash | `source_sha256`, `source_evidence_sha256` 유지 |
| Diff | connector가 hash한 UTF-8 bytes 그대로 저장 |
| Artifact | source, impact, report, 선택적 diff 경로 유지 |
| Stale diff | 신규 diff가 없으면 기존 diff 삭제 유지 |
| Empty output | 빈 `--output-dir`은 기존처럼 default PR 경로 사용 |

`--refresh-graph`는 parser 호환 계약으로 남아 있다. v0.3.0 PR 분석은 이미 항상 graph를 재생성했으며 Stage 1A도 같은 동작을 유지한다.

## 4. Application Contract

```python
@dataclass(frozen=True)
class AnalyzePullRequestRequest:
    pull_request: str
    repository_root: str | Path = "."
    repository: str | None = None
    profile: str | None = None
    config: str | None = None
    graph: str | None = None
    approved_rules: str | None = None
    refresh_graph: bool = False
    skip_diff: bool = False
    skip_discussion: bool = False
    allow_repository_mismatch: bool = False
    allow_head_mismatch: bool = False
    allow_dirty_worktree: bool = False
    max_depth: int = 3
    output_dir: str | Path | None = None
```

```python
@dataclass(frozen=True)
class AnalyzePullRequestResult:
    source: dict
    impact: dict
    output_dir: Path
    source_path: Path
    impact_path: Path
    report_path: Path
    diff_path: Path | None
    changed_files: tuple[str, ...]
```

Application dependency:

```python
analyze_pull_request(
    request,
    github_cli=client,
    capture_state=state_reader,
)
```

- `github_cli`는 request data가 아니라 execution dependency다.
- `capture_state`를 명시적으로 전달해 CLI test seam과 후속 port extraction 경계를 보존한다.
- Stage 2에서 GitHub concrete dependency를 integration port로 교체할 수 있다.

## 5. Failure Contract

Application use case는 오류를 exit code로 변환하지 않는다.

- direct caller는 기존 `ValueError`와 connector exception을 전달받는다.
- CLI adapter만 기존 `_error()`로 stderr와 exit code `2`를 만든다.
- repository/head/dirty 검증 실패 시 impact artifact를 작성하지 않는다.
- diff 수집 실패는 warning과 metadata 분석으로 degrade한다.
- artifact write rollback semantics는 이번 Stage에서 변경하지 않았다.

## 6. 설계 리뷰

### DR-1 — Connector까지 동시에 분해하는 범위 팽창

**결정:** `github_connector.py` 분리는 Stage 2로 유지한다. 이번 increment는 orchestration 위치만 변경한다.

### DR-2 — argparse Namespace 노출

**결정:** immutable request dataclass를 사용하며 application module은 argparse를 import하지 않는다.

### DR-3 — Infrastructure option 혼입

**결정:** `timeout`, `gh_executable`은 CLI가 `GitHubCLI`를 만들 때만 사용한다.

### DR-4 — 리팩터링 중 artifact 개선 혼합

**결정:** output atomicity와 collision policy는 별도 기능 Stage로 보류한다.

### DR-5 — `--refresh-graph` 의미 변경

**결정:** 기존 항상-rebuild behavior를 보존한다.

### DR-6 — Public import compatibility

**결정:** `review_system.cli.main`, `cmd_analyze_pr`, `pie`, `urs`를 유지한다.

## 7. 구현 리뷰와 보완

### IR-1 — Hidden project-state test seam

**발견**

기존 head/dirty tests는 `review_system.cli.capture_project_state`를 patch했다. 단순 이동 후 application module의 고정 참조를 사용하면 fixture가 적용되지 않아 fail-closed tests가 거짓 성공했다.

**보완**

- `capture_state` execution dependency 추가
- CLI wrapper가 현재 `capture_project_state` symbol을 명시적으로 전달
- 기존 head mismatch와 dirty-worktree tests 무수정 통과

**상태:** CLOSED

### IR-2 — Empty output path behavior drift

**발견**

기존 조건은 빈 문자열을 미지정으로 취급했지만 `is not None` 사용 시 현재 디렉터리로 해석될 수 있었다.

**보완**

- 기존 truthiness 조건 복원
- empty output direct-use-case regression 추가

**상태:** CLOSED

### IR-3 — Transient test output 잔존

**발견**

원격 진단 과정의 `stage1-unittest-output.txt`가 중간 commit에 포함됐다.

**보완**

최종 branch와 PR diff에서 삭제했다.

**상태:** CLOSED

### IR-4 — One-time workflow 잔존

**발견**

clone 불가 환경에서 CLI 파일을 안전하게 refactor하기 위해 사용한 일회성 workflow가 중간 branch에 남았다.

**보완**

최종 diff에서 workflow와 refactor script를 모두 제거했다. 제품 CI workflow는 변경하지 않았다.

**상태:** CLOSED

### IR-5 — Branch write race

**발견**

bot push와 connector write가 근접 실행되며 PR metadata가 일시적으로 과거 HEAD를 표시했다.

**보완**

- branch ref의 실제 파일을 재조회
- stacked base와 branch ref를 `compare_commits`로 재검증
- 최종 changed-file 목록을 권위 범위로 사용

**상태:** CLOSED

## 8. 테스트

추가된 direct application tests:

1. artifact와 source/diff hash 계약
2. repository mismatch fail-closed
3. empty output default path
4. CLI argument mapping과 use-case delegation

기존 tests가 계속 검증하는 경로:

- PR intake end-to-end
- stale diff cleanup
- cached graph rebuild
- repository unverified/mismatch
- head mismatch override
- dirty-worktree override
- GitHub source validation

## 9. 검증 결과

Implementation matrix run: `29989642844`

| 검증 | Python 3.11 | Python 3.13 | Python 3.14 |
|---|---:|---:|---:|
| Package install | PASS | PASS | PASS |
| Asset sync | PASS | PASS | PASS |
| 102 unit tests | PASS | PASS | PASS |
| `urs version` | PASS | PASS | PASS |
| 4 preset profile validation | PASS | PASS | PASS |
| Finding validation | PASS | PASS | PASS |
| Wheel build | PASS | PASS | PASS |

최종 판정의 권위 근거는 위 implementation matrix와 함께 **PR #2 최신 HEAD에 연결된 GitHub PR check**다. 문서에 특정 최종 HEAD SHA를 고정해 다시 stale하게 만들지 않으며, 이후 commit이 추가되면 PR check를 다시 통과해야 한다.

Stacked base 대비 최종 변경 범위:

```text
docs/architecture/README.md
docs/architecture/STAGE-1-APPLICATION-BOUNDARY.md
src/review_system/application/__init__.py
src/review_system/application/analyze_pr.py
src/review_system/cli.py
tests/test_application_analyze_pr.py
```

## 10. Rollback

Stage 1A 변경을 revert하면 `cmd_analyze_pr`의 inline orchestration으로 복귀한다. schema, migration, external state 또는 artifact format 변경이 없어 data rollback은 필요하지 않다.

## 11. 판정

```text
Detailed Design: PASS
Design Review: PASS
Implementation: PASS
Implementation Review: PASS
Regression Verification: PASS
Compatibility Decision: PRESERVED
Stage 1A Gate: PASS
```

## 12. 다음 작업

PR #1과 stacked PR #2가 병합된 뒤 Stage 1B에서 다음 use case를 분리한다.

```text
IndexProject
AnalyzeChange
```

같은 절차로 request/result contract, thin CLI adapter, direct tests, failure compatibility를 적용한다.
