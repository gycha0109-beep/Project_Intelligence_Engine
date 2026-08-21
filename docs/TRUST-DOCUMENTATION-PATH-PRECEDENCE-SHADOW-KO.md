# Trust Documentation Path Precedence — Shadow Calibration

## 1. 목적

Wave 1 frozen holdout adjudication에서 확인된 단일 defect `DOCUMENTATION_HIGH_RISK_FILENAME_TOKEN_COLLISION`을 authoritative Trust 변경 없이 shadow candidate로 검증합니다.

관측 sample은 `KB-274`입니다.

```text
docs/evidence/facelab/face-lab-d2d-x-execution-authorization-20260821-v1.md
```

현재 authoritative `_path_classification()`은 documentation 판정보다 R3 high-risk filename token 판정을 먼저 수행하므로 위 docs-only path를 R3로 분류합니다.

Human label은 R1이며, rationale은 documentation-only authorization record이고 runtime/security/database semantic mutation이 없다는 것입니다.

## 2. Authority

Base:

- Wave 1 holdout adjudication Draft PR #46
- base head: `b9adf5e7dbab9228743ac5a26900e7865e668b75`
- PR #46 CI #1159: SUCCESS / Python 3.11, 3.13, 3.14

Shadow remediation Draft PR #47 initial verified head:

- head: `512c6d78a171aac67a8f05db743770a4a35b76c8`
- CI #1165 / run `32458268724`: SUCCESS
- Python 3.11: SUCCESS
- Python 3.13: SUCCESS
- Python 3.14: SUCCESS

## 3. Candidate rule

Authoritative classification을 전면 재정의하지 않습니다.

Shadow candidate는 다음 조건만 중화합니다.

```text
authoritative path class == R3
AND _is_documentation_path(path) == true
=> candidate path class = R1
```

Reason:

```text
DOCUMENTATION_HIGH_RISK_TOKEN_NEUTRALIZED
```

이 규칙은 R4 결과를 변경하지 않습니다.

따라서 다음은 유지됩니다.

- `src/review_system/trust.py` -> R4
- `docs/policies/access-control.md` -> R4
- executable `src/auth/security.py` -> R3
- executable `supabase/migrations/*.sql` -> R3
- `.github/workflows/*.yml` -> authoritative R3; D1 workflow evidence가 있을 때만 기존 D1 semantics 적용

## 4. D1 historical contract 보존

PR #45의 blind prediction freeze는 당시 authoritative/D1 결과를 역사적으로 보존해야 합니다.

따라서 기존 public `project_candidate_risk()`의 default behavior는 변경하지 않았습니다.

`KB-274`에 대해:

```text
Authoritative: R3
D1 historical candidate: R3
Documentation-precedence shadow candidate: R1
```

이를 위해 `trust_workflow_bridge._candidate_risk_projection()` 내부에 path-classifier injection seam만 추가하고, 기존 public D1 함수의 호출 경로와 default classifier는 그대로 유지했습니다.

## 5. Calibration 결과

### Seen 23

D1 candidate 결과를 그대로 보존합니다.

- acceptable: **23 / 23**
- exact expected: **22 / 23**
- underclassification: **0**
- D1 -> documentation candidate band change: **0**

남은 exact-only boundary mismatch는 기존 `KB-275`이며 acceptable band 안에 있습니다.

### Frozen holdout 11

- acceptable: **11 / 11**
- exact expected: **11 / 11**
- underclassification: **0**
- D1 -> documentation candidate band change: **KB-274 only**

주요 결과:

```text
RW-57: R2 유지
KB-274: R3 -> R1
```

### Combined seen + holdout

- sample count: **34**
- acceptable: **34 / 34**
- exact expected: **33 / 34**
- underclassification: **0**

## 6. Safety properties

Shadow test는 다음을 고정합니다.

1. R3 documentation token collision만 R1로 중화
2. executable auth/security path는 R3 유지
3. executable migration SQL은 R3 유지
4. workflow authoritative floor는 별도 D1 evidence 없이는 R3 유지
5. verifier/policy R4는 유지
6. historical D1 prediction contract는 유지
7. seen 23에서 D1 대비 band drift 없음
8. holdout 11에서 KB-274 외 band drift 없음

## 7. 상태 판정

```text
DOCUMENTATION_HIGH_RISK_FILENAME_TOKEN_COLLISION shadow remediation: PASS
Seen + frozen holdout calibration: 34/34 acceptable, 0 underclassification
Authoritative promotion: NOT AUTHORIZED
```

이 결과는 shadow candidate의 calibration 통과를 의미하며 authoritative `trust.py` 변경, hard-gate 변경, merge, automation/pilot authorization 또는 Stage10K HUMAN_DECISION을 의미하지 않습니다.

## 8. 남은 별도 defect

이 PR은 다음 기존 defect를 의도적으로 다루지 않습니다.

- `GENERIC_POLICY_TOKEN_ACCESS_CONTROL_COLLISION`
- `R4_SEMANTIC_UNDERDETECTION`
- `PROJECT_SPECIFIC_HIGH_RISK_SEMANTIC_BLIND_SPOT`

각 defect는 one-defect-per-remediation 원칙에 따라 별도 calibration/remediation이 필요합니다.
