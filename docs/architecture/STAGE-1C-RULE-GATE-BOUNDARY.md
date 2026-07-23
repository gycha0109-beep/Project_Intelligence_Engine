# PIE Stage 1C — ApproveRule / CalculateGate Application Boundaries

기준일: 2026-07-23  
선행 기준선: PR #4 HEAD `7252d60cd5c767663619bd9b9dc14c6082281d82`  
작업 브랜치: `agent/stage-1c-rule-gate-boundary`  
Stacked PR: `#6`  
상태: `IMPLEMENTATION_REVIEW_PASS / FINAL_VERIFICATION_PENDING`

## 1. 목적

Stage 1C는 규칙 승인과 Gate 계산 orchestration을 CLI에서 application 계층으로 분리한다.

```text
argparse Namespace
→ immutable Request
→ application use case
→ immutable Result
→ CLI 출력 / exit code
```

## 2. 최종 범위

### 생성

```text
src/review_system/application/approve_rule.py
src/review_system/application/calculate_gate.py
tests/test_application_rule_gate.py
docs/architecture/STAGE-1C-RULE-GATE-BOUNDARY.md
```

### 수정

```text
src/review_system/application/__init__.py
src/review_system/cli.py
src/review_system/intelligence_learning.py
docs/architecture/README.md
```

### 변경하지 않음

- `calculate-gate-dir`
- Gate 정책 구조와 우선순위
- rule discovery·evaluation
- Evidence Ledger 또는 Policy Registry
- CLI option
- package version과 dependency
- public schema·preset·pack·workflow

## 3. 보호 계약

### ApproveRule

- candidate와 approved rule 파일을 기존 validation으로 읽는다.
- 승인 주체, 시각, 근거를 기존 구조로 기록한다.
- candidate와 approved 파일을 `dump_yaml_pair_atomic`으로 함께 갱신한다.
- 실패 시 두 파일의 부분 갱신을 허용하지 않는다.
- 성공 summary와 exit code `0`을 유지한다.
- 입력·실행 오류는 stderr와 exit code `2`로 변환한다.

### CalculateGate

- Review Run validation을 먼저 수행한다.
- validation 오류를 기존 형식으로 출력하고 exit code `2`를 반환한다.
- policy 미지정 시 packaged default policy를 사용한다.
- `--trust-metrics` 의미를 유지한다.
- output 지정 시 기존 JSON을 기록한다.
- 계산 결과 전체를 stdout JSON으로 출력한다.
- `PASS`, `CONDITIONAL_PASS`는 exit code `0`, 나머지는 `3`을 유지한다.

## 4. Application 계약

```python
@dataclass(frozen=True)
class ApproveRuleRequest:
    candidates: str | Path
    approved: str | Path
    rule_id: str
    approved_by: str
    approved_at: str | None = None
    rationale: str | None = None

@dataclass(frozen=True)
class ApproveRuleResult:
    rule_id: str
    candidates_path: Path
    approved_path: Path
    candidates: dict
    approved: dict
```

```python
@dataclass(frozen=True)
class CalculateGateRequest:
    run: str | Path
    policy: str | Path | None = None
    output: str | Path | None = None
    trust_metrics: bool = False

@dataclass(frozen=True)
class CalculateGateResult:
    gate: dict
    output_path: Path | None
```

Review Run validation 오류는 일반 실행 오류와 구분한다.

```python
class ReviewRunValidationError(ValueError):
    errors: tuple[str, ...]
```

CLI는 이 예외만 별도로 받아 기존 `_print_errors()` 형식을 유지한다.

## 5. 설계 리뷰

### DR-1 — Gate exit code를 application에 포함

**결정:** 포함하지 않는다. Gate 결과는 application 결과이고 CLI exit code는 adapter 정책이다.

### DR-2 — Review Run validation을 CLI에 유지

**결정:** application으로 이동한다. typed validation exception으로 기존 출력 형식을 보존한다.

### DR-3 — 승인 파일을 각각 저장

**결정:** 금지한다. 기존 pair-atomic writer를 유지한다.

### DR-4 — Gate 정책 또는 rule lifecycle 확장 혼합

**결정:** 보류한다. 이번 Stage는 책임 이동과 발견된 저장 결함 보정만 수행한다.

### DR-5 — default policy 경로를 request 기본값으로 노출

**결정:** request는 `None`을 유지하고 application이 packaged asset을 선택한다.

## 6. 구현 리뷰와 보완

### IR-1 — 승인 후 candidate 파일이 다시 읽히지 않음

**발견**

기존 승인 로직은 candidate rule의 상태를 `approved`로 바꾸면서 `approval` 기록을 candidate 감사본에 넣지 않았다. 저장 직후 rule schema validation으로 다시 읽으면 실패했다.

**보완**

승격된 rule 전체와 `promoted_at`을 candidate 감사본에도 기록하도록 수정했다. candidate와 approved 파일 모두 저장 후 정상적으로 validation된다.

**상태:** CLOSED

### IR-2 — Gate validation 오류 출력 변화 위험

**발견**

일반 `ValueError`로 변환하면 기존 다중 오류 출력이 단일 `ERROR ...` 문장으로 바뀔 수 있었다.

**보완**

`ReviewRunValidationError.errors`를 CLI가 `_print_errors()`에 전달하도록 분리했다.

**상태:** CLOSED

### IR-3 — Gate 판정과 process exit code 결합 위험

**보완**

Application은 Gate dict만 반환하고 CLI가 `0` 또는 `3`을 결정하도록 유지했다.

**상태:** CLOSED

### IR-4 — 임시 적용·진단 자산

원격 적용에 사용한 script, workflow, unittest log와 status 파일은 최종 diff에서 모두 제거했다.

**상태:** CLOSED

## 7. 테스트

추가 검증:

1. rule approval이 두 파일을 함께 갱신
2. candidate와 approved 파일의 재검증
3. approval 실패 시 두 파일 불변
4. request 불변성
5. direct Gate 계산과 output 저장
6. invalid Review Run typed error와 output 미생성
7. CLI argument mapping
8. Gate validation 오류 형식
9. Gate exit code `0`/`3`

Python 3.11 적용 검증에서 전체 `122 tests`가 통과했다. 최종 PR matrix에서 Python 3.11·3.13·3.14와 package smoke, wheel build를 다시 검증한다.

## 8. Rollback

Stage 1C 변경을 revert하면 두 command의 inline orchestration으로 복귀한다. schema migration이나 외부 state migration은 없다.

## 9. Exit Criteria

- 두 CLI command가 thin adapter가 된다.
- application API를 argparse 없이 직접 호출할 수 있다.
- rule pair atomicity와 Gate validation/exit contract가 유지된다.
- candidate와 approved rule 파일이 저장 후 재검증된다.
- 신규 집중 테스트와 전체 회귀가 통과한다.
- 최종 diff에 임시 script·workflow·diagnostic 파일이 남지 않는다.
