# PIE Stage 2D — PR Collector Boundary Extraction

기준일: 2026-07-24  
선행 기준선: PR #9 HEAD `1501296644cc03d3af5590d00224023109983a0e`  
작업 브랜치: `agent/stage-2d-collector-boundaries`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

`github_connector.py`에 남아 있는 PR 수집 책임을 다음 네 경계로 분리한다.

```text
pagination.py  → REST paginated list collection
 discussion.py → issue comments, reviews, inline review comments
 source.py     → source artifact assembly, hash, validation
 collector.py  → collection orchestration
```

`github_connector.py`는 기존 import 경로를 보존하는 compatibility facade와 `doctor()`만 유지한다.

## 2. 범위

### 생성

```text
src/review_system/github/pagination.py
src/review_system/github/discussion.py
src/review_system/github/source.py
src/review_system/github/collector.py
tests/test_github_collection_boundaries.py
```

### 수정

```text
src/review_system/github/__init__.py
src/review_system/github_connector.py
docs/architecture/README.md
```

### 비목표

- GitHub CLI 실행기·재시도 정책 변경
- target parsing·repository binding 변경
- API endpoint·호출 순서 변경
- artifact schema·필드명·hash 규칙 변경
- diff failure·discussion partial failure 정책 변경
- local HEAD·dirty-worktree 검증 변경
- CLI option·dependency·version 변경
- collector를 application layer로 이동

## 3. 보호 계약

- `gh pr view` JSON 필드 집합을 유지한다.
- changed-file REST pagination은 GraphQL 100-file 제한을 보완한다.
- declared changed-file count가 수집 결과와 다르면 fail-closed한다.
- REST pagination 실패 시 기존 fallback·warning·fatal 조건을 유지한다.
- diff 수집 실패는 metadata 실패가 아니라 warning으로 남긴다.
- PR number와 response repository 검증 순서를 유지한다.
- discussion 세 endpoint와 partial warning 문장을 유지한다.
- source schema `1.0`, field shape, `retrieved_at`, canonical SHA-256을 유지한다.
- `refresh_source_hash`, `validate_pull_request_source`, `collect_pull_request`의 기존 import 경로를 유지한다.
- `doctor()` 결과를 유지한다.

## 4. 목표 구조

### Pagination

```python
def flatten_paginated_arrays(text: str, *, label: str) -> list[dict[str, Any]]: ...

def collect_paginated_list(
    cli: GitHubCLI,
    endpoint: str,
    *,
    hostname: str,
    cwd: str | Path,
) -> tuple[list[dict[str, Any]] | None, str | None]: ...
```

### Discussion

```python
@dataclass(frozen=True)
class DiscussionEvidence:
    issue_comments: tuple[dict[str, Any], ...]
    reviews: tuple[dict[str, Any], ...]
    inline_review_comments: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    warnings: tuple[str, ...]
```

### Source

```python
def assemble_pull_request_source(...) -> dict[str, Any]: ...
def refresh_source_hash(source: dict[str, Any]) -> str: ...
def validate_pull_request_source(source: dict[str, Any]) -> list[str]: ...
```

### Collector

```python
def collect_pull_request(...) -> tuple[dict[str, Any], str | None]: ...
```

Collector는 명령 순서와 failure policy를 소유하지만 JSON compaction, pagination parsing, artifact layout 구현은 위임한다.

## 5. 설계 리뷰

### DR-1 — 모든 GitHub 기능을 하나의 client class로 통합

**결정:** 제외. 현재는 작은 함수 경계가 기존 dependency와 test seam을 가장 잘 보존한다.

### DR-2 — discussion failure를 예외로 강화

**결정:** 금지. 기존 partial evidence + warning 정책을 유지한다.

### DR-3 — diff를 별도 module로 분리

**결정:** 보류. diff 수집은 짧고 collector command ordering과 밀접하다.

### DR-4 — source schema를 dataclass로 교체

**결정:** 금지. 현재 공개 artifact는 JSON dict이며 schema 변경 없이 조립 책임만 이동한다.

### DR-5 — private helper를 compatibility export

**결정:** 불필요. 공개 계약만 facade에서 유지하고 신규 하위 module helper는 직접 테스트한다.

### DR-6 — endpoint 호출 병렬화

**결정:** 금지. 호출 순서·rate limit·failure evidence가 달라질 수 있다.

## 6. 구현 순서

1. pagination characterisation 구현
2. discussion compaction·partial failure 구현
3. source assembly·hash·validation 이동
4. collector orchestration 이동
5. legacy facade 교체
6. focused test 추가
7. existing connector tests 전체 재실행
8. implementation review
9. Python 3.11·3.13·3.14 exact-head CI

## 7. 검증 항목

- flat JSON array와 slurped page arrays
- invalid JSON·API failure 반환 계약
- discussion complete·partial·disabled 상태
- actor·comment·review compaction
- source field equality와 deterministic hash
- hash refresh·tamper validation
- >100 changed files pagination
- declared count mismatch fail-closed
- diff warning
- response PR/repository mismatch
- legacy imports
- full regression, CLI/profile/finding smoke, wheel build

## 8. Rollback

Stage 2D 변경을 revert하면 모든 구현이 다시 `github_connector.py`로 돌아간다. artifact 또는 storage migration은 없다.

## 9. Exit Criteria

- 네 책임이 별도 module에 존재한다.
- `github_connector.py`는 compatibility facade가 된다.
- 기존 endpoint, command ordering, warnings, artifact와 hash가 동일하다.
- focused test와 전체 matrix가 통과한다.
- 최종 diff에 임시 workflow·script·trigger가 없다.
