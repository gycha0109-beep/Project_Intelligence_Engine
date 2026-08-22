# Trust R4 Verifier-Role Remediation — Shadow Calibration

## Status

- defect: `EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_GAP`
- candidate contract: `TRUST_R4_EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_SHADOW_V1`
- PIE authority main: `7aa435f1b5afd208a05b222f5bed55da77d4c6e8`
- Trust risk model: `1.3`
- mode: `REPORT_ONLY`
- authority: `SHADOW_ONLY`
- `automation_authorized = false`
- `pilot_authorized = false`
- authoritative remediation: **not authorized**
- blind holdout claim: **not made**
- shadow calibration: **PASS**

이 calibration은 PR #53의 MasterV audit에서 분리된 세 gap 중 `EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_GAP` 하나만 다룹니다.

별도 범위:

- `SIGNING_TRUST_ROOT_AUTHORITY_GAP` — R3
- `PRODUCTION_EXECUTION_BOUNDARY_GAP` — R3

이번 작업은 두 R3 gap을 수정하거나 함께 일반화하지 않습니다.

## 1. Trigger evidence

MasterV PR #7의 핵심 verifier:

```text
scripts/desktop-rel-1c-published-updater-windows.mjs
```

는 실제 public release를 읽고, published updater path를 실행하며, signature acceptance를 검증한 뒤 durable evidence를 기록합니다.

성공 authority:

```text
MASTERV_REL_1C_PUBLISHED_UPDATER_SIGNATURE_ACCEPTANCE_PASS
```

PR #53 shadow audit에서 current Trust v1.3은 이 파일을:

```text
SUPPORTING_REGRESSION_ONLY
is_r4_authority = false
```

로 판별했습니다.

Evidence status:

```text
post-Wave1 independent source = YES
selected after source inspection = YES
blind evidence = NO
blind generalization claim = NO
```

## 2. Rejected broad rules

다음 규칙은 사용하지 않습니다.

```text
PASS string -> R4
scripts/verify-* -> R4
release word -> R4
MasterV -> R4
```

같은 MasterV PR #7 내부의 supporting contract:

```text
scripts/desktop-rel-1c-contract.mjs
```

는 live verifier의 marker를 검사하지만 실제 published release 관측이나 durable acceptance evidence를 생성하지 않습니다. Candidate는 이 파일을 R4로 올리지 않습니다.

## 3. Candidate discriminator

Candidate는 current classifier가 이미:

```text
SUPPORTING_REGRESSION_ONLY
```

로 판정한 executable supporting path만 재검토합니다.

R4 candidate 승격에는 다음 조건을 모두 요구합니다.

1. explicit acceptance / verification / closure `PASS|SUCCESS` outcome
2. external or operational observation
3. durable evidence output
4. published / production / hosted / signed-release operational context
5. fail-closed behavior
6. executable assertion behavior
7. explicit evaluation-only ceiling 부재

Candidate output class는 기존 class를 재사용합니다.

```text
EXECUTABLE_VERIFICATION_GATE_AUTHORITY
```

Candidate reason set:

```text
R4_EXECUTABLE_ACCEPTANCE_OUTCOME
R4_EXTERNAL_OPERATIONAL_OBSERVATION
R4_DURABLE_ACCEPTANCE_EVIDENCE
R4_FAIL_CLOSED_EXECUTION
```

## 4. Calibration result

### Real positive

```text
MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER
current   = SUPPORTING_REGRESSION_ONLY
candidate = EXECUTABLE_VERIFICATION_GATE_AUTHORITY
candidate R4 = true
RESULT = CORRECTED
```

### Real same-PR negative

```text
MV-7-SUPPORTING-CONTRACT-NEGATIVE
current   = SUPPORTING_REGRESSION_ONLY
candidate = SUPPORTING_REGRESSION_ONLY
candidate R4 = false
RESULT = PRESERVED
```

Acceptance marker 문자열을 참조하더라도 external observation과 durable acceptance evidence가 없으므로 승격하지 않습니다.

### Synthetic negative controls

다음 네 control도 모두 비승격 상태를 유지했습니다.

