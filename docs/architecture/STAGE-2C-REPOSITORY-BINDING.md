# PIE Stage 2C — Repository Binding Extraction

기준일: 2026-07-24  
선행 기준선: PR #8 HEAD `d55dcbc11c783310f1568e858a6aa7aa45585025`  
작업 브랜치: `agent/stage-2c-repository-binding`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

PR 입력, 명시적 `--repo`, 현재 작업 저장소 사이의 일치 여부를 결정하는 책임을 PR collector에서 분리한다.

```text
PullRequestTarget + optional repository + current repository
→ github.binding.resolve_repository_binding
→ RepositoryBinding
→ existing collector
```

## 2. 범위

### 생성

```text
src/review_system/github/binding.py
tests/test_github_binding.py
```

### 수정

```text
src/review_system/github/__init__.py
src/review_system/github_connector.py
docs/architecture/README.md
```

### 비목표

- 인증 상태 판단 변경
- GitHub API·PR view·diff 호출 변경
- pagination·discussion 수집 분리
- source JSON·hash·warning 정책 변경
- local HEAD·dirty-worktree 검증 변경
- CLI option·schema·dependency·version 변경
- PR collector 전체 이동

## 3. 보호 계약

- 명시적 repository가 있으면 기존 형식으로 정규화한다.
- PR URL의 repository와 `--repo`가 다르면 기존 오류 문장을 유지한다.
- PR URL hostname과 명시적 repository hostname이 다르면 기존 오류 문장을 유지한다.
- PR URL에 repository가 있으면 이를 사용한다.
- 숫자 PR만 주어진 경우 `GitHubCLI.current_repository()`를 사용한다.
- 현재 repository를 결정하지 못하면 기존 fail-closed 오류를 유지한다.
- public GitHub와 Enterprise의 `gh --repo` argument를 동일하게 생성한다.
- 인증 확인은 binding 완료 후 기존 collector에서 수행한다.
- collector의 command argument와 source artifact는 변하지 않는다.

## 4. 설계

```python
@dataclass(frozen=True)
class RepositoryBinding:
    hostname: str
    name_with_owner: str
    gh_repo_argument: str


def resolve_repository_binding(
    cli: GitHubCLI,
    target: PullRequestTarget,
    *,
    cwd: str | Path,
    repository: str | None = None,
) -> RepositoryBinding: ...
```

`binding.py`는 repository 선택·정규화·일치 검증만 소유한다. 인증, network collection, artifact assembly는 collector에 남긴다.

## 5. 설계 리뷰

### DR-1 — 인증 확인까지 binding에 포함

**결정:** 제외. 인증은 repository identity가 아니라 원격 접근 준비 상태다.

### DR-2 — local HEAD·dirty-worktree 검증 통합

**결정:** 제외. 해당 검증은 application `AnalyzePullRequest` 실행 경계에 남긴다.

### DR-3 — collector 전체 이동

**결정:** 금지. 이번 단계는 repository binding만 분리한다.

### DR-4 — hostname·repository 비교를 대소문자 구분으로 강화

**결정:** 금지. 기존 case-insensitive repository 비교와 hostname 동작을 그대로 유지한다.

### DR-5 — legacy private helper 제거

**결정:** collector의 `_repo_argument` 사용은 binding 결과로 대체한다. `github.target.repository_argument` public export는 유지한다.

## 6. 검증 계획

1. URL target + matching explicit repository
2. URL repository mismatch 거부
3. URL hostname mismatch 거부
4. URL target에서 repository 자동 선택
5. 숫자 target에서 current repository 선택
6. current repository 부재 시 fail-closed
7. GitHub Enterprise repo argument
8. frozen `RepositoryBinding`
9. collector command·source JSON·hash 회귀
10. Python 3.11·3.13·3.14 전체 matrix
11. package asset sync, CLI/profile/finding smoke, wheel build

## 7. Rollback

Stage 2C 변경을 revert하면 repository 선택과 일치 검증이 다시 `github_connector.py` 내부로 돌아간다. schema, artifact 또는 저장 데이터 migration은 없다.

## 8. Exit Criteria

- repository binding 책임이 별도 모듈에 존재한다.
- collector는 resolved binding만 사용한다.
- 기존 오류·command·artifact 계약이 동일하다.
- 신규 characterisation test와 전체 회귀가 통과한다.
- 최종 diff에 임시 적용 script·workflow가 남지 않는다.
