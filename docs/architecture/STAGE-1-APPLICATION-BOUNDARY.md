# PIE Stage 1 — Application Boundary Extraction

기준일: 2026-07-23  
선행 기준선: PR #1 HEAD `351c7283730f47876a98b29ef8089445e7b74b74`  
작업 브랜치: `agent/stage-1-application-boundary`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_IN_PROGRESS`

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

## 2. 범위

### 생성

```text
src/review_system/application/__init__.py
src/review_system/application/analyze_pr.py
tests/test_application_analyze_pr.py
```

### 수정

```text
src/review_system/cli.py
docs/architecture/README.md
```

### 비목표

- `github_connector.py` 내부 분해
- GitHub port/protocol 도입
- source JSON 또는 hash canonicalization 변경
- output transaction/atomicity 개선
- CLI option·exit code 변경
- graph cache 정책 변경
- namespace rename
- dependency 추가
- 다른 use case 추출

## 3. 보호 계약

| 계약 | 유지 기준 |
|---|---|
| CLI | `pie analyze-pr`와 모든 기존 option 유지 |
| Exit code | 성공 `0`, 입력·실행 오류 `2` |
| GitHub intake | 인증된 `gh` session, read-only 수집 |
| Repository binding | mismatch/unverified 기본 fail-closed |
| Head binding | PR HEAD 불일치 기본 fail-closed |
| Dirty worktree | analysis scope 변경 기본 fail-closed |
| Graph | verified local head에서 항상 재생성 |
| Rule | approved rule만 impact에 반영 |
| Source hash | `refresh_source_hash`와 `source_evidence_sha256` 유지 |
| Diff | connector가 hash한 UTF-8 bytes 그대로 저장 |
| Artifact | `github-source.json`, `impact.json`, `REPORT.md`, 선택적 diff |
| Stale diff | 신규 diff가 없으면 기존 `pull-request.diff` 삭제 |

`--refresh-graph` option은 현재 parser 호환 계약으로 남아 있으나 v0.3.0 PR 분석은 이미 항상 graph를 재생성한다. Stage 1은 이 동작을 바꾸지 않는다.

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

GitHub client는 request data가 아니라 실행 dependency다.

```python
analyze_pull_request(request, github_cli=client)
```

Stage 2에서 이 dependency를 integration port로 교체할 수 있지만 이번 Stage에서는 connector import를 유지한다.

## 5. Failure Contract

Application use case는 오류를 숨기거나 exit code로 변환하지 않는다.

- direct caller: 기존 `ValueError`·connector exception을 전달받는다.
- CLI adapter: 기존 `_error()`를 통해 stderr 출력 후 `2`를 반환한다.
- repository/head/dirty 검증 실패 시 impact artifact를 작성하지 않는다.
- diff 수집 실패는 warning과 metadata 분석으로 degrade한다.
- artifact 작성 중 filesystem 오류의 rollback semantics는 변경하지 않는다.

## 6. 설계 리뷰

### DR-1 — Connector까지 동시에 분해하는 범위 팽창

**결정:** `github_connector.py` 분리는 Stage 2로 유지한다. Stage 1은 orchestration 위치만 변경한다.

### DR-2 — argparse Namespace를 application API로 노출

**결정:** 명시적 immutable request dataclass를 사용한다. application module은 argparse를 import하지 않는다.

### DR-3 — Infrastructure option을 request에 혼합

**결정:** `timeout`, `gh_executable`은 CLI에서 `GitHubCLI` 생성에만 사용한다. use case request에는 포함하지 않는다.

### DR-4 — 리팩터링 중 artifact behavior 개선

**결정:** output atomicity, collision policy, cleanup 확대는 별도 기능 변경으로 보류한다.

### DR-5 — `--refresh-graph` 의미 변경

**결정:** 기존 항상-rebuild 동작을 보존한다. option 제거·재정의는 하지 않는다.

### DR-6 — CLI import compatibility 파괴

**결정:** `review_system.cli.main`, `cmd_analyze_pr`, `pie`, `urs`를 유지하고 wrapper만 축소한다.

## 7. 구현 검증 계획

1. 기존 CLI end-to-end tests 무수정 통과
2. direct use case 성공 테스트
3. direct use case mismatch failure 테스트
4. CLI request mapping/delegation 테스트
5. source/diff hash 동등성
6. stale diff cleanup 회귀
7. Python 3.11·3.13·3.14 전체 unittest
8. profile/finding CLI smoke
9. wheel build
10. stacked PR diff가 Stage 1 파일로만 제한되는지 검증

## 8. Rollback

Stage 1 commit을 revert하면 `cmd_analyze_pr`의 기존 inline orchestration으로 돌아간다. schema, artifact, database migration 또는 외부 state 변경이 없으므로 data rollback은 필요하지 않다.

## 9. Exit Criteria

- `cmd_analyze_pr`이 request 생성·use case 호출·summary 출력만 담당
- use case가 argparse 없이 직접 호출 가능
- 기존 CLI·artifact·hash·failure behavior 유지
- direct application tests와 전체 회귀 통과
- dependency·version·schema·workflow 변경 없음
