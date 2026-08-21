# Trust Workflow Semantic Bridge D1 — Candidate Calibration v1

## 1. 목적

이 문서는 `WORKFLOW_BLANKET_R3_OVERCLASSIFICATION`의 production 수정 전에 수행하는 bounded candidate calibration을 동결합니다.

현재 Trust는 `.github/workflows/**` 경로를 무조건 `R3 / HIGH_RISK_PATH`로 분류합니다. Wave 1B seen baseline에서 RankingWiki RW-54는 ordinary domain algorithm + regression verifier wiring임에도 이 경로 규칙 하나 때문에 R2에서 R3으로 상승했습니다.

반면 KB-269와 KB-275는 workflow 안에서 실제 write authority를 변경하므로 R3을 유지해야 합니다.

이번 변경은 이 두 종류를 구별할 수 있는지 검증하는 candidate bridge이며, 아직 production Trust authority가 아닙니다.

## 2. Authority

```text
PIE main = 96b053f63a25465a4e75e58d755a62462b20ee68
Wave 1A freeze = c599f53f12bb9e8218b472752b3a8039f48413fb
Wave 1B seen baseline = 02c44376484c7f471307bf6470de8078d9e62492
Workflow semantic contract PR #42 head = 134c56377e007a115e84a101dd9c046ea5294c1d
```

Frozen holdout는 이번 작업에서 replay하지 않습니다.

## 3. Exact evidence binding

`workflow_semantics.py`의 evidence builder는 다음을 하나의 canonical identity로 묶습니다.

```text
exact source revision
source evidence SHA-256
changed-file set SHA-256
collected diff SHA-256
per-workflow patch SHA-256
per-workflow semantic classification
canonical evidence SHA-256
```

Workflow semantic evidence가 changed-file set이나 exact source revision과 맞지 않으면 bridge는 fail-closed합니다.

Production 연결 시에는 `analyze-pr`가 수집한 complete PR diff와 `github-source.json`의 exact evidence hash를 사용해야 합니다.

테스트 fixture의 `source_evidence_sha256`은 candidate mechanics 검증을 위한 synthetic deterministic binding입니다. 실제 GitHub source evidence라고 주장하지 않습니다. Fixture의 diff도 저장 크기를 제한하기 위해 workflow section만 포함하며 production complete-diff contract를 대체하지 않습니다.

## 4. Candidate mapping

Candidate bridge의 workflow path risk contribution은 다음과 같습니다.

| Semantic class | Candidate band | Reason |
| --- | --- | --- |
| `CI_TEST_WIRING_ONLY` | R2 | `WORKFLOW_CI_TEST_WIRING_ONLY` |
| `AUTHORITY_MUTATION` | R3 | `WORKFLOW_AUTHORITY_MUTATION` |
| `UNKNOWN` | R3 | `WORKFLOW_SEMANTICS_UNKNOWN` |

`UNKNOWN`은 안전하게 R3에 남습니다.

Non-workflow path, protected-path floor, task-class base band, review-pack corroboration은 현재 Trust projection과 동일하게 유지합니다.

## 5. Seen acceptance target

Semantic evidence를 주입하는 seen 표본은 세 건뿐입니다.

```text
RW-54  CI_TEST_WIRING_ONLY -> R2
KB-269 AUTHORITY_MUTATION  -> R3
KB-275 AUTHORITY_MUTATION  -> R3
```

나머지 20개 seen 표본은 candidate bridge를 적용하지 않고 current `_risk_projection`과 완전히 동일해야 합니다.

Acceptance target:

```text
SEEN_SAMPLES = 23
ACCEPTABLE_BAND_MATCH = 23 / 23
EXACT_EXPECTED_MATCH = 22 / 23
UNDERCLASSIFICATION = 0
RW-54 = R2
KB-269 = R3
KB-275 = R3
FROZEN_HOLDOUT_REPLAY = 0
```

KB-275는 frozen human prior가 R2이고 acceptable band가 R2/R3이므로 R3 유지가 boundary-acceptable입니다.

## 6. Production non-authority

이번 candidate bridge는 다음을 변경하지 않습니다.

```text
trust.py = unchanged
Trust request/report schema = unchanged
hard-gate projection = unchanged
.github/workflows/** production path floor = unchanged
profile = unchanged
review-pack selector = unchanged
R4 semantic inference = unchanged
Stage10K HUMAN_DECISION = unchanged
mode = REPORT_ONLY
automation authorization = unchanged / false
pilot authorization = unchanged / false
```

따라서 candidate calibration PASS는 production Trust 수정 승인이나 merge 승인이 아닙니다.

## 7. 다음 gate

Candidate CI가 전체 repository regression과 23-sample seen acceptance를 통과한 뒤에만 다음 별도 작업에서 production Trust bridge를 설계할 수 있습니다.

Production 단계에서는 최소한 다음이 함께 해결되어야 합니다.

1. `analyze-pr`의 complete collected diff에서 workflow evidence 생성
2. exact PR head / changed files / source evidence hash binding
3. Trust assessment 및 source replay에서 동일 evidence 재사용
4. `CI_TEST_WIRING_ONLY`만 blanket workflow R3 contribution을 완화
5. `AUTHORITY_MUTATION` / `UNKNOWN`은 R3 유지
6. hard-gate rollback/deployment semantics도 workflow semantic class와 모순되지 않도록 재검증

이번 문서는 그 production 변경을 수행하거나 승인하지 않습니다.
