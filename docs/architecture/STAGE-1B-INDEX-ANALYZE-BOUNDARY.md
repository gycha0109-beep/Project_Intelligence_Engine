# PIE Stage 1B — IndexProject / AnalyzeChange Application Boundaries

기준일: 2026-07-23  
선행 기준선: PR #2 HEAD `57d22ac7673572e6ab33d2458d868663919f5133`  
작업 브랜치: `agent/stage-1b-index-analyze-boundary`  
Stacked PR: `#4`  
상태: `PASS`

## 1. 목적

Stage 1B는 `cmd_index_project`와 `cmd_analyze_change`에 남아 있던 application orchestration을 CLI adapter에서 분리한다.

```text
argparse Namespace
→ immutable Request
→ application use case
→ immutable Result
→ CLI summary / exit code
```

Stage 1A에서 확정한 원칙을 동일하게 적용했다.

- application layer는 argparse를 import하지 않는다.
- CLI는 argument mapping, dependency 전달, error-to-exit-code 변환, summary 출력만 담당한다.
- 기존 graph, impact, rule, Markdown, path와 failure 계약은 변경하지 않는다.

## 2. 최종 구조

```text
src/review_system/application/
├─ __init__.py
├─ _project_context.py
├─ analyze_pr.py
├─ index_project.py
└─ analyze_change.py
```

### 생성

```text
src/review_system/application/_project_context.py
src/review_system/application/index_project.py
src/review_system/application/analyze_change.py
tests/test_application_index_analyze.py
docs/architecture/STAGE-1B-INDEX-ANALYZE-BOUNDARY.md
```

### 수정

```text
src/review_system/application/__init__.py
src/review_system/cli.py
docs/architecture/README.md
```

### 변경하지 않음

- `compare-changes`
- `capture-state`
- graph builder와 impact analyzer 내부
- graph·rule·review schema
- CLI option·exit code·summary 의미
- output transaction과 rollback semantics
- package namespace·version·dependency
- preset·pack·Gate policy·CI workflow
- Evidence Ledger와 Run identity

## 3. 보호 계약

### 3.1 IndexProject

| 계약 | 유지 결과 |
|---|---|
| Profile | 기존 `validate_profile_file` 사용 |
| Root | explicit repository root 우선, 없으면 profile 기준 해석 |
| Config | 기존 `load_intelligence_config` 사용 |
| Graph | include/exclude, components, max size 전달 유지 |
| Artifact | 기존 graph JSON 구조와 output path 유지 |
| Error | application exception 전파, CLI stderr + exit `2` 유지 |
| Summary | files, edges, warnings, output 유지 |

### 3.2 AnalyzeChange

| 계약 | 유지 결과 |
|---|---|
| Graph | object 여부와 `validate_project_graph` 검증 유지 |
| Rules | 지정된 approved-rules 파일 부재 시 fail-closed 유지 |
| Input | `--files` 또는 `--base` 상호배타 계약 유지 |
| Git diff | repository root, base, head 전달 유지 |
| Impact | packs, approved rules, max depth, revisions 유지 |
| JSON | 기존 impact JSON 구조와 output path 유지 |
| Markdown | 요청 시 parent 생성 후 기존 renderer로 저장 |
| Summary | direct, impacted, packs, output 유지 |
| Error | application exception 전파, CLI exit `2` 유지 |

## 4. Application Contracts

### 4.1 IndexProject

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

### 4.2 AnalyzeChange

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

Git changed-file 조회는 execution dependency다.

```python
analyze_project_change(
    request,
    git_diff_reader=git_changed_files,
)
```

CLI wrapper가 현재 `review_system.cli.git_changed_files` symbol을 명시적으로 전달한다.

## 5. 입력과 경로 규칙

- profile, config, graph, rule, files, output 상대경로 의미를 기존 CLI와 동일하게 유지했다.
- explicit repository root만 resolve한다.
- repository root가 없으면 profile의 repository-root 해석을 사용한다.
- `files` 입력은 현재 작업 디렉터리 기준으로 읽는다. repository root에 임의 결합하지 않는다.
- direct API는 `files`와 `base` 중 정확히 하나를 요구한다.
- CLI에서는 기존 argparse mutually-exclusive group이 같은 계약을 선행 보장한다.
- Markdown output이 없거나 빈 값이면 Markdown file을 만들지 않는다.

## 6. Failure Contract

Application use case는 exit code를 알지 못한다.

- invalid profile/config/graph/rule은 exception으로 종료한다.
- invalid graph 또는 missing approved-rules 상태에서는 impact output을 작성하지 않는다.
- changed-file source가 유효하지 않으면 analysis를 실행하지 않는다.
- output write 중 오류의 partial-write/rollback 의미는 기존과 동일하다.
- CLI만 `_error()`를 통해 stderr와 exit code `2`를 생성한다.

## 7. 설계 리뷰

### DR-1 — 두 use case를 한 module에 결합

**결정:** command별 module로 분리하고 profile/root 해석만 private helper로 공유했다.

### DR-2 — CLI helper 역의존

**결정:** application은 CLI를 import하지 않는다. `_project_context.py`가 독립적으로 profile과 root를 해석한다.

### DR-3 — Domain 함수 이름 충돌

기존 domain 함수 이름이 `analyze_change`다.

**결정:** application entrypoint를 `analyze_project_change`로 명명했다.

### DR-4 — Git diff 고정 참조

