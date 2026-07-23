# PIE Stage 1B — IndexProject / AnalyzeChange Application Boundaries

기준일: 2026-07-23  
선행 기준선: PR #2 HEAD `57d22ac7673572e6ab33d2458d868663919f5133`  
작업 브랜치: `agent/stage-1b-index-analyze-boundary`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

Stage 1B는 `cmd_index_project`와 `cmd_analyze_change`에 남아 있는 application orchestration을 CLI adapter에서 분리한다.

```text
argparse Namespace
→ immutable Request
→ application use case
→ immutable Result
→ CLI summary / exit code
```

Stage 1A에서 확정한 원칙을 동일하게 적용한다.

- application layer는 argparse를 import하지 않는다.
- CLI는 argument mapping, dependency 전달, error-to-exit-code 변환, summary 출력만 담당한다.
- 기존 graph, impact, rule, Markdown, path와 failure 계약을 변경하지 않는다.

## 2. 최종 목표 구조

```text
src/review_system/application/
├─ __init__.py
├─ _project_context.py
├─ analyze_pr.py
├─ index_project.py
└─ analyze_change.py
```

### 신규 파일

```text
src/review_system/application/_project_context.py
src/review_system/application/index_project.py
src/review_system/application/analyze_change.py
tests/test_application_index_analyze.py
docs/architecture/STAGE-1B-INDEX-ANALYZE-BOUNDARY.md
```

### 수정 파일

```text
src/review_system/application/__init__.py
src/review_system/cli.py
docs/architecture/README.md
```

## 3. 비목표

- `compare-changes` application 추출
- `capture-state` application 추출
- graph builder 또는 impact analyzer 내부 변경
- graph schema 또는 rule schema 변경
- output atomicity·transaction 개선
- CLI option·exit code·summary 문구 변경
- package namespace rename
- dependency·version·workflow 변경
- Evidence Ledger 또는 Run identity 도입

## 4. 보호 계약

### 4.1 IndexProject

| 계약 | 유지 기준 |
|---|---|
| Profile | 기존 `validate_profile_file` 사용 |
| Root | explicit `--repository-root` 우선, 없으면 profile 기준 해석 |
| Config | 기존 `load_intelligence_config` 사용 |
| Graph | scope include/exclude, components, max size 전달 유지 |
| Artifact | 기존 JSON 구조와 output path 유지 |
| Error | application exception 전파, CLI가 stderr + exit `2` 변환 |
| Summary | files, edges, warnings, output 필드 유지 |

### 4.2 AnalyzeChange

| 계약 | 유지 기준 |
|---|---|
| Graph | object 여부와 `validate_project_graph` 검증 유지 |
| Rules | 지정된 approved-rules 파일 부재 시 fail-closed |
| Input | `--files` 또는 `--base` 상호배타 계약 유지 |
| Git diff | repository root, base, head 전달 유지 |
| Impact | configured packs, approved rules, max depth, revisions 유지 |
| JSON | 기존 impact JSON 구조와 output path 유지 |
| Markdown | 요청 시 parent 생성 후 기존 renderer로 저장 |
| Summary | direct, impacted, packs, output 필드 유지 |
| Error | application exception 전파, CLI가 exit `2` 변환 |

## 5. Application Contracts

### 5.1 IndexProject

```python
@dataclass(frozen=True)
class IndexProjectRequest:
    profile: str | Path
    config: str | Path
    output: str | Path
    repository_root: str | Path | None = None

@dataclass(frozen=True)
class IndexProjectResult:
    graph: dict
    repository_root: Path
    output_path: Path
```

```python
index_project(request) -> IndexProjectResult
```

### 5.2 AnalyzeChange

```python
@dataclass(frozen=True)
class AnalyzeChangeRequest:
    profile: str | Path
    graph: str | Path
    output: str | Path
    approved_rules: str | Path | None = None
    files: str | Path | None = None
    base: str | None = None
    head: str = "HEAD"
    change_id: str | None = None
    max_depth: int = 3
    repository_root: str | Path | None = None
    markdown_output: str | Path | None = None

@dataclass(frozen=True)
class AnalyzeChangeResult:
    analysis: dict
    changed_files: tuple[str, ...]
    repository_root: Path
    output_path: Path
    markdown_path: Path | None
```

Git changed-file 조회는 execution dependency로 분리한다.

