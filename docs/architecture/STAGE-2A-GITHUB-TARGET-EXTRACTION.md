# PIE Stage 2A — GitHub Target Parsing Extraction

기준일: 2026-07-24  
선행 기준선: PR #6 HEAD `3eb4991d59e3ed209392f48fdc30f1fa91365e3a`  
작업 브랜치: `agent/stage-2a-github-target-extraction`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

Stage 1에서 계획한 다섯 application boundary가 모두 분리됐으므로 해당 계층을 동결한다. Stage 2A는 `github_connector.py`의 첫 번째 독립 책임인 GitHub PR target·repository 입력 해석을 내부 모듈로 추출한다.

```text
raw PR / repository input
→ github.target
→ validated PullRequestTarget / normalized repository
→ existing collector
```

## 2. 범위

### 생성

```text
src/review_system/github/__init__.py
src/review_system/github/target.py
tests/test_github_target.py
```

### 수정

```text
src/review_system/github_connector.py
docs/architecture/README.md
```

### 비목표

- `GitHubCLI` command runner·retry 분리
- repository binding 정책 분리
- PR collector·pagination·discussion 분리
- source document·hash 변경
- CLI option·output·exit code 변경
- public schema·dependency·version 변경
- 새로운 URL 형식 또는 입력 정책 추가

## 3. 보호 계약

- `review_system.github_connector.PullRequestTarget` import가 계속 동작한다.
- `parse_pr_target()`와 `normalize_repository()`의 예외·반환값을 그대로 유지한다.
- positive PR number, HTTPS PR URL, GitHub Enterprise hostname을 동일하게 처리한다.
- repository 입력의 `OWNER/REPO`, `HOST/OWNER/REPO`, HTTPS URL 형식을 그대로 유지한다.
- `collect_pull_request()`가 생성하는 command argument와 source JSON은 변하지 않는다.
- shell 실행, retry, pagination, hash 계산에는 손대지 않는다.

## 4. 설계

새 모듈은 다음만 소유한다.

```python
@dataclass(frozen=True)
class PullRequestTarget:
    raw: str
    number: int
    hostname: str
    repository: str | None
    gh_target: str


def parse_pr_target(value: str) -> PullRequestTarget: ...
def normalize_repository(value: str, *, default_hostname: str = "github.com") -> tuple[str, str]: ...
def repository_argument(hostname: str, repository: str) -> str: ...
```

`github_connector.py`는 위 객체를 import하고 기존 이름을 재노출한다. `_repo_argument`는 compatibility alias로 유지해 collector diff를 최소화한다.

## 5. 설계 리뷰

### DR-1 — `github_connector.py`를 한 번에 분해

**결정:** 금지. 입력 파서만 이동한다. command runner와 collector는 별도 Stage로 분리한다.

### DR-2 — URL 검증 강화

**결정:** 이번 단계에서 하지 않는다. query, trailing path 등 기존 수용·거부 동작을 characterisation test로 고정한다.

### DR-3 — 기존 import 제거

**결정:** 금지. 기존 public import path는 compatibility export로 유지한다.

### DR-4 — 새 dependency 도입

**결정:** 금지. 표준 라이브러리만 사용한다.

### DR-5 — private `_repo_argument` 제거

**결정:** collector 변경을 최소화하기 위해 alias로 유지한다.

## 6. 테스트 계획

1. 숫자 PR target의 기존 반환값
2. GitHub·Enterprise HTTPS PR URL
3. 기존 unsafe·ambiguous target 거부
4. repository 세 입력 형식 정규화
5. `.git`, whitespace, default hostname 처리
6. 기존 module과 새 module의 export identity
7. collector metadata·diff·discussion·hash 회귀
8. Python 3.11·3.13·3.14 전체 matrix
9. CLI/profile/finding smoke와 wheel build

## 7. Rollback

Stage 2A commit을 revert하면 target parsing이 다시 `github_connector.py` 내부로 돌아간다. schema, artifact, persisted data migration은 없다.

## 8. Exit Criteria

- target parsing 책임이 별도 모듈로 이동한다.
- 기존 import와 collector 결과가 동일하다.
- 신규 characterisation test와 기존 전체 회귀가 통과한다.
- 최종 diff에 임시 적용 workflow·script가 남지 않는다.
