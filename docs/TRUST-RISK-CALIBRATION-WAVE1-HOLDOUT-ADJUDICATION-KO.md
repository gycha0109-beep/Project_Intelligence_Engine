# Trust Risk Calibration Wave 1 — Frozen Holdout Adjudication

## 1. 목적

이 문서는 Wave 1 `frozen_holdout`의 human label을 **prediction freeze가 exact-head CI로 재현된 뒤에만** 최초 개봉하여 D1 workflow-diff semantic candidate를 blind adjudication한 결과를 기록합니다.

이 단계는 calibration 결과 기록이며 authoritative Trust risk 정책 변경이나 merge 승인이 아닙니다.

## 2. Label-open authority

Prediction authority:

- Prediction Draft PR: #45
- Prediction head: `c9aa348edd617b34f07d37d4bcfdaf448750be08`
- Prediction fixture blob: `d7f9d97acccc3238da62fef5b73c6119d59998a2`
- Exact-head CI: run #1154 / `32457186199`
- Python 3.11: SUCCESS
- Python 3.13: SUCCESS
- Python 3.14: SUCCESS
- Frozen labels blob: `0e132fb18bfb3d1f841bbc1649632b60f3fe85ae`

PR #45의 prediction artifact는 `labels_opened_for_this_replay=false` 상태에서 먼저 동결되었고, CI #1154가 성공한 뒤에만 `wave1-labels.json`을 읽었습니다.

## 3. Pre-label replay correction

첫 prediction replay CI에서 KB-274가 재현되지 않았습니다.

원인은 human label이 아니라 current classifier와 prediction artifact 간의 불일치였습니다.

KB-274 changed path:

```text
docs/evidence/facelab/face-lab-d2d-x-execution-authorization-20260821-v1.md
```

현재 `_path_classification()`은 documentation 판정보다 먼저 filename의 `authorization` 토큰을 R3 high-risk path로 처리합니다. 따라서 current code가 재계산하는 authoritative/candidate prediction은 둘 다 R3입니다.

Human labels를 열기 전에 prediction artifact만 다음과 같이 교정했습니다.

```text
KB-274: authoritative R1 -> R3
KB-274: candidate     R1 -> R3
```

교정 후 exact-head `c9aa348e...`의 CI #1154가 3개 Python matrix에서 모두 성공했습니다.

## 4. Blind holdout 결과

Holdout sample 수: **11**

### Authoritative baseline

- exact expected: **9 / 11**
- acceptable band: **9 / 11**
- underclassification: **0**
- overclassification: **2**
- mismatch: `RW-57`, `KB-274`

### D1 candidate

- exact expected: **10 / 11**
- acceptable band: **10 / 11**
- underclassification: **0**
- overclassification: **1**
- mismatch: `KB-274`

### Delta

- exact expected: **+1**
- acceptable band: **+1**
- underclassification: **+0**
- overclassification: **-1**

## 5. D1 workflow-semantic scope

Holdout에서 workflow patch를 포함한 D1 관련 sample은 다음 3개입니다.

| Sample | Human | Authoritative | Candidate | Result |
|---|---:|---:|---:|---|
| RW-43 | R3 | R3 | R3 | PASS |
| RW-46 | R3 | R3 | R3 | PASS |
| RW-57 | R2 | R3 | R2 | PASS / corrected overpromotion |

RW-43과 RW-46의 workflow delta 자체는 `CI_TEST_WIRING_ONLY`이지만 migration path가 독립적으로 R3 floor를 유지합니다.

RW-57은 별도 high-risk floor가 없는 CI test wiring-only workflow change였고, candidate가 blanket workflow R3를 제거하여 human R2와 일치했습니다.

따라서 D1의 bounded objective는 holdout에서 **3 / 3 exact, underclassification 0**입니다.

Adjudication:

```text
PASS_FOR_WORKFLOW_SEMANTIC_SCOPE
```

이 판정은 D1 candidate의 workflow-specific discrimination에만 적용됩니다.

## 6. 남은 defect — KB-274

유일한 candidate mismatch는 `KB-274`입니다.

Human label:

- expected: R1
- acceptable: R1
- confidence: HIGH
- rationale: documentation-only authorization record이며 runtime/security/database semantic mutation 없음

Current Trust behavior:

- authoritative: R3
- D1 candidate: R3

Observed defect:

```text
DOCUMENTATION_HIGH_RISK_FILENAME_TOKEN_COLLISION
```

현재 path classifier는 documentation path인지 확인하기 전에 filename에서 `authorization`, `security`, `migration` 등의 high-risk token을 검사합니다. 따라서 docs-only evidence 문서가 제목 용어만으로 R3가 될 수 있습니다.

이 문제는 workflow blanket R3와 원인이 다르므로 D1 remediation에 섞지 않습니다.

## 7. 해석

Wave 1 holdout은 D1이 의도했던 것을 실제로 구분합니다.

- benign CI test wiring을 무조건 R3로 유지하지 않음
- migration이 함께 존재하면 R3를 유지함
- underclassification을 새로 만들지 않음

동시에 전체 calibration은 아직 닫히지 않았습니다. KB-274가 documentation path precedence 결함을 드러냈기 때문입니다.

따라서 전체 상태는:

```text
D1 workflow scope: PASS
Global calibration: IMPROVED_NOT_CLOSED
```

## 8. 한계

Frozen holdout에는 independent R4 sample이 없습니다.

따라서 이번 blind adjudication으로 다음을 주장할 수 없습니다.

- arbitrary external verifier/policy changes의 R4 blind generalization
- 전체 Trust risk taxonomy의 완전한 calibration closure

또한 이 artifact는 다음을 승인하지 않습니다.

- authoritative `trust.py` mutation
- D1 shadow candidate promotion
- hard-gate 변경
- automation/pilot authorization
- Stage10K HUMAN_DECISION
- PR #40~#45 merge

## 9. 다음 bounded remediation

다음 defect는 D1과 분리하여 처리해야 합니다.

```text
DOCUMENTATION_HIGH_RISK_FILENAME_TOKEN_COLLISION
```

최소 acceptance target:

1. documentation-only path는 filename에 `authorization`, `security`, `migration`, `policy` 같은 용어가 있어도 실행 가능한 high-risk change가 아니라면 R1 유지
2. 실제 executable auth/security/migration paths는 기존 R3 유지
3. verifier/policy authority R4는 약화하지 않음
4. seen + frozen holdout replay에서 underclassification 0 유지
5. KB-274 R3 -> R1 교정
6. human label을 이용한 per-sample special case 금지

이 remediation은 별도 branch/PR에서 다룹니다.
