# Stage 6 — Evaluation Lab

상태: `DESIGN_REVIEW_PASS`

권위 기준선: PR #13 HEAD `f171129935b6617ed5d69983b50f07fab2399b3c`

## 1. 목적

후보 Rule을 승인하기 전에 동일한 사람이 라벨링한 데이터셋에서 현재 승인 Rule 집합과 후보 Rule 집합을 동일 조건으로 실행하고, 재현 가능한 성능·회귀 증거를 만든다.

Stage 6은 AI judge를 사용하지 않는다. 기존 PIE `analyze_change()`의 결정적 출력과 사람이 고정한 기대값만 비교한다.

## 2. 비목표

- 기존 `approve-rule`을 evaluation 필수 조건으로 즉시 변경하지 않는다.
- 기존 Rule schema version을 변경하지 않는다.
- 원격 저장소 clone이나 GitHub API 실행을 Evaluation Lab 내부에서 수행하지 않는다.
- 모델 기반 유사도·LLM 평가·자동 라벨 생성은 추가하지 않는다.
- Stage 5 Defect Registry lifecycle을 자동 전이하지 않는다.
- Journey Connect 12개 PR의 라벨을 근거 없이 생성하지 않는다.

## 3. Dataset 권위 계약

Dataset은 JSON 또는 YAML 단일 문서이며 모든 입력 artifact는 dataset 파일의 디렉터리를 기준으로 한 상대 경로다.

```text
schema_version: "1.0"
dataset_id: stable string
cases:
  - case_id
    repository
    source_revision
    split: development | validation | holdout
    input_artifacts:
      graph
      changed_files
    configured_packs: []
    expected_changed_scope: []
    expected_packs: []
    expected_tests: []
    expected_protected_result: PASS | FAIL
    labels: []
    provenance:
      source
      labeled_by
      labeled_at
```

### 경로 규칙

- absolute path, drive path, `..`, symlink escape를 거부한다.
- `graph`와 `changed_files`는 실제 regular file이어야 한다.
- Graph는 기존 `validate_project_graph()`를 통과해야 한다.
- changed-files artifact는 빈 줄을 제외한 repository-relative path 목록이다.
- case ID는 dataset 내에서 유일해야 한다.
- `(repository, source_revision)` 중복은 허용하되 case ID로 구분한다.

## 4. Policy 계약

Baseline과 Challenger는 기존 approved Rule file이다.

- `schema_version: "1.0"`
- 모든 Rule status는 `approved`
- policy identity는 canonical JSON SHA-256으로 계산한다.
- 같은 policy hash를 baseline과 challenger로 사용할 수 있으나 comparison delta는 0이어야 한다.

Stage 6은 새로운 Policy Registry를 만들지 않는다. versioned Policy 객체는 Stage 7 대상이다.

## 5. 실행 모델

각 case는 baseline과 challenger에 대해 독립적으로 다음 흐름을 거친다.

```text
Graph + changed-files + configured packs + approved rules
→ existing analyze_change()
→ normalized outcome
```

Normalized outcome:

```text
changed_scope
selected_packs
required_tests
matched_rules
protected_result
protected_reasons
outcome_sha256
```

`changed_scope`는 직접 변경 파일과 dependent file path의 합집합이다.

초기 `protected_result`는 다음 hard guard를 정규화한 값이다.

- Graph에 없는 직접 변경 파일이 있으면 `FAIL`
- Rule이 profile에 없는 pack을 요구하면 `FAIL`
- 둘 다 없으면 `PASS`

이는 security baseline 전체를 대체하지 않는다. 이후 executor가 실제 protected snapshot 결과를 제공할 수 있도록 report field를 독립적으로 유지한다.

## 6. 지표

각 policy에 대해 전체와 split별로 계산한다.

- changed scope TP / FP / FN / precision / recall
- review pack TP / FP / FN / precision / recall
- required test TP / FP / FN / precision / recall
- exact case match
- protected result accuracy
- coverage

0분모 규칙:

- precision 분모가 0이면 기대값도 0일 때 `1.0`, 아니면 `0.0`
- recall 분모가 0이면 예측값도 0일 때 `1.0`, 아니면 `0.0`

## 7. Challenger 비교와 Gate

Comparison은 baseline 대비 challenger delta를 기록한다.

```text
precision_delta
recall_delta
exact_match_delta
protected_negative_regressions
protected_positive_regressions
changed_cases
```

Protected negative regression은 다음 조건이다.

```text
expected_protected_result == PASS
AND baseline.protected_result == PASS
AND challenger.protected_result == FAIL
```

Gate 기본 조건:

