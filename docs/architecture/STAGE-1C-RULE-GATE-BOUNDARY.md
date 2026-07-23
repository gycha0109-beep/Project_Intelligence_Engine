# PIE Stage 1C — ApproveRule / CalculateGate Application Boundaries

기준일: 2026-07-23  
선행 기준선: PR #4 HEAD `7252d60cd5c767663619bd9b9dc14c6082281d82`  
작업 브랜치: `agent/stage-1c-rule-gate-boundary`  
Stacked PR: `#6`  
상태: `PASS`

## 목적

규칙 승인과 Gate 계산 orchestration을 CLI에서 application 계층으로 분리한다.

```text
argparse Namespace
→ immutable Request
→ application use case
→ immutable Result
→ CLI 출력 / exit code
```

## 최종 범위

생성:

```text
src/review_system/application/approve_rule.py
src/review_system/application/calculate_gate.py
tests/test_application_rule_gate.py
docs/architecture/STAGE-1C-RULE-GATE-BOUNDARY.md
```

수정:

```text
src/review_system/application/__init__.py
src/review_system/cli.py
src/review_system/intelligence_learning.py
docs/architecture/README.md
```

변경하지 않음:

- `calculate-gate-dir`
- Gate 정책 구조와 우선순위
- rule discovery·evaluation
- Evidence Ledger와 Policy Registry
- CLI option, package version, dependency
- public schema, preset, pack, workflow

## 보호 계약

### ApproveRule

- candidate와 approved rule 파일을 기존 validation으로 읽는다.
- 승인 주체, 시각, 근거를 기존 구조로 기록한다.
- 두 파일을 기존 pair-atomic writer로 함께 갱신한다.
- 실패 시 부분 갱신을 허용하지 않는다.
- 성공 `0`, 입력·실행 오류 `2`를 유지한다.

### CalculateGate

- Review Run validation을 먼저 수행한다.
- validation 오류는 기존 형식과 exit code `2`를 유지한다.
- 기본 policy, `--trust-metrics`, JSON output 동작을 유지한다.
- `PASS`·`CONDITIONAL_PASS`는 `0`, 그 외 판정은 `3`을 유지한다.

## Application 계약

```python
ApproveRuleRequest / ApproveRuleResult
CalculateGateRequest / CalculateGateResult
ReviewRunValidationError
```

모든 Request와 Result는 immutable dataclass다. Gate validation 오류는 별도 typed exception으로 전달해 CLI의 다중 오류 출력 형식을 보존한다.

## 설계 리뷰

- Gate exit code는 application 결과에 포함하지 않고 CLI adapter가 결정한다.
- Review Run validation은 application으로 이동하되 오류 목록은 보존한다.
- 규칙 파일은 개별 저장하지 않고 기존 원자적 pair writer를 유지한다.
- Gate 정책 확장, rule evaluation, ledger 작업은 범위 밖으로 유지한다.

## 구현 리뷰와 보완

### 승인 후 candidate 파일 재검증 실패

기존 로직은 candidate rule의 상태를 `approved`로 바꾸면서 candidate 감사본에 `approval` 기록을 넣지 않았다. 저장 직후 다시 읽으면 schema validation이 실패했다.

승격된 rule 전체와 `promoted_at`을 candidate 감사본에도 기록하도록 수정했다. candidate와 approved 파일 모두 저장 후 정상적으로 재검증된다.

### Gate 오류·종료 코드 보존

`ReviewRunValidationError.errors`를 CLI가 기존 `_print_errors()`로 출력하도록 분리했다. Gate dict는 application이 반환하고 process exit code `0` 또는 `3`은 CLI가 결정한다.

### 임시 자산 제거

원격 적용에 사용한 script, workflow, unittest output과 status 파일은 최종 diff에서 모두 제거했다.

## 검증

최종 검증 HEAD: `7dff93e8519e2140d6b535fd2e38a8293a245756`  
GitHub Actions run: `29997076383`

| 검증 | Python 3.11 | Python 3.13 | Python 3.14 |
|---|---:|---:|---:|
| Package install | PASS | PASS | PASS |
| Package asset sync | PASS | PASS | PASS |
| 122 unit tests | PASS | PASS | PASS |
| CLI/version smoke | PASS | PASS | PASS |
| 4 preset profile validation | PASS | PASS | PASS |
| Finding validation | PASS | PASS | PASS |
| Wheel build | PASS | PASS | PASS |

## 판정

```text
Detailed Design: PASS
Design Review: PASS
Implementation: PASS
Implementation Review: PASS
Regression Verification: PASS
Compatibility Decision: PRESERVED
Stage 1C Gate: PASS
```

## 다음 작업

남은 CLI orchestration을 점검해 Application Boundary Extraction을 동결한 뒤 Evidence Ledger 단계로 진입한다.
