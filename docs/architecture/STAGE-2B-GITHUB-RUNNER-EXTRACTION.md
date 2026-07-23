# PIE Stage 2B — GitHub CLI Runner Extraction

기준일: 2026-07-24  
선행 기준선: PR #7 HEAD `03d4b01fecff4ab34c1291d172147829328d3ce0`  
작업 브랜치: `agent/stage-2b-github-runner-extraction`  
상태: `IMPLEMENTATION_REVIEW_PASS / FINAL_VERIFICATION_PENDING`

## 1. 목적

`github_connector.py`에 결합된 GitHub CLI 프로세스 실행과 재시도 정책을 독립 모듈로 추출한다.

```text
collector / doctor
→ github.runner.GitHubCLI
→ argument-vector subprocess execution
→ bounded retry
→ CommandResult or GitHubCLIError
```

## 2. 최종 범위

### 생성

```text
src/review_system/github/runner.py
tests/test_github_runner.py
docs/architecture/STAGE-2B-GITHUB-RUNNER-EXTRACTION.md
```

### 수정

```text
src/review_system/github/__init__.py
src/review_system/github_connector.py
tests/test_github_connector.py
docs/architecture/README.md
```

### 변경하지 않음

- PR collector·pagination·discussion
- repository binding 정책
- source JSON·diff·hash
- retry 횟수·대기 시간·대상 marker
- 인증·current repository 결과 형식
- CLI option·schema·dependency·version·최종 workflow

## 3. 보호 계약

- `review_system.github_connector.GitHubCLI`, `GitHubCLIError`, `CommandResult` import가 계속 동작한다.
- subprocess는 shell 없이 argument vector로 실행한다.
- `GH_PAGER=cat`, `PAGER=cat`, `NO_COLOR=1` 환경을 유지한다.
- 기본 timeout 120초와 호출별 override 의미를 유지한다.
- retry는 최대 3회이며 rate limit, HTTP 429·502·503·504에만 적용한다.
- backoff는 1초, 2초다.
- `check=False`는 실패 결과를 반환하고 `check=True`는 기존 오류 문장을 유지한다.
- timeout과 OS 실행 오류는 `GitHubCLIError`로 변환한다.
- `version()`, `auth_status()`, `current_repository()` 반환 구조를 유지한다.

## 4. 구현

새 모듈이 다음 책임을 소유한다.

```python
class GitHubCLIError(RuntimeError): ...

@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

class GitHubCLI:
    def run(...): ...
    def version(...): ...
    def auth_status(...): ...
    def current_repository(...): ...
```

`github_connector.py`는 세 객체를 import해 기존 이름으로 재노출한다. collector와 doctor는 기존 호출 구조를 변경하지 않고 새 runner 객체를 사용한다.

## 5. 설계 리뷰

### DR-1 — runner와 collector 동시 분리

**결정:** 금지. 프로세스 실행 책임만 이동했다.

### DR-2 — retry policy 일반화

**결정:** 보류. 현재 상수와 오류 문장을 그대로 보존했다.

### DR-3 — shell wrapper 또는 문자열 command

**결정:** 금지. argument-vector 실행을 유지했다.

### DR-4 — 기존 import 제거

**결정:** 금지. `github_connector` compatibility export를 유지했다.

### DR-5 — 내부 monkeypatch 경로

**결정:** canonical 경로를 `review_system.github.runner`로 이동했다. legacy class identity와 실행 동작은 별도 테스트로 보호한다.

## 6. 구현 리뷰

### IR-1 — 실행 동작 이동 완전성

`GitHubCLIError`, `CommandResult`, `GitHubCLI` 본문이 connector에서 제거되고 runner 모듈 한 곳에만 존재함을 확인했다.

**상태:** CLOSED

### IR-2 — retry 의미 변화

retry marker, 최대 3회, 1·2초 backoff, rate-limit 전용 actionable 오류가 기존과 동일함을 확인했다.

**상태:** CLOSED

### IR-3 — collector 영향

collector의 command argument, 인증 확인, pagination, discussion 수집, source hash 코드는 변경되지 않았다.

**상태:** CLOSED

### IR-4 — compatibility export

기존 module과 새 module이 동일 class 객체를 노출하도록 identity test를 추가했다.

**상태:** CLOSED

### IR-5 — 임시 실행 자산

원격 적용에 사용한 script와 workflow는 최종 diff에서 제거했다.

**상태:** CLOSED

## 7. 검증

집중 테스트는 다음을 고정한다.

1. legacy export identity
2. argument vector·cwd·환경·timeout
3. shell 미사용
4. transient 502·503 후 성공
5. 1·2초 backoff
6. 영구 rate-limit 3회 후 actionable 오류
7. non-retryable 단일 실행
8. `check=False` 실패 반환
9. timeout·OSError 변환
10. version/auth/current repository 결과
11. missing executable 동작
12. 기존 collector 회귀

Python 3.11 적용 검증에서 전체 테스트가 통과했다. 최종 PR HEAD에서 Python 3.11·3.13·3.14, package asset sync, CLI/profile/finding smoke, wheel build를 다시 검증한다.

## 8. Rollback

Stage 2B 변경을 revert하면 runner 구현이 다시 `github_connector.py` 내부로 돌아간다. schema, artifact 또는 저장 데이터 migration은 없다.

## 9. Exit Criteria

- command runner와 retry 정책이 별도 모듈에 존재한다.
- legacy import와 collector 동작이 동일하다.
- characterisation tests와 전체 회귀가 통과한다.
- 최종 diff에 임시 script·workflow·diagnostic 파일이 남지 않는다.
