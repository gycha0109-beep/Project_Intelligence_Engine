# Stage 10D Implementation Review

상태: `PASS`

기준선: PR #19 HEAD `c3a9facd6e2f530dfea069cb092636be734cee2e`

## 구현 결과

- R0-only report-only observation threshold policy schema
- R0 safe cohort와 all-band confirmed unsafe challenge cohort 분리
- R0 auto-pass boundary 전용 TP/FP/TN/FN projection
- observed R0 false negative zero-tolerance policy floor
- evidence timestamp 기반 관찰 span
- distinct R0 assessment 단위 independent Audit count
- embedded policy threshold snapshot과 self-contained projection verification
- Stage 10B registry + threshold policy source replay
- `pie-trust` additive commands와 `pie-trust-observation` entry point
- symlink input/output fail-closed 및 atomic output preservation
- 모든 결과에서 `automation_authorized=false`, `pilot_authorized=false`

## 구현 리뷰에서 발견하고 수정한 문제

### 1. 통과 불가능한 unsafe denominator

초기 설계는 R0 cohort 안에서 unsafe 표본을 1건 이상 요구하면서 R0 false negative는 0건을 요구했다. R0로 분류된 unsafe Outcome은 정의상 R0 pilot false negative이므로 두 조건은 동시에 만족할 수 없었다.

수정:

```text
R0 + SAFE    = TN
R0 + UNSAFE  = FN
>R0 + UNSAFE = TP
>R0 + SAFE   = FP
```

- R0 safe 운영 표본은 R0 cohort에서 집계한다.
- unsafe challenge denominator는 모든 conclusive UNSAFE Outcome에서 집계한다.
- R0 FNR은 `FN / (TP + FN)`으로 계산한다.

### 2. unsafe denominator 0의 가짜 완벽성

unsafe challenge가 0일 때 FNR을 0으로 두면 미탐이 없는 것처럼 보일 수 있었다.

수정:

- unsafe denominator 0이면 `r0_false_negative_rate=null`
- null metric은 maximum threshold를 만족하지 못한다.
- 별도 `minimum_confirmed_unsafe_challenge_count >= 1` structural floor를 둔다.

### 3. report가 policy 의미를 충분히 self-contained 검증하지 못할 위험

policy ID/hash reference만 보존하면 outer hash를 다시 만든 변조에서 threshold 의미를 독립 재계산하기 어렵다.

수정:

- report에 threshold snapshot을 내장한다.
- embedded policy ID/hash를 다시 계산한다.
- 10개 check set/order와 actual/required/pass를 다시 계산한다.
- status, blocker, next step을 다시 계산한다.
- R0 conclusive count, safe count, unsafe denominator, coverage, FNR arithmetic을 재검산한다.

단, Registry에서 유도된 source metric 자체의 진실성은 standalone report만으로 증명할 수 없다. 그 부분은 `--registry` + `--policy` source replay가 권위 검증이다.

### 4. 생성 시각으로 observation span을 부풀릴 위험

수정:

- `generated_at`은 evidence span 계산에 사용하지 않는다.
- R0 assessment capture 및 연결 event timestamp만 사용한다.
- 동일 registry를 1년 뒤 다시 보고해도 evidence span은 동일하다.

### 5. output symlink에서 하위 Stage 오류 타입 누출

Stage 10B atomic writer의 path guard가 `TrustComparisonError`를 발생시켜 Stage 10D 전용 CLI error contract를 벗어날 수 있었다.

수정:

- Stage 10D `write_report` 경계에서 `TrustObservationError`로 정규화한다.
- 전용 CLI는 해당 입력 오류를 exit 3으로 처리한다.

### 6. atomic replace 및 valid-source mutation 회귀 부족

추가 hardening:

- input/output symlink reject
- atomic replace 실패 시 기존 report bytes 보존
- outer corruption이 아닌 **유효한 Stage 10B registry 변경**도 source replay mismatch로 탐지

### 7. repeated Audit event로 threshold를 부풀릴 수 있는 cardinality 오류

초기 구현은 `INDEPENDENT_AUDIT` event 개수를 직접 세었다. 같은 assessment에 Audit event를 반복 추가하면 minimum audit threshold를 부풀릴 수 있었다.

수정:

- `r0_independent_audit_count`는 conclusive independent Audit이 존재하는 **distinct R0 assessment 수**로 계산한다.
- 동일 assessment 반복 Audit이 count를 늘리지 않는 regression을 추가했다.

### 8. malformed report에서 semantic verifier가 비정상 종료할 가능성

Schema가 이미 깨진 report에 대해 semantic projection을 계속 수행하면 누락 field에서 `KeyError`가 발생할 수 있었다.

수정:

- schema-invalid report는 semantic projection에 진입하지 않고 validation errors를 반환한다.
- malformed checks 회귀를 추가했다.

### 9. repository sample policy가 CI 검증 대상이 아니었던 문제

수정:

- `examples/trust-observation-policy.sample.json`을 실제 `load_policy`로 검증하는 regression을 추가했다.
- sample에서도 report-only/R0/zero-miss invariant를 확인한다.

## Policy governance 경계

`examples/trust-observation-policy.sample.json`의 20/10/5/14일 등의 수치는 **비규범적 schema/CLI 예시**다.

Stage 10D는 다음을 하지 않는다.

- 적정 표본 수 자동 추천
- 관찰 기간 자동 추천
- threshold 자동 완화
- 조직 정책으로 sample 값을 승격

코드가 강제하는 유일한 안전 floor는 minimum count/coverage/span이 0이 아니어야 한다는 구조적 조건과 observed R0 FN/FNR 허용치가 0이라는 조건이다.

## 안전 경계

- threshold를 모두 만족해도 `THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION`일 뿐이다.
- source reconciliation은 `required_before_pilot=true`, `verified_in_this_stage=false`로 고정한다.
- R0 auto-pass 실행 경로를 만들지 않았다.
- GitHub approve/merge/comment/label/write를 추가하지 않았다.
- R1 conditional approval을 시작하지 않았다.
- reviewer alignment는 safety threshold가 아니다.
- Outcome 없는 사례는 SAFE로 간주하지 않는다.

## 알려진 제한

- Stage 10C source reconciliation은 아직 구현되지 않았다.
- Defect Registry/Evaluation 원본과 Outcome reference의 존재성은 Stage 10D가 검증하지 않는다.
- 실제 threshold 조직 governance는 별도 policy 결정이 필요하다.
- cryptographic signer identity와 cross-process lock은 없다.
- Stage 10D report는 pilot authorization artifact가 아니다.

## 검증 근거

- initial exact-head CI: HEAD `4e7f55d75416acb009110a4c490c9ce78a7252c4`, run `32084224419` / #641 — Python 3.11·3.13·3.14 성공
- first hardening CI: HEAD `b9e1c1b8b1a3e3c5088b9a1474be882211ee0519`, run `32084469804` / #647 — Python 3.11·3.13·3.14 성공
- final code hardening CI: HEAD `20f13be01f2c5c768ae4a9100016473baf3bfedd`, run `32084758761` / #659 — Python 3.11·3.13·3.14 성공

Documentation-inclusive final exact-head CI authority는 PR #20 body에 기록한다.
