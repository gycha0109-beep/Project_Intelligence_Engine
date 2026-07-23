# PIE Stage 1C — ApproveRule / CalculateGate Application Boundaries

기준일: 2026-07-23  
선행 기준선: PR #4 HEAD `7252d60cd5c767663619bd9b9dc14c6082281d82`  
작업 브랜치: `agent/stage-1c-rule-gate-boundary`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

Stage 1C는 규칙 승인과 Gate 계산 orchestration을 CLI에서 application 계층으로 분리한다.

```text
argparse Namespace
→ immutable Request
→ application use case
→ immutable Result
→ CLI 출력 / exit code
```

## 2. 범위

### 생성

```text
src/review_system/application/approve_rule.py
src/review_system/application/calculate_gate.py
tests/test_application_rule_gate.py
```

### 수정

```text
src/review_system/application/__init__.py
src/review_system/cli.py
docs/architecture/README.md
```

### 비목표

- `calculate-gate-dir` 분리
- Gate 정책 구조 또는 우선순위 변경
- rule schema 또는 approval audit 구조 변경
- rule discovery·evaluation 추가
- Evidence Ledger 또는 Policy Registry 구현
- CLI option·exit code 변경
- dependency·version·workflow 변경

## 3. 보호 계약

### ApproveRule

- candidate와 approved rule 파일을 기존 validation으로 읽는다.
- 승인 주체, 시각, 근거를 기존 구조로 기록한다.
- candidate와 approved 파일은 `dump_yaml_pair_atomic`으로 함께 갱신한다.
- 실패 시 두 파일의 부분 갱신을 허용하지 않는다.
- 성공 summary 문자열과 exit code `0`을 유지한다.
- 입력·실행 오류는 기존처럼 stderr와 exit code `2`로 변환한다.

### CalculateGate

- Review Run validation을 먼저 수행한다.
- validation 오류는 기존처럼 각 오류를 출력하고 exit code `2`를 반환한다.
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

**결정:** 포함하지 않는다. Gate 결과는 도메인 결과이고 CLI exit code는 adapter 정책이다.

### DR-2 — Review Run validation을 CLI에 유지

**결정:** application으로 이동한다. 대신 typed validation exception으로 기존 출력 형식을 보존한다.

### DR-3 — 승인 파일을 각각 저장

**결정:** 금지한다. 기존 pair-atomic writer를 그대로 사용한다.

### DR-4 — Gate policy 검증 또는 rule lifecycle 확장 혼합

**결정:** 보류한다. 이번 Stage는 책임 이동만 수행한다.

### DR-5 — default policy path를 request 기본값으로 노출

**결정:** request는 `None`을 유지하고 application이 packaged asset을 선택한다.

## 6. 테스트 계획

1. direct rule approval이 candidate audit와 approved rule을 함께 갱신
2. approval 실패 시 파일 불변
3. immutable request 검증
4. direct Gate PASS와 output 저장
5. direct Gate HOLD/FAIL 결과 보존
6. invalid Review Run typed validation error와 output 미생성
7. custom policy와 trust-metrics 전달
8. CLI request mapping과 delegation
9. Gate validation 오류 출력·exit `2`
10. Gate 결정별 exit `0`/`3`
11. 기존 전체 회귀
12. Python 3.11·3.13·3.14 matrix
13. profile/finding smoke와 wheel build

## 7. Rollback

Stage 1C 변경을 revert하면 두 command의 inline orchestration으로 복귀한다. schema, migration, artifact format 또는 외부 state migration이 없어 별도 data rollback은 필요하지 않다.

## 8. Exit Criteria

- 두 CLI command가 thin adapter가 된다.
- application API를 argparse 없이 직접 호출할 수 있다.
- rule pair atomicity와 Gate validation/exit contract가 유지된다.
- 신규 집중 테스트와 기존 전체 회귀가 통과한다.
- 최종 diff에 임시 script·workflow가 남지 않는다.