Stage 1A의 state-capture seam과 같은 hidden coupling 위험이 있었다.

**결정:** `git_diff_reader`를 명시적 execution dependency로 전달한다.

### DR-5 — Direct API 입력 완전성

**결정:** `files`/`base` exactly-one을 fail-closed로 검증한다.

### DR-6 — Output 개선 혼합

**결정:** output atomicity와 collision policy는 별도 기능 Stage로 보류했다.

### DR-7 — `compare-changes` 동시 추출

**결정:** 회귀 원인 격리를 위해 Stage 1B에서 제외했다.

## 8. 구현 리뷰와 보완

### IR-1 — 기존 Git diff patch seam

**검토**

단순 이동 후 application module의 default import만 사용하면 CLI module patch가 적용되지 않을 수 있다.

**조치**

- `git_diff_reader` parameter 추가
- CLI wrapper가 `git_changed_files`를 명시적으로 전달
- adapter test에서 callable 전달 확인

**상태:** CLOSED

### IR-2 — Profile/root 의미 drift

**검토**

공통 helper가 기존 `_profile_and_root`와 다른 truthiness 또는 resolve 규칙을 사용하면 repository scope가 변할 수 있다.

**조치**

- explicit root truthiness와 `Path.resolve()` 유지
- root 미지정 시 `repository_root_for` 유지
- direct test에서 resolved root 확인

**상태:** CLOSED

### IR-3 — Changed-file source ambiguity

**검토**

Direct caller는 argparse 보호를 거치지 않으므로 files/base 모두 지정하거나 모두 누락할 수 있다.

**조치**

exactly-one validation과 양성·음성 회귀 테스트를 추가했다.

**상태:** CLOSED

### IR-4 — Output/Markdown behavior drift

**검토**

상대 output path, Markdown parent 생성, Markdown 미요청 시 파일 부재가 변하지 않아야 한다.

**조치**

기존 `Path`, `dump_json`, `mkdir(parents=True)`, renderer 호출 순서를 유지하고 direct test로 고정했다.

**상태:** CLOSED

### IR-5 — CLI summary와 exit behavior

**검토**

리팩터링 중 result object를 사용하면서 출력 필드나 오류 변환이 달라질 수 있다.

**조치**

- 기존 summary 필드와 `args.output` 표기 유지
- application exception은 CLI `_error()`에서만 exit `2`로 변환
- 두 command의 request mapping/delegation test 추가

**상태:** CLOSED

### IR-6 — 임시 실행 자산 잔존

**검토**

clone 불가 환경에서 사용한 일회성 refactor script/workflow가 제품 diff에 남을 수 있었다.

**조치**

최종 stacked diff에서 모두 제거했다. 기존 CI workflow는 변경하지 않았다.

**상태:** CLOSED

## 9. 테스트

추가된 집중 테스트 9개:

1. IndexProject graph·artifact 계약
2. AnalyzeChange files-source JSON·Markdown·impact 계약
3. base/head와 injected Git diff reader 전달
4. invalid graph fail-closed 및 output 미생성
5. missing approved-rules fail-closed
6. files/base exactly-one validation
7. request dataclass 불변성
8. index-project CLI mapping/delegation
9. analyze-change CLI mapping/dependency 전달

기존 `test_index_and_analyze_change_end_to_end`는 수정 없이 통과했다.

## 10. 검증 결과

Implementation-review HEAD: `8a98f24f25eade81a1be9f6ca66e30bdf70b6e15`  
GitHub Actions run: `29991198951`

| 검증 | Python 3.11 | Python 3.13 | Python 3.14 |
|---|---:|---:|---:|
| Package install | PASS | PASS | PASS |
| Package asset sync | PASS | PASS | PASS |
| 112 unit tests | PASS | PASS | PASS |
| `urs version` | PASS | PASS | PASS |
| 4 preset profile validation | PASS | PASS | PASS |
| Finding validation | PASS | PASS | PASS |
| Wheel build | PASS | PASS | PASS |

최종 문서 commit을 포함한 exact HEAD는 동일 파일 범위를 사용하는 별도 PR-open matrix로 다시 확인한다. 해당 검증은 PR 설명에 SHA와 run ID를 기록한다.

## 11. 최종 변경 범위

PR #2 HEAD 대비 정확히 8개 파일이다.

```text
docs/architecture/README.md
docs/architecture/STAGE-1B-INDEX-ANALYZE-BOUNDARY.md
src/review_system/application/__init__.py
src/review_system/application/_project_context.py
src/review_system/application/analyze_change.py
src/review_system/application/index_project.py
src/review_system/cli.py
tests/test_application_index_analyze.py
```

다음은 변경하지 않았다.

- public schema
- package version과 dependency
- preset·pack·Gate policy
- GitHub intake와 source hash
- final workflow
- artifact format

## 12. Rollback

Stage 1B 변경을 revert하면 두 command의 inline orchestration으로 복귀한다. schema, migration, artifact format 또는 external state 변경이 없어 data rollback은 필요하지 않다.

## 13. 판정

```text
Detailed Design: PASS
Design Review: PASS
Implementation: PASS
Implementation Review: PASS
Regression Verification: PASS
Compatibility Decision: PRESERVED
Stage 1B Gate: PASS
```

## 14. 다음 작업

Stage 1C에서 다음 application boundary를 추출한다.

```text
ApproveRule
CalculateGate
```

같은 절차로 immutable request/result, thin CLI adapter, direct tests, failure compatibility를 적용한다.
