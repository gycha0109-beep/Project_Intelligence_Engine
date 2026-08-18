# Stage 10E — R0 Pilot Safety Review

## 1. 목적

Stage 10E는 Stage 10B/10C/10D의 evidence plane을 처음으로 하나의 R0 pilot eligibility 판단에 결합한다.

이 단계는 pilot을 활성화하지 않는다. 출력은 오직 다음 둘 중 하나다.

```text
NOT_ELIGIBLE
ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

두 번째 상태도 실행 권한이 아니다. 명시적 사람 승인을 요청할 수 있는 evidence 상태일 뿐이다.

고정 안전 경계:

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
target_band=R0
```

## 2. 입력 권위

Stage 10E는 다음 다섯 입력을 동시에 요구한다.

1. Stage 10B Trust Comparison Registry
2. Stage 10C reconciliation report
3. Stage 10C reconciliation source manifest
4. Stage 10D observation report
5. Stage 10D observation policy

Stage 10C와 Stage 10D report의 내부 hash만 비교하는 것으로 충분하지 않다. 두 report 모두 같은 Stage 10B registry를 기준으로 exact source replay되어야 한다.

## 3. Cross-plane identity 계약

다음 값은 모두 일치해야 한다.

```text
registry.project_id
reconciliation.project_id
observation.project_id

registry.registry_id
reconciliation.comparison_registry.registry_id
observation.registry.registry_id

registry.registry_sha256
reconciliation.comparison_registry.registry_sha256
observation.registry.registry_sha256
```

하나라도 다르면 `REGISTRY_IDENTITY_MATCH` 또는 `PROJECT_ID_MATCH`가 실패한다.

## 4. Source replay 계약

Stage 10E는 기존 public verifier를 재사용한다.

- Stage 10C: `verify_reconciliation_report_sources(...)`
- Stage 10D: `verify_report_sources(...)`

따라서 stale report, source mutation, 다른 manifest/policy를 이용한 replay는 eligibility를 만들 수 없다.

## 5. Pilot safety checks

고정 check set:

1. `PROJECT_ID_MATCH`
2. `REGISTRY_IDENTITY_MATCH`
3. `RECONCILIATION_SOURCE_REPLAY`
4. `OBSERVATION_SOURCE_REPLAY`
5. `RECONCILIATION_COMPLETE`
6. `NO_CONCLUSIVE_UNRECONCILED_OUTCOMES`
7. `NO_CONCLUSIVE_DUPLICATE_AUTHORITY`
8. `NO_CONCLUSIVE_UNSUPPORTED_SOURCE`
9. `NO_CONCLUSIVE_PROVENANCE_UNVERIFIED`
10. `OBSERVATION_THRESHOLDS_SATISFIED`
11. `R0_FALSE_NEGATIVES_ZERO`
12. `R0_FALSE_NEGATIVE_RATE_ZERO`
13. `UNSAFE_CHALLENGE_EVIDENCE_PRESENT`
14. `R0_AUDIT_COUNT_PROJECTION_MATCH`
15. `VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD`

모든 check가 true일 때만 `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW`가 가능하다.

## 6. Independent Audit structural blocker

Stage 10E 설계 리뷰에서 현재 upstream contract 사이의 구조적 충돌을 확인했다.

Stage 10D observation policy schema는:

```text
minimum_r0_independent_audit_count >= 1
```

을 요구한다.

반면 Stage 10C는 repository-backed Independent Audit authority contract가 없기 때문에 모든 `INDEPENDENT_AUDIT` Outcome을:

```text
base_status=PROVENANCE_UNVERIFIED
status=PROVENANCE_UNVERIFIED
reconciled=false
checks.independent_provenance_verified=false
```

로 고정한다.

따라서 현재 upstream contract만으로는 유효한 Stage 10D threshold pass와 완전한 Stage 10C conclusive reconciliation을 동시에 만족시킬 수 없다.

