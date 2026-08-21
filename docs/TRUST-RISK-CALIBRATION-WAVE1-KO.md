# PIE Trust Risk Calibration — Wave 1A Freeze

## 1. Status

`WAVE1A_CORPUS_LABEL_SPLIT_FROZEN`

이 문서는 Trust/Risk remediation의 실사용 calibration 자료를 고정하기 위한 evidence note입니다.

이번 변경은 classifier remediation이 아닙니다.

- `src/review_system/trust.py` 변경 없음
- review-pack selector 변경 없음
- Project Profile 변경 없음
- automation/pilot authorization 변경 없음
- Stage10K HUMAN_DECISION 생성/추론 없음
- Factory Intelligence / Software Factory 범위 확장 없음

## 2. PIE Authority

Wave 1A의 PIE 기준선:

- repository: `gycha0109-beep/Project_Intelligence_Engine`
- authoritative main: `96b053f63a25465a4e75e58d755a62462b20ee68`
- tree: `478e938fafa800d410ca9bf25b45ee03a1557967`

이 기준선 이후 classifier를 수정하기 전에 corpus, human prior, partition을 먼저 고정합니다.

## 3. Raw Corpus Snapshot

Source window:

- start inclusive: `2026-08-19T00:00:00Z`
- end exclusive: `2026-08-21T03:00:00Z`

03:00Z cutoff은 기존에 수집한 69 PR snapshot을 재현하기 위해 고정합니다. 이후 생성된 PR은 Wave 1 입력에 소급 편입하지 않습니다.

| Repository | PRs | Count |
|---|---|---:|
| BuildMap | #42–#67 | 26 |
| AnnoyingRadar | #30–#33 | 4 |
| RankingWiki (`ranking`) | #41–#60 | 20 |
| MasterV | #3 | 1 |
| BEJEWELY (`K_beauty`) | #262–#279 | 18 |
| **Total** |  | **69** |

69개 PR은 69개의 독립 calibration sample로 취급하지 않습니다. lifecycle-correlated implementation/closeout/remediation/helper PR이 포함되어 있기 때문입니다.

## 4. Leakage Correction

초기 탐색 중 일부 PR은 이미 current PIE risk output을 확인했습니다.

따라서 이 표본은 blind holdout으로 재분류하지 않습니다.

Wave 1A partition:

| Partition | PR samples | Authority |
|---|---:|---|
| `calibration_seen` | 13 | classifier remediation 설계에 사용 가능 |
| `seen_validation` | 10 | 이미 관찰됨; blind claim 금지 |
| `frozen_holdout` | 11 | Wave 1A freeze 시점 current PIE replay 미실행 |
| `external_seen_probe` | 5 | profile mismatch 상태의 이미 관찰된 외부 probe |
| excluded | BuildMap #67 | prior observation revision을 exact SHA로 고정하지 못한 뒤 open PR head drift 발생 |

BuildMap #67은 과거 관찰을 현재 head에 소급 귀속시키지 않습니다. revision ambiguity를 피하기 위해 scoring set에서 제외했습니다.

## 5. Frozen Holdout

Frozen holdout은 11 PR / 9 lifecycle clusters입니다.

- BuildMap: #47
- RankingWiki: #43, #44, #45, #46, #47, #48, #53, #57
- BEJEWELY: #274, #276

Expected-band coverage:

- R1: 6
- R2: 3
- R3: 2
- R4: 0

### R4 limitation

현재 69 PR snapshot의 독립적인 R4 후보는 이미 관찰된 lifecycle과 강하게 상관되어 있습니다.

따라서 R4 표본을 억지로 holdout에 넣어 leakage를 만들지 않습니다.

**Wave 1 frozen holdout으로 blind R4 generalization을 주장할 수 없습니다.**

R4 remediation은 calibration/seen evidence로 개발할 수 있지만, 일반화 판정에는 이후 fresh independent R4 sample이 추가로 필요합니다.

## 6. Human Prior Freeze

`wave1-labels.json`은 PIE output과 분리된 human prior authority입니다.

각 label은 다음을 고정합니다.

- `expected_band`
- `acceptable_bands`
- `confidence`
- `semantic_classes`
- `rationale`

Boundary case는 `acceptable_bands`로 별도 표시합니다. 예를 들어 작은 workflow permission/control-plane 변경이나 test harness는 R2/R3 경계가 될 수 있습니다.

Human labels 파일에는 다음 PIE 결과 필드를 저장하지 않습니다.

- effective risk
- path floor
- corroborated floor
- selected review packs
- underdeclared status
- hard-gate result

이 분리는 output을 본 뒤 prior를 맞추는 calibration contamination을 방지합니다.

## 7. Lifecycle Isolation

`frozen_holdout` lifecycle cluster는 calibration/seen/external partition과 교차할 수 없습니다.

같은 implementation-closeout 또는 같은 remediation continuation을 서로 다른 calibration/holdout으로 나누지 않습니다.

Fixture integrity test가 이 조건을 강제합니다.

## 8. External Generalization Boundary

AnnoyingRadar #30–#33과 MasterV #3은 useful evidence지만 현재 dedicated PIE profile이 없습니다.

따라서 Wave 1A에서는:

`external_seen_probe`

로만 동결합니다.

이 표본을 authoritative calibration accuracy 계산에 섞지 않습니다. profile 문제와 classifier 문제를 분리하기 위해서입니다.

## 9. Frozen Artifacts

- `tests/fixtures/trust-risk-calibration/wave1-corpus.json`
- `tests/fixtures/trust-risk-calibration/wave1-labels.json`
- `tests/fixtures/trust-risk-calibration/wave1-split.json`
- `tests/test_trust_risk_calibration_wave1_fixtures.py`

Fixture test는 corpus/label/split 무결성만 검사합니다.

**Holdout에 대해 Trust classifier를 실행하지 않습니다.**

## 10. Next Boundary

Wave 1A가 merge되더라도 다음을 의미하지 않습니다.

- risk classifier가 calibrated 되었다는 의미 아님
- D1–D4 defect가 remediate 되었다는 의미 아님
- holdout PASS 의미 아님
- R4 generalization 검증 의미 아님

다음 작업은 frozen 기준선에 대해 현재 classifier baseline output을 별도 artifact로 기록하는 것입니다. 그 뒤 defect remediation은 하나씩 분리해서 진행합니다.

Planned remediation order:

1. `GENERIC_POLICY_TOKEN_ACCESS_CONTROL_COLLISION`
2. `WORKFLOW_BLANKET_R3_OVERPROMOTION`
3. `R4_SEMANTIC_UNDERDETECTION`

`PROJECT_SPECIFIC_HIGH_RISK_SEMANTIC_BLIND_SPOT`은 AnnoyingRadar/MasterV profile/generalization 문제와 분리해 유지합니다.