1. live endpoint regression + durable smoke log, acceptance authority outcome 없음
2. acceptance marker contract, live observation/evidence output 없음
3. live synthetic evaluation, explicit evaluation-only ceiling 존재
4. live acceptance output, durable evidence 없음

```text
synthetic false-positive promotions = 0
```

## 5. Existing v1.3 R4 regression

기존 fixture:

```text
tests/fixtures/trust-risk-calibration/r4-semantic-underdetection-seen-v1.json
```

를 그대로 재사용했습니다.

기존 real seen positives:

```text
KB-262
KB-272
KB-277
KB-279
AR-30
```

모두 기존 classification을 유지했습니다.

기존 negatives:

```text
RW-54
KB-275
NEG-DOC-VERIFICATION
NEG-DOMAIN-POLICY
```

도 모두 기존 classification을 유지했고 새 R4 promotion은 발생하지 않았습니다.

```text
existing v1.3 R4 positives preserved = 5/5
existing v1.3 negative controls preserved = 4/4
```

## 6. Genericity boundary

Candidate implementation은 repository name이나 `MasterV` token을 risk input으로 사용하지 않습니다.

동일 source에서 status prefix를 neutral product vocabulary로 바꾼 synthetic genericity check도 candidate R4를 유지했습니다.

따라서 calibration target은:

```text
EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE
```

이며 다음은 아닙니다.

```text
MASTERV_VERIFIER
```

## 7. Candidate risk projection

Core MV-7 verifier path 단독 bounded projection에서:

```text
current v1.3 effective band = R2
candidate effective band    = R4
candidate reason            = SEMANTIC_R4_VERIFIER_ROLE_CANDIDATE
```

PR #53에서 확인된 실제 MV-7 PR aggregate current band는 workflow `UNKNOWN` floor 때문에 R3입니다. 이번 calibration은 full original PR candidate replay를 새로 주장하지 않으며, verifier path에 R4 semantic authority를 부여하는 bounded role discriminator만 검증합니다.

## 8. Initial exact-head verification

Implementation/calibration head:

```text
9f188fa3fe034c494406736f4e8f2ee11d3ad179
```

CI:

```text
CI #1243
run_id = 32543288688
conclusion = SUCCESS
```

Matrix:

```text
Python 3.11 = SUCCESS
Python 3.13 = SUCCESS
Python 3.14 = SUCCESS
full unittest = SUCCESS
asset sync = SUCCESS
all profile validations = SUCCESS
findings validation = SUCCESS
wheel build = SUCCESS
```

## 9. Evidence ceiling

이번 candidate는 one post-Wave1 real positive에서 출발합니다.

따라서 이번 PASS는 다음을 의미하지 않습니다.

- blind R4 generalization
- 모든 release verifier coverage
- 모든 언어/runtime verifier coverage
- authoritative Trust remediation readiness
- risk model v1.4 확정

Shadow PASS의 의미는 다음으로 제한됩니다.

> 확인된 executable acceptance verifier gap을 기존 v1.3 seen positives/negatives와 bounded false-positive controls를 깨뜨리지 않는 generic discriminator로 분리할 수 있다.

## 10. Explicit non-actions

이번 PR은 다음을 하지 않습니다.

- `trust.py` 수정
- `trust_r4_semantics_authority.py` 수정
- schema 수정
- profile/review-pack 수정
- risk model version 변경
- R3 signing gap 수정
- R3 production execution boundary 수정
- automation/pilot authorization
- Stage10K HUMAN_DECISION
- authoritative promotion
- merge authorization

## 11. Final gate

결과 문서 동결 commit까지 포함한 final exact-head CI를 별도로 요구합니다.

현재 authority ceiling:

```text
R4_VERIFIER_ROLE_REMEDIATION_SHADOW = PASS
AUTHORITATIVE_REMEDIATION = NOT_AUTHORIZED
AUTHORITATIVE_PROMOTION = NOT_AUTHORIZED
PR54_MERGE = NOT_AUTHORIZED
STAGE10K_HUMAN_DECISION = NO
```
