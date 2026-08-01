# PIE Stage 10B — Decision Comparison & Outcome Audit Foundation

기준일: 2026-08-02  
선행 기준선: PR #18 HEAD `4f2fc0610213d01bc3471f67283d721b44922f0b`  
작업 브랜치: `agent/stage-10b-decision-outcome-audit`  
상태: `DESIGN_REVIEW_PASS`

## 1. 목적

Stage 10A의 report-only Trust 판단을 사람의 실제 검수 결정 및 사후 Outcome과 연결한다.

이번 단계는 자동 승인 정확도를 주장하지 않는다. 다음 두 통계를 분리한다.

1. **Reviewer alignment** — PIE와 사람이 같은 결론을 냈는가.
2. **Confirmed outcome accuracy** — 독립 Audit, 실제 Defect, Regression, Security Incident 또는 Controlled Evaluation로 정답이 확인된 사례에서 PIE가 맞았는가.

## 2. 사람 판단의 의미

다음 세 수준을 엄격히 구분한다.

- `WORKFLOW_ACCEPTED`: 결과를 받아 다음 작업으로 이동했다. 안전 검수로 간주하지 않는다.
- `REVIEWED`: diff와 검증 근거를 실제로 확인하고 승인·수정 요청·보류·거절·재분류를 명시했다.
- `AUDITED`: 최초 검수와 분리된 심층 재검사를 완료했다.

`진행`, `다음 작업`, PR 생성·CI 통과 또는 단순 Workflow 수락은 자동으로 `REVIEWED`나 `AUDITED`가 되지 않는다.

## 3. 권위 모델

파일 기반 `trust-comparison-registry.json`을 최초 권위 원본으로 둔다.

- `assessments`: 검수 전에 고정된 Stage 10A Trust report reference.
- `events`: append-only human decision 및 Outcome event hash chain.
- `comparisons`: assessment와 최신 유효 decision·Outcome에서 재계산되는 projection.
- `metrics`: 잠정 alignment와 confirmed outcome 지표를 분리한 projection.

Ledger migration은 만들지 않는다. Registry가 안정된 뒤 별도 Stage에서 Ledger projection 여부를 검토한다.

## 4. Assessment identity

자연키:

```text
project_id + task_id + source_revision + trust_report_id + trust_report_sha256
```

동일 자연키의 재수집은 idempotent하다. 같은 PR이라도 source revision이 바뀌면 새로운 assessment다.

Assessment에는 다음만 보존한다.

- Trust report ID·SHA-256
- task ID·source revision
- predicted risk band
- readiness status
- triggered hard gates
- report-only·automation prohibited 상태

Trust report 원문은 중복 저장하지 않는다.

## 5. Event contract

### Human decision

- `decision`: `APPROVE`, `REQUEST_CHANGES`, `HOLD`, `REJECT`, `RECLASSIFY`
- `review_level`: `WORKFLOW_ACCEPTED`, `REVIEWED`, `AUDITED`
- `confirmed_risk_band`: `R0`~`R4` 또는 null
- reason code 목록
- actor·timestamp

`WORKFLOW_ACCEPTED`는 reviewer alignment의 안전 정답으로 사용하지 않는다.

### Outcome

- `outcome_type`: `INDEPENDENT_AUDIT`, `PRODUCTION_DEFECT`, `REGRESSION`, `SECURITY_INCIDENT`, `CONTROLLED_EVALUATION`, `FALSE_POSITIVE_REVIEW`
- `verdict`: `SAFE`, `UNSAFE`, `INCONCLUSIVE`
- actor·timestamp
- 선택적 Defect ID 및 evidence references

`INDEPENDENT_AUDIT`는 해당 assessment의 최초 `REVIEWED` decision actor와 같은 actor가 확정하면 independent outcome으로 인정하지 않는다.

모든 event는 이전 event hash를 포함하는 global append-only hash chain을 구성한다.

## 6. 비교 상태

사람 decision만 있는 경우:

- `UNREVIEWED`: decision 없음 또는 `WORKFLOW_ACCEPTED`뿐임.
- `PROVISIONAL_MATCH`
- `PROVISIONAL_OVER_ESTIMATE`
- `PROVISIONAL_UNDER_ESTIMATE`
- `PROVISIONAL_DECISION_MISMATCH`
- `UNCOMPARABLE`

