# Trust Workflow Semantic Shadow D1 — Operational Evidence Bridge v1

## 1. 목적

이 변경은 `WORKFLOW_BLANKET_R3_OVERCLASSIFICATION`을 authoritative Trust classifier에 반영하기 전에, 실제 GitHub PR evidence와 candidate classifier를 연결하는 **shadow-only operational bridge**입니다.

핵심 원칙은 다음과 같습니다.

```text
CURRENT TRUST AUTHORITY = UNCHANGED
CANDIDATE WORKFLOW SEMANTICS = SHADOW_ONLY
FROZEN HOLDOUT = NOT REPLAYED IN THIS PR
```

Blind holdout를 열기 전에 authoritative risk band를 변경하면 calibration과 validation이 섞이므로, 이번 변경은 current Trust band와 candidate band를 나란히 계산할 뿐 current Trust report / hard gate / intake authority를 수정하지 않습니다.

## 2. Authority chain

```text
PIE main = 96b053f63a25465a4e75e58d755a62462b20ee68
Wave 1A freeze = c599f53f12bb9e8218b472752b3a8039f48413fb
Wave 1B seen baseline = 02c44376484c7f471307bf6470de8078d9e62492
Workflow semantic contract PR #42 = 134c56377e007a115e84a101dd9c046ea5294c1d
Candidate bridge PR #43 = 5b1fef895a1d92a3abbb3fc0604fce06dfe31224
```

PR #43에서 verified seen candidate result는 다음과 같습니다.

```text
SEEN = 23
ACCEPTABLE_BAND_MATCH = 23 / 23
EXACT_EXPECTED_MATCH = 22 / 23
UNDERCLASSIFICATION = 0
RW-54 = candidate R2
KB-269 = candidate R3
KB-275 = candidate R3
FROZEN_HOLDOUT_REPLAY = 0
```

## 3. analyze-pr sidecar

`pie analyze-pr`는 기존 GitHub source / impact / report / pull-request.diff 산출물을 유지합니다.

추가로 다음 두 조건이 모두 충족될 때만:

```text
PR HEAD = exact 40-hex git SHA
pull-request.diff = available
```

다음을 생성합니다.

```text
workflow-semantics.json
```

이 sidecar는 다음에 binding됩니다.

```text
exact source revision
GitHub source evidence SHA-256
complete collected PR diff SHA-256
changed-file-set SHA-256
per-workflow aggregated patch SHA-256
workflow semantic classification
workflow semantic evidence SHA-256
```

Diff가 skip되었거나 unavailable하거나 remote head가 exact SHA가 아니면 sidecar는 생성하지 않습니다. 같은 output directory에 stale sidecar가 있으면 제거합니다.

## 4. Multi-commit patch handling

`gh pr diff --patch`는 multi-commit PR에서 같은 파일이 여러 commit patch section에 반복될 수 있습니다.

따라서 workflow evidence reducer는 동일 path의 section을 **commit order대로 결합**합니다.

이 설계는 다음 효과를 가집니다.

- 같은 workflow에 여러 test wiring commit이 있으면 하나의 semantic evidence로 평가됩니다.
- write authority가 중간 commit에서 추가되었다가 제거되더라도 added/removed authority signal이 모두 남아 `AUTHORITY_MUTATION`으로 보수적으로 분류됩니다.
- 반복 section 자체를 malformed evidence로 오인하지 않습니다.

## 5. Shadow report

`trust_workflow_shadow.py`는 다음 입력을 직접 재검증합니다.

```text
Trust request
Project Profile
GitHub source evidence
pull-request.diff
```

검증 조건:

1. GitHub source schema/hash가 유효해야 합니다.
2. Trust request source revision이 GitHub exact PR HEAD와 같아야 합니다.
3. Trust request changed-files가 GitHub source changed-files와 정확히 같아야 합니다.
4. GitHub source가 diff를 requested + available로 기록해야 합니다.
5. supplied diff SHA-256이 GitHub source의 recorded diff SHA-256과 같아야 합니다.
6. workflow semantic evidence가 위 source identity로 다시 계산되어야 합니다.

하나라도 맞지 않으면 shadow 계산은 fail-closed합니다.

## 6. Shadow output

Shadow artifact는 다음을 함께 보존합니다.

```text
authority = SHADOW_ONLY
mode = REPORT_ONLY
automation_authorized = false
pilot_authorized = false

authoritative_risk_band
candidate_risk_band
band_delta
band_changed

authoritative_risk
candidate_risk
workflow semantic evidence references
shadow_sha256
```

`shadow_sha256`은 deterministic canonical payload hash입니다. 동일 source set은 동일 shadow artifact를 재현해야 합니다.

## 7. Candidate mapping

이번 shadow에서 사용하는 candidate workflow path mapping은 PR #43과 동일합니다.

| Workflow semantic class | Candidate contribution |
| --- | --- |
| `CI_TEST_WIRING_ONLY` | R2 |
| `AUTHORITY_MUTATION` | R3 |
| `UNKNOWN` | R3 |

Non-workflow path floor, protected path, task-class base band, review-pack corroboration은 current Trust semantics를 그대로 사용합니다.

## 8. Authoritative non-changes

이번 변경은 다음을 수정하지 않습니다.

```text
src/review_system/trust.py = UNCHANGED
Trust request schema = UNCHANGED
Trust report schema = UNCHANGED
hard-gate semantics = UNCHANGED
current .github/workflows/** R3 floor = UNCHANGED
profile semantics = UNCHANGED
review-pack selector = UNCHANGED
R4 inference = UNCHANGED
prospective intake authority = UNCHANGED
Stage10K HUMAN_DECISION = NONE
mode = REPORT_ONLY
automation_authorized = false
pilot_authorized = false
```

따라서 shadow candidate가 R2를 출력해도 current authoritative Trust는 여전히 기존 R3을 출력합니다.

## 9. Holdout boundary

이번 PR 자체에서는 frozen holdout를 읽거나 replay하지 않습니다.

이 PR의 CI가 통과한 뒤 다음 gate에서만 Wave 1A에 이미 동결된 `frozen_holdout` 11개를 **최초 1회 blind shadow replay**합니다.

Holdout 결과를 본 뒤 이 동일 holdout에 맞추어 classifier를 수정하고 다시 "blind"라고 부르는 것은 금지합니다.

Holdout replay 결과는 별도 generated result artifact로 저장하고, 기존 human labels를 수정하지 않습니다.

## 10. 다음 gate

```text
SHADOW INTEGRATION CI PASS
        ↓
FROZEN HOLDOUT BLIND SHADOW REPLAY
        ↓
HOLDOUT ACCEPT / REJECT
        ↓
only then consider authoritative Trust mutation
```

Holdout 통과 전에는 `.github/workflows/**` authoritative R3 path floor를 변경하지 않습니다.
