# Stage 10E — Implementation Review

## Review scope

Stage 10E R0 Pilot Safety Review 구현을 다음 관점에서 재검토했다.

- authority composition
- fail-closed semantics
- denominator consistency
- stale/source mutation resistance
- semantic rehash resistance
- authorization boundary
- path/output hardening

## Finding 1 — Independent Audit authority gap is a structural blocker

### 발견

Stage 10D policy schema는 `minimum_r0_independent_audit_count >= 1`을 요구한다.

Stage 10C report schema는 현재 모든 `INDEPENDENT_AUDIT` Outcome을 `PROVENANCE_UNVERIFIED`, `reconciled=false`로 고정한다.

따라서 현 upstream contract만으로는 다음 두 조건을 동시에 만족할 수 없다.

```text
Stage 10D thresholds satisfied
Stage 10C all conclusive Outcomes reconciled
```

### 조치

Stage 10E는 audit evidence를 암묵적으로 신뢰하지 않는다.

다음을 별도 check로 고정했다.

```text
NO_CONCLUSIVE_PROVENANCE_UNVERIFIED
VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD
```

실패 시 next step:

```text
ESTABLISH_INDEPENDENT_AUDIT_AUTHORITY
```

### 결과

현재 contract에서 실제 R0 pilot eligibility가 잘못 열리지 않는다.

---

## Finding 2 — Source replay failure must outrank downstream evidence blockers

### 초기 구현

source replay와 audit provenance가 동시에 실패하면 audit authority 보완을 먼저 지시했다.

### 위험

source가 실제 authority와 일치하는지 검증되지 않은 상태에서 downstream blocker를 진단하면 stale/mutated evidence에 근거한 잘못된 remediation을 제시할 수 있다.

### 수정

next-step 우선순위를 다음으로 변경했다.

1. project/registry/source replay repair
2. independent audit authority
3. observation safety blocker
4. reconciliation blocker
5. generic blocker

즉 source authority가 불확실하면 항상:

```text
REPAIR_AND_REPLAY_SOURCE_EVIDENCE
```

가 우선한다.

---

## Finding 3 — Reconciliation completeness needed explicit assessment projection

### 초기 구현

`RECONCILIATION_COMPLETE`는 Stage 10C의:

```text
source_reconciliation_complete=true
status=RECONCILED
```

만 확인했다.

### 수정

방어 심층화를 위해 다음도 직접 요구한다.

```text
assessment_unreconciled_count == 0
```

Stage 10C semantic verifier와 source replay가 이미 이 관계를 보호하지만, Stage 10E 자체 check도 같은 의미를 명시한다.

---

## Finding 4 — Independent Audit denominator must remain assessment-based

Stage 10D는 반복 audit event 수를 세지 않고 distinct R0 assessment 수를 센다.

Stage 10E는 Registry에서 같은 projection을 다시 계산하고 다음을 비교한다.

```text
observation.r0_independent_audit_count
registry distinct R0 audited assessment count
```

검증된 audit도 distinct assessment 기준으로 계산한다.

따라서 repeated audit event로 coverage threshold를 부풀릴 수 없다.

---

## Finding 5 — Stage 10D pass alone must not weaken zero-tolerance

Stage 10E는 Stage 10D status만 확인하지 않고 독립적으로 다음을 재고정한다.

```text
r0_false_negative == 0
r0_false_negative_rate == 0
confirmed_unsafe_challenge_count > 0
```

향후 observation policy가 변경되어도 이 Stage의 pilot safety boundary는 자동 완화되지 않는다.

---

## Finding 6 — Cross-plane registry identity cannot be inferred from filenames

Stage 10C와 Stage 10D가 같은 파일 이름을 사용한다는 사실은 authority가 아니다.

Stage 10E는 다음 semantic identity를 모두 비교한다.

```text
project_id
registry_id
registry_sha256
```

그리고 양 report를 같은 실제 Stage 10B Registry에 대해 source replay한다.

---

## Finding 7 — Stage 10A is transitively replayed, not independently re-read

Stage 10E가 Stage 10A Trust report를 직접 추가 입력으로 받지는 않는다.

그 대신 Stage 10C가 각 Stage 10B assessment에 대해 Stage 10A Trust report와 원본 request/profile/evidence를 replay한다. Stage 10E는 Stage 10C exact source replay를 다시 요구한다.

따라서 Stage 10A authority는 다음 체인을 통해 포함된다.

```text
Stage 10A Trust source
  -> Stage 10B assessment
  -> Stage 10C exact replay/reconciliation
  -> Stage 10E safety review
```

Stage 10E에서 Stage 10A를 별도로 다시 전달받는 중복 경로는 추가하지 않았다.

---

## Finding 8 — Semantic rehash cannot flip NOT_ELIGIBLE to eligible

Report verifier는 다음을 모두 재계산한다.

- fixed 15-check set
- check booleans
- blockers
- status
- next step
- evidence snapshot hash
- review ID
- report hash

테스트에서 blocked report의 status/blockers/next_step을 eligibility 상태로 바꾸고 모든 hash를 다시 계산해도 projection mismatch로 거부됨을 고정했다.

---

## Finding 9 — Time cannot manufacture evidence identity

`generated_at`은 evidence snapshot에서 제외했다.

같은 source evidence에서 생성 시각만 변경하면:

```text
evidence_snapshot_sha256 unchanged
review_id unchanged
report_sha256 changed
```

이다.

Stage 10D에서 이미 evidence span이 source timestamp로 계산되므로 Stage 10E generation time은 observation maturity를 늘릴 수 없다.

---

## Finding 10 — Output mutation hardening

Stage 10E output은:

- output path symlink 거부
- parent traversal의 symlink 거부
- temporary file + fsync + `os.replace`
- replace 실패 시 기존 target bytes 보존

을 테스트한다.

---

## Remaining limitation 1 — Detached verification is not source freshness proof

`verify_pilot_review_report_data(...)`는 report 내부 semantic integrity를 검증한다.

원본 Registry/Stage 10C sources/Stage 10D policy가 이후 변경되지 않았다는 사실은 detached report만으로 증명할 수 없다.

Pilot authorization 전에는 반드시:

```text
verify_pilot_review_report_sources(...)
```

로 exact source replay를 다시 수행해야 한다.

---

## Remaining limitation 2 — No Independent Audit authority contract

현재 가장 중요한 미해결 prerequisite다.

필요한 것은 단순 `reviewer` 문자열이 아니라 repository-backed provenance contract다. 최소한 다음 질문을 해결해야 한다.

- audit artifact의 canonical identity는 무엇인가
- 누가 audit를 발행할 권한이 있는가
- audit가 어떤 exact assessment/source revision을 검증했는가
- audit 발행 시각과 이후 수정/철회를 어떻게 증명하는가
- 동일 audit authority 재사용을 어떻게 차단하는가
- signer/issuer identity를 어떤 trust root에 묶는가

이 authority가 생기기 전까지 Stage 10E는 pilot eligibility를 열어서는 안 된다.

---

## Authorization conclusion

Stage 10E implementation은 어떤 code path에서도 다음 값을 변경하지 않는다.

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
```

`ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW`조차 pilot activation이 아니다.

실제 activation은 별도 명시적 사람 승인과 별도 activation contract 이후에만 가능하다.