확정 Outcome이 있는 경우:

- `CONFIRMED_TRUE_NEGATIVE`
- `CONFIRMED_FALSE_NEGATIVE`
- `CONFIRMED_TRUE_POSITIVE`
- `CONFIRMED_FALSE_POSITIVE`
- `CONFIRMED_INCONCLUSIVE`

Stage 10A 결과는 자동 승인 후보가 아니므로 predicted safe/risky는 보수적으로 다음처럼 해석한다.

- predicted safe candidate: `R0` 또는 `R1`이며 triggered hard gate가 없음.
- predicted risky: 그 외 모든 경우.

## 7. 지표

### 잠정 지표

분모는 `REVIEWED` 또는 `AUDITED` decision이 존재하는 비교 가능 assessment다.

- reviewed assessment count
- reviewer alignment count/rate
- over-estimate count
- under-estimate count
- decision mismatch count
- risk-band confusion matrix

### 확정 지표

분모는 conclusive `SAFE` 또는 `UNSAFE` Outcome이 존재하는 assessment만 포함한다.

- TP, FP, TN, FN
- precision, recall, false-positive rate, false-negative rate, accuracy
- R0~R4별 confirmed counts

분모가 0인 비율은 `null`이다. Outcome 없는 사례는 안전으로 간주하지 않는다.

### 성숙도

- assessment count
- workflow-accepted count
- reviewed count
- audited count
- conclusive outcome count
- outcome coverage
- independent audit count
- observed false-negative count

## 8. Audit sampling

`sample-audit`는 아직 정답을 만들지 않는다. Audit 후보 목록만 결정적으로 생성한다.

우선순위:

1. R0/R1 predicted safe candidate
2. `WORKFLOW_ACCEPTED`만 있고 실제 review가 없는 작업
3. 사람이 PIE보다 낮은 risk band를 확정한 작업
4. 오래된 미확정 assessment
5. 나머지 무작위 표본

동일 registry와 seed는 동일 sample을 생성한다.

## 9. 검증 및 안전성

- Trust report는 기존 Stage 10A verifier로 검증 후 캡처한다.
- `automation_authorized=false`, `mode=REPORT_ONLY`, `maximum_automation_band=NONE`이 아니면 거부한다.
- symbolic source revision, report hash mismatch, duplicate natural key conflict를 거부한다.
- event timestamp는 assessment capture 이후여야 한다.
- event ID·hash chain·projection·metrics·registry hash를 재계산한다.
- symlink input/output, path traversal, partial write를 거부한다.
- atomic temp+fsync+replace를 사용한다.
- self-contained verification과 optional Trust report replay를 분리한다.

## 10. CLI

```text
pie-trust init-comparison-registry
pie-trust capture-assessment
pie-trust record-decision
pie-trust record-outcome
pie-trust sample-audit
pie-trust comparison-metrics
pie-trust verify-comparison-registry
```

기존 `pie`·`urs`에는 additive alias만 연결한다. 기존 Trust assess, Gate, Ledger, Defect, Evaluation, Policy, Reground, BuildMap 의미와 exit contract는 변경하지 않는다.

## 11. 비대상

- R0 auto-pass
- R1 conditional auto-approval
- GitHub approve·merge·label·comment·branch write
- 사람 decision 자동 추론
- `진행` 또는 Workflow 수락의 안전 검수 승격
- Outcome 없는 사례를 SAFE로 간주
- 조직 단위 중앙 Trust service
- cryptographic signer identity
- Ledger migration

## 12. 완료 기준

- 동일 Trust report capture가 idempotent하다.
- source revision이 바뀌면 별도 assessment가 생성된다.
- `WORKFLOW_ACCEPTED`가 reviewer alignment 분모에 들어가지 않는다.
- 사람 decision과 Outcome이 append-only hash chain으로 보존된다.
- independent Audit actor 제약이 적용된다.
- provisional alignment와 confirmed outcome metrics가 분리된다.
- 분모 0 지표가 null이다.
- confirmed false negative를 실제 Outcome으로만 계산한다.
- deterministic Audit sample을 생성한다.
- tamper·reorder·rehash·dangling reference·symlink·atomic write failure를 fail closed 처리한다.
- Python 3.11·3.13·3.14 전체 회귀와 wheel build가 통과한다.