Stage 10E는 이 모순을 완화하거나 audit evidence를 임의 신뢰하지 않는다. 다음 두 check로 명시적으로 차단한다.

```text
NO_CONCLUSIVE_PROVENANCE_UNVERIFIED
VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD
```

둘 중 하나라도 실패하면 우선 next step은:

```text
ESTABLISH_INDEPENDENT_AUDIT_AUTHORITY
```

이다.

## 7. Audit denominator 보존

Stage 10D는 independent audit coverage를 event 수가 아니라 distinct R0 assessment 수로 계산한다.

Stage 10E도 같은 의미를 보존한다.

- raw count: Stage 10B Registry에서 R0 + conclusive `INDEPENDENT_AUDIT`가 존재하는 distinct assessment 수
- verified count: 위 assessment 중 Stage 10C에서 실제 `reconciled=true`인 audit authority를 가진 distinct assessment 수

두 raw projection은 일치해야 하고, verified count가 Stage 10D policy threshold 이상이어야 한다.

반복 audit event로 denominator를 부풀릴 수 없다.

## 8. Observation safety boundary

Stage 10D status가 다음이어야 한다.

```text
THRESHOLDS_SATISFIED_AWAITING_SOURCE_RECONCILIATION
```

또한 Stage 10E는 별도로 다음을 다시 고정한다.

```text
r0_false_negative == 0
r0_false_negative_rate == 0
confirmed_unsafe_challenge_count > 0
```

따라서 향후 Stage 10D policy가 변경되더라도 Stage 10E 자체가 R0 confirmed false negative를 허용하지 않는다.

## 9. Reconciliation safety boundary

Stage 10E는 Stage 10C summary만 신뢰하지 않고 `outcome_reconciliation[]`에서 conclusive 상태를 다시 projection한다.

차단 대상:

- unreconciled conclusive Outcome
- duplicate conclusive authority
- unsupported conclusive source
- provenance-unverified conclusive source

Stage 10C exact source replay까지 통과해야 하므로 report 내부 값을 재해시한 것만으로는 이 경계를 우회할 수 없다.

## 10. Report identity

Stage 10E report는 다음을 가진다.

```text
review_id
evidence_snapshot_sha256
report_sha256
```

`generated_at`은 evidence snapshot에서 제외된다.

따라서 같은 evidence에 대해 generation time만 바뀌면:

```text
evidence_snapshot_sha256 = 동일
review_id = 동일
report_sha256 = 변경
```

이 된다.

## 11. Semantic self-verification

`verify_pilot_review_report_data(...)`는 다음을 재계산한다.

- 15개 check projection
- blocker set
- status
- next step
- evidence snapshot hash
- review ID
- outer report hash

따라서 `NOT_ELIGIBLE` report를 `ELIGIBLE...`로 바꾸고 모든 hash를 다시 계산해도 semantic projection mismatch로 거부된다.

JSON Schema는 추가로 다음을 상수로 고정한다.

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
target_band=R0
```

## 12. CLI

독립 entry point:

```text
pie-trust-pilot-review review-r0-pilot
pie-trust-pilot-review verify-r0-pilot-review
```

통합 entry point:

```text
pie-trust review-r0-pilot
pie-trust verify-r0-pilot-review
```

Review 생성은 source replay에 필요한 다섯 source를 모두 요구한다.

Report 검증은 detached semantic verification을 지원하지만, 실제 pilot authorization 판단 전에는 exact source replay 검증을 다시 수행해야 한다.

## 13. 현재 단계 결론

Stage 10E 구현 자체는 R0 pilot eligibility gate를 제공한다.

그러나 현재 Stage 10C/10D authority contract 조합에서는 Independent Audit provenance가 해결되기 전까지 실제 evidence가 `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW`에 도달해서는 안 된다.

따라서 Stage 10E PASS는 pilot PASS가 아니다.

다음 prerequisite는 별도 `Independent Audit Authority Contract` 단계다.
