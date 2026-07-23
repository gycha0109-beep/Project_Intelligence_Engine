# PIE Stage 2B — GitHub CLI Runner Extraction

기준일: 2026-07-24  
선행 기준선: PR #7 HEAD `03d4b01fecff4ab34c1291d172147829328d3ce0`  
작업 브랜치: `agent/stage-2b-github-runner-extraction`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

`github_connector.py`에 결합된 GitHub CLI 프로세스 실행과 재시도 정책을 독립 모듈로 추출한다.

```text
collector / doctor
→ github.runner.GitHubCLI
→ argument-vector subprocess execution
→ bounded retry
→ CommandResult or GitHubCLIError
```

## 2. 범위

### 생성

```text
src/review_system/github/runner.py
tests/test_github_runner.py
```

### 수정

```text
src/review_system/github/__init__.py
src/review_system/github_connector.py
tests/test_github_connector.py
docs/architecture/README.md
```

### 비목표

- PR collector·pagination·discussion 분리
- repository binding 정책 변경
- source JSON·diff·hash 변경
- retry 횟수·대기 시간·대상 marker 변경
- 인증·current repository 결과 형식 변경
- CLI option·schema·dependency·version 변경

## 3. 보호 계약

- `review_system.github_connector.GitHubCLI`, `GitHubCLIError`, `CommandResult` import가 계속 동작한다.
- subprocess는 shell 없이 argument vector로 실행한다.
- `GH_PAGER=cat`, `PAGER=cat`, `NO_COLOR=1` 환경을 유지한다.
- 기본 timeout 120초와 호출별 override 의미를 유지한다.
- retry는 최대 3회이며 rate limit, HTTP 429·502·503·504에만 적용한다.
- backoff는 기존처럼 1초, 2초다.
- `check=False`는 실패 결과를 반환하고 `check=True`는 기존 오류 문장을 유지한다.
- timeout과 OS 실행 오류는 기존 `GitHubCLIError`로 변환한다.
- `version()`, `auth_status()`, `current_repository()` 반환 구조를 유지한다.

## 4. 설계

새 모듈이 소유한다.

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

`github_connector.py`는 세 객체를 import해 기존 이름으로 재노출한다. collector는 같은 객체를 사용하므로 command argument와 source artifact 계약은 변하지 않는다.

## 5. 설계 리뷰

### DR-1 — runner와 collector를 한 번에 분리

**결정:** 금지. 프로세스 실행 책임만 이동한다.

### DR-2 — retry policy를 configurable object로 일반화

**결정:** 보류. 현재 값과 오류 문장을 그대로 옮겨 회귀 위험을 최소화한다.

### DR-3 — shell wrapper 또는 문자열 command 도입

**결정:** 금지. 기존 argument-vector 실행을 유지한다.

### DR-4 — 기존 import 제거

**결정:** 금지. `github_connector`는 compatibility export를 유지한다.

### DR-5 — 기존 테스트의 내부 monkeypatch 경로 유지

**결정:** canonical patch 경로를 `review_system.github.runner`로 이동한다. 이는 public API가 아니며, legacy class import와 실행 동작은 identity test로 보호한다.

## 6. 검증 계획

1. legacy export와 새 모듈 객체 identity
2. argument vector·cwd·환경·timeout 전달
3. shell 미사용
4. transient 502 후 성공과 1·2초 backoff
5. 영구 rate-limit 3회 후 actionable 오류
6. non-retryable 오류 1회 종료
7. `check=False` 실패 반환
8. timeout·OSError 변환
9. version/auth/current repository 반환값
10. 기존 collector metadata·diff·discussion·hash 회귀
11. Python 3.11·3.13·3.14 전체 matrix
12. package asset sync, CLI/profile/finding smoke, wheel build

## 7. Rollback

Stage 2B 변경을 revert하면 runner 구현이 다시 `github_connector.py` 내부로 돌아간다. schema, artifact 또는 저장 데이터 migration은 없다.

## 8. Exit Criteria

- command runner와 retry 정책이 별도 모듈에 존재한다.
- legacy import와 collector 동작이 동일하다.
- characterisation tests와 전체 회귀가 통과한다.
- 최종 diff에 임시 적용 script·workflow·diagnostic 파일이 남지 않는다.
