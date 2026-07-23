# PIE Stage 2A — GitHub Target Parsing Extraction

기준일: 2026-07-24  
선행 기준선: PR #6 HEAD `3eb4991d59e3ed209392f48fdc30f1fa91365e3a`  
작업 브랜치: `agent/stage-2a-github-target-extraction`  
상태: `IMPLEMENTATION_REVIEW_PASS / FINAL_VERIFICATION_PENDING`

## 1. 목적

Stage 1에서 계획한 다섯 application boundary가 모두 분리됐으므로 해당 계층을 동결한다. Stage 2A는 `github_connector.py`의 첫 번째 독립 책임인 GitHub PR target·repository 입력 해석을 내부 모듈로 추출한다.

```text
raw PR / repository input
→ github.target
→ validated PullRequestTarget / normalized repository
→ existing collector
```

## 2. 최종 범위

### 생성

```text
src/review_system/github/__init__.py
src/review_system/github/target.py
tests/test_github_target.py
docs/architecture/STAGE-2A-GITHUB-TARGET-EXTRACTION.md
```

### 수정

```text
src/review_system/github_connector.py
docs/architecture/README.md
```

### 변경하지 않음

- `GitHubCLI` command runner·retry
- repository binding 정책
- PR collector·pagination·discussion
- source document·hash
- CLI option·output·exit code
- public schema·dependency·version
- URL 수용·거부 정책

## 3. 보호 계약

- `review_system.github_connector.PullRequestTarget` import가 계속 동작한다.
- `parse_pr_target()`와 `normalize_repository()`의 예외·반환값을 그대로 유지한다.
- positive PR number, HTTPS PR URL, GitHub Enterprise hostname을 동일하게 처리한다.
- repository 입력의 `OWNER/REPO`, `HOST/OWNER/REPO`, HTTPS URL 형식을 그대로 유지한다.
- `collect_pull_request()`가 생성하는 command argument와 source JSON은 변하지 않는다.
- shell 실행, retry, pagination, hash 계산에는 손대지 않는다.

## 4. 구현

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

`github_connector.py`는 위 객체를 import하고 기존 이름을 재노출한다. `_repo_argument`는 compatibility alias로 유지한다.

## 5. 설계 리뷰

- connector 전체 분해를 금지하고 입력 파서만 이동했다.
- URL 검증 강화나 새 입력 형식을 추가하지 않았다.
- 기존 public import path를 compatibility export로 유지했다.
- 새 dependency를 추가하지 않았다.
- command runner와 collector는 후속 Stage로 분리했다.

## 6. 구현 리뷰

### IR-1 — 이동 후 정규식 상수 잔존

**발견:** 파서 함수는 이동됐지만 `_GITHUB_PR_RE`, `_REPOSITORY_RE`가 connector에 남아 중복 책임이 유지됐다.

**보완:** 두 상수를 제거하고 connector가 새 모듈의 파서만 사용하도록 재검증했다.

**상태:** CLOSED

### IR-2 — 기존 import 호환성

`PullRequestTarget`, `parse_pr_target`, `normalize_repository`가 `github_connector`에서 동일 객체로 재노출되는 characterisation test를 추가했다.

**상태:** CLOSED

### IR-3 — 범위 오염

원격 적용에 사용한 workflow와 script를 최종 diff에서 제거했다. 최종 변경은 6개 파일이다.

**상태:** CLOSED

## 7. 테스트

추가 검증:

1. 숫자 PR target 반환값
2. GitHub·Enterprise HTTPS PR URL
3. 기존 unsafe·ambiguous target 거부
4. repository 세 입력 형식 정규화
5. `.git`, whitespace, default hostname 처리
6. 기존 module과 새 module의 export identity
7. public·enterprise `gh --repo` argument
8. 기존 collector metadata·diff·discussion·hash 회귀

최종 PR matrix에서 Python 3.11·3.13·3.14, package asset sync, CLI/profile/finding smoke, wheel build를 검증한다.

## 8. Rollback

Stage 2A 변경을 revert하면 target parsing이 다시 `github_connector.py` 내부로 돌아간다. schema, artifact, persisted data migration은 없다.

## 9. Exit Criteria

- target parsing 책임이 별도 모듈로 이동한다.
- 기존 import와 collector 결과가 동일하다.
- 신규 characterisation test와 기존 전체 회귀가 통과한다.
- 최종 diff에 임시 적용 workflow·script가 남지 않는다.
