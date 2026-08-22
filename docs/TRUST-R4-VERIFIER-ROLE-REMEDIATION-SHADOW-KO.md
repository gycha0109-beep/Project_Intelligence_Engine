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
- verification: **PENDING EXACT-HEAD CI**

이 calibration은 PR #53의 MasterV audit에서 분리된 세 gap 중 R4 verifier-role gap 하나만 다룹니다.

다음은 별도 범위입니다.

- `SIGNING_TRUST_ROOT_AUTHORITY_GAP` — R3
- `PRODUCTION_EXECUTION_BOUNDARY_GAP` — R3

이번 작업은 두 R3 gap을 수정하거나 함께 일반화하지 않습니다.

## 1. Trigger evidence

MasterV PR #7의 핵심 verifier:

```text
scripts/desktop-rel-1c-published-updater-windows.mjs
```

는 실제 public release를 읽고, published updater path를 실행하며, signature acceptance를 검증한 뒤 durable evidence를 기록합니다.

그 성공 authority는:

```text
MASTERV_REL_1C_PUBLISHED_UPDATER_SIGNATURE_ACCEPTANCE_PASS
```

입니다.

PR #53 shadow audit에서 current Trust v1.3은 이 파일을:

```text
SUPPORTING_REGRESSION_ONLY
is_r4_authority = false
```

로 판별했습니다.

PR 전체는 workflow `UNKNOWN` floor 때문에 R3이지만 frozen band intent상 verifier authority 자체는 R4입니다.

Evidence status:

```text
post-Wave1 independent source = YES
selected after source inspection = YES
blind evidence = NO
blind generalization claim = NO
```

## 2. Why a generic PASS rule is rejected

다음과 같은 규칙은 허용하지 않습니다.

```text
PASS string -> R4
scripts/verify-* -> R4
release word -> R4
MasterV -> R4
```

이런 규칙은 supporting regression harness, contract checker, synthetic evaluation을 과승격시킵니다.

실제 같은 MasterV PR #7 안에도 다음 supporting contract가 존재합니다.

```text
scripts/desktop-rel-1c-contract.mjs
```

이 파일은 live verifier의 marker와 구조를 검사하지만 실제 published release를 관측하거나 acceptance evidence를 생성하지 않습니다. Candidate는 이 파일을 R4로 올리면 안 됩니다.

## 3. Candidate discriminator

Candidate는 current classifier가 이미:

```text
SUPPORTING_REGRESSION_ONLY
```

로 판정한 executable supporting path만 재검토합니다.

R4 candidate 승격에는 다음 조건을 **모두** 요구합니다.

1. explicit acceptance / verification / closure `PASS|SUCCESS` outcome
2. external or operational observation
3. durable evidence output
4. published / production / hosted / signed-release 등 operational acceptance context
5. fail-closed behavior
6. executable assertion behavior
7. explicit evaluation-only ceiling 부재

즉:

```text
SUPPORTING_REGRESSION_ONLY
+ acceptance authority outcome
+ external observation
+ durable evidence
+ operational context
+ fail closed
+ assertions
!= ordinary regression harness
```

Candidate output class는 새 authority vocabulary를 만들지 않고 기존 class를 재사용합니다.

```text
EXECUTABLE_VERIFICATION_GATE_AUTHORITY
```

## 4. Calibration matrix

### Positive

`MV-7-LIVE-PUBLISHED-UPDATER-ACCEPTANCE-VERIFIER`

Expected:

```text
current   = SUPPORTING_REGRESSION_ONLY
candidate = EXECUTABLE_VERIFICATION_GATE_AUTHORITY
R4        = true
```

### Real same-PR negative

`MV-7-SUPPORTING-CONTRACT-NEGATIVE`

Expected:

```text
current   = SUPPORTING_REGRESSION_ONLY
candidate = SUPPORTING_REGRESSION_ONLY
```

Acceptance marker 문자열을 참조하더라도 실제 external observation과 durable acceptance evidence가 없으므로 승격하지 않습니다.

### Synthetic negative controls

1. live endpoint regression + durable smoke log, but no acceptance authority outcome
2. acceptance marker contract check, but no live observation/evidence output
3. live synthetic evaluation with explicit evaluation-only ceiling
4. live acceptance output without durable evidence

모두 R4 승격 금지입니다.

## 5. Existing v1.3 R4 regression

기존 fixture:

```text
tests/fixtures/trust-risk-calibration/r4-semantic-underdetection-seen-v1.json
```

를 그대로 재사용합니다.

기존 real seen positives:

```text
KB-262
KB-272
KB-277
KB-279
AR-30
```

은 기존 classification을 유지해야 합니다.

기존 negatives:

```text
RW-54
KB-275
NEG-DOC-VERIFICATION
NEG-DOMAIN-POLICY
```

도 candidate로 새롭게 R4가 되어서는 안 됩니다.

따라서 이번 calibration의 핵심 acceptance condition은:

```text
MV-7 live verifier corrected = YES
same-PR supporting contract promoted = NO
existing v1.3 R4 positives preserved = YES
existing v1.3 negatives preserved = YES
synthetic false-positive controls = 0
```

입니다.

## 6. Genericity boundary

Candidate implementation은 repository name이나 MasterV token을 입력으로 사용하지 않습니다.

동일 semantic source에서 status prefix를 neutral product vocabulary로 바꾸어도 candidate classification이 동일해야 합니다.

이번 calibration이 검증하려는 일반 class는:

```text
EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE
```

이지:

```text
MASTERV_VERIFIER
```

가 아닙니다.

## 7. Evidence ceiling

이번 candidate는 one post-Wave1 real positive에서 출발합니다.

따라서 성공하더라도 다음을 주장하지 않습니다.

- blind R4 generalization
- 모든 release verifier coverage
- 모든 언어/runtime verifier coverage
- authoritative Trust remediation readiness
- risk model v1.4 필요성 확정

Shadow PASS의 의미는 오직:

> 현재 확인된 executable acceptance verifier gap을 기존 seen positives/negatives를 깨뜨리지 않는 bounded generic discriminator로 분리할 수 있는가?

입니다.

## 8. Explicit non-actions

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

## 9. Verification target

Exact-head CI에서 최소 다음을 요구합니다.

```text
candidate matrix = exact
MV-7 live positive = corrected to R4 candidate
same-PR supporting contract = unchanged
existing v1.3 R4 matrix = unchanged
synthetic false-positive controls = 0
Python 3.11 = SUCCESS
Python 3.13 = SUCCESS
Python 3.14 = SUCCESS
full unittest = SUCCESS
profile/findings/wheel validation = SUCCESS
```

CI 성공 전 최종 상태는:

```text
R4_VERIFIER_ROLE_REMEDIATION_SHADOW = CALIBRATION_PENDING
AUTHORITATIVE_REMEDIATION = NOT_AUTHORIZED
```