```python
analyze_project_change(
    request,
    git_diff_reader=git_changed_files,
)
```

CLI wrapper는 현재 `review_system.cli.git_changed_files` symbol을 명시적으로 전달해 기존 patch seam과 후속 port extraction 경계를 보존한다.

## 6. 입력과 경로 규칙

- profile, config, graph, rule, files, output path의 상대경로 의미는 기존 CLI와 동일하게 유지한다.
- explicit repository root는 resolve한다.
- repository root가 없으면 profile의 repository-root 해석을 사용한다.
- `files` 입력은 현재 작업 디렉터리 기준 `Path`로 읽는다. repository root에 임의 결합하지 않는다.
- direct API에서 `files`와 `base`가 모두 있거나 모두 없으면 fail-closed한다. CLI에서는 argparse mutually-exclusive group이 같은 계약을 선행 보장한다.
- Markdown output이 없으면 Markdown file을 만들지 않는다.

## 7. Failure Contract

Application use case는 exit code를 알지 못한다.

- invalid profile/config/graph/rule은 exception으로 종료한다.
- invalid graph 또는 missing approved-rules 상태에서는 output impact를 작성하지 않는다.
- changed-file source가 유효하지 않으면 analysis를 실행하지 않는다.
- output write 중 오류의 rollback semantics는 기존과 동일하며 이번 Stage에서 개선하지 않는다.
- CLI만 `_error()`를 통해 stderr와 exit code `2`를 생성한다.

## 8. 설계 리뷰

### DR-1 — 두 use case를 한 거대 module에 결합

**결정:** command별 module을 분리한다. 공통 profile/root 해석만 private helper로 공유한다.

### DR-2 — 기존 CLI helper를 application에서 import

**결정:** application은 CLI에 의존하지 않는다. `_project_context.py`에 독립적인 해석 함수를 둔다.

### DR-3 — Domain 함수 이름 충돌

**발견:** 기존 domain 함수가 `analyze_change`라는 이름을 사용한다.

**결정:** application entrypoint는 `analyze_project_change`로 명명해 domain analyzer와 구분한다.

### DR-4 — Git diff를 고정 import

**위험:** Stage 1A의 state-capture seam처럼 기존 test seam 또는 후속 integration port가 끊길 수 있다.

**결정:** `git_diff_reader`를 명시적 execution dependency로 전달한다.

### DR-5 — Direct API 입력을 CLI보다 느슨하게 허용

**결정:** `files`/`base`는 exactly-one을 요구한다. CLI argparse 계약과 동일한 fail-closed 의미다.

### DR-6 — 리팩터링과 output atomicity 개선 혼합

**결정:** 현재 write 순서와 partial-write 가능성을 보존한다. transaction 개선은 별도 Stage로 보류한다.

### DR-7 — `compare-changes`까지 동시 추출

**결정:** Stage 1B 범위에서 제외한다. 한 PR에서 두 연관 use case만 이동해 회귀 원인 격리를 유지한다.

## 9. 테스트 계획

### Direct application

1. IndexProject graph·stats·artifact 계약
2. AnalyzeChange files-source JSON·Markdown·impact 계약
3. AnalyzeChange base/head와 injected Git diff reader 전달
4. invalid graph fail-closed 및 output 미생성
5. missing approved-rules fail-closed
6. files/base exactly-one validation
7. request dataclass 불변성

### CLI adapter

8. `index-project` argument mapping과 delegation
9. `analyze-change` argument mapping과 dependency 전달
10. 기존 end-to-end `test_index_and_analyze_change_end_to_end` 무수정 통과

### Full verification

- Python 3.11 / 3.13 / 3.14 unittest matrix
- package asset synchronization
- CLI version smoke
- four profile validations
- finding validation
- wheel build
- stacked-base 대비 changed-file 범위 검증

## 10. Rollback

Stage 1B commit을 revert하면 두 command의 inline orchestration으로 복귀한다. schema, migration, artifact format, external state 변경이 없으므로 data rollback은 필요하지 않다.

## 11. Exit Criteria

- `cmd_index_project`와 `cmd_analyze_change`가 thin adapter가 된다.
- 두 use case가 argparse 없이 직접 호출 가능하다.
- 기존 CLI·graph·impact·rule·Markdown·failure behavior가 유지된다.
- direct tests와 기존 end-to-end tests가 통과한다.
- dependency·version·schema·workflow 변경이 없다.