- dataset, policies, outcomes 모두 schema·hash valid
- repeatability run 2회 결과 hash 동일
- challenger combined precision >= configured threshold, 기본 `1.0`
- challenger combined recall >= configured threshold, 기본 `1.0`
- protected negative regression <= configured maximum, 기본 0
- holdout split이 반드시 존재해야 하며 holdout에도 같은 조건 적용

Gate는 `PASS` 또는 `FAIL`이다. threshold는 report에 고정한다.

## 8. Report 계약

Report는 실행 시간에 의존하지 않는 deterministic JSON이다.

```text
schema_version
evaluation_id
dataset
baseline_policy
challenger_policy
thresholds
cases
metrics
comparison
gate
report_sha256
```

- `evaluation_id`는 dataset hash + baseline hash + challenger hash + evaluator contract + threshold의 digest다.
- evaluator name, contract version, PIE product version을 report에 고정한다.
- `outcome_sha256`과 `report_sha256`은 자기 hash field를 제외한 canonical JSON SHA-256이다.
- 같은 입력을 다시 실행하면 byte-equivalent JSON을 생성해야 한다.
- `verify-report`는 report hash와 내부 outcome hash를 모두 재검증한다.

## 9. Rule 승인 연결

`pie-eval attach`는 PASS report를 candidate Rule에 연결한다.

```text
evaluation:
  evaluation_id
  report
  report_sha256
  decision
  dataset_sha256
  baseline_policy_sha256
  challenger_policy_sha256
```

- candidate file write는 temp file + `os.replace`로 원자화한다.
- report가 FAIL이거나 hash가 불일치하면 attach를 거부한다.
- 기존 `approve-rule`은 evaluation 없는 candidate도 계속 승인한다.
- evaluation이 없으면 warning을 반환·출력한다.
- 후속 schema version에서만 evaluation reference를 required로 승격한다.

## 10. CLI

신규 별도 entrypoint:

```text
pie-eval validate-dataset <dataset>
pie-eval run <dataset> --baseline-policy ... --challenger-policy ... --output ...
pie-eval verify-report <report>
pie-eval attach <report> --candidates ... --rule-id ...
```

Exit contract:

- 성공: `0`
- 입력·실행 오류: `2`
- report 또는 evaluation Gate FAIL: `3`
- integrity verification 실패: `4`

기존 `pie`와 `urs` command surface는 변경하지 않는다.

## 11. 실패·원자성

- Dataset validation 실패 시 output을 생성하지 않는다.
- case 하나라도 실행 실패하면 report를 생성하지 않는다.
- report는 temporary file에 기록한 뒤 `os.replace`한다.
- attach 실패 시 candidate file 원본을 유지한다.
- repeatability mismatch는 fail-closed한다.

## 12. 테스트 매트릭스

- dataset schema와 중복 ID
- path traversal, absolute path, missing file, symlink escape
- invalid Graph와 invalid approved policy
- baseline/challenger deterministic execution
- set metric 0분모
- split metrics와 holdout Gate
- protected negative regression
- same-policy zero delta
- report and outcome tamper detection
- atomic report output failure
- PASS report attach
- FAIL/tampered report attach rejection
- approve-rule warning without evaluation
- approve-rule no warning with evaluation
- CLI exit code
- full repository regression, asset sync, wheel

## 13. Rollback

신규 module, entrypoint, tests와 문서를 제거하고 `approve-rule` warning 보완만 되돌리면 Stage 5 상태로 복귀한다. 기존 artifact, Ledger migration, Rule schema, dependency, product version은 변경하지 않는다.

## 14. 설계 리뷰

### 계약 충돌

- 기존 Rule file은 additional metadata를 허용하므로 `evaluation` 추가는 schema break가 아니다.
- evaluation 없는 승인을 막지 않아 기존 automation을 보존한다.
- `analyze_change()`를 직접 호출하므로 CLI output contract를 변경하지 않는다.

### 과설계

- remote executor, database dataset catalog, cryptographic signing, policy version registry를 제외했다.
- 첫 버전은 local immutable fixture와 deterministic hash에 집중한다.

### 무결성

- 모든 source path를 dataset root 안에 가둔다.
- dataset·policy·outcome·report hash를 계층적으로 고정한다.
- current time을 report payload에 넣지 않아 재현성을 보존한다.

### Test oracle 완전성

- 하나의 aggregate score만 사용하지 않고 scope·pack·test·protected 결과를 분리한다.
- 전체와 development·validation·holdout 지표를 모두 기록한다.
- protected negative regression은 score 상쇄를 허용하지 않는 hard Gate다.

설계 리뷰 판정: `PASS`
