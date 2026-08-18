# Stage 10F — Implementation Review

## Review target

Stage 10F Independent Audit Authority Contract의 구현이 다음 질문에 답하는지 검토했다.

> Stage 10B의 `INDEPENDENT_AUDIT` Outcome이 단순 self-assertion이 아니라 exact repository authority source replay를 통해서만 Stage 10C `RECONCILED`가 되는가?

고정 안전 경계:

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
```

## 구현 구조

새 authority plane:

- `trust_audit.py` — authority registry, root/grant/revocation, audit artifact primitives
- `trust_audit_verified.py` — assessment-capture-aware public issuance boundary
- `trust_audit_cli.py` — standalone/integrated CLI

Stage 10C extension:

- `trust_reconciliation_authority.py` — audit-aware reconciliation projection
- `trust_reconciliation_verified.py` — Stage 10F semantic verifier, temporal projection
- `trust_reconciliation_hardened.py` — normalized source-replay and atomic-write error boundary

Stage 10E composition:

- `trust_pilot_review_authority.py`
- existing pilot-review CLI routed through authority-aware reconciliation replay

## Review findings and fixes

### 1. Stage 10C legacy verifier could not represent widened audit statuses

초기 extension은 Independent Audit에 `SOURCE_MISSING`, `SOURCE_VERIFICATION_FAILED`, `OUTCOME_REFERENCE_MISMATCH` 등의 세분 상태를 추가했지만 legacy Stage 10C verifier는 audit를 사실상 `RECONCILED` 또는 `PROVENANCE_UNVERIFIED`로만 재투영했다.

위험:

- 올바른 Stage 10F fail-closed report가 verifier에서 거부될 수 있음
- 구현과 verifier의 semantic authority가 분리됨

수정:

- Stage 10F 전용 strong verifier를 추가했다.
- audit-specific base status를 full check set에서 재계산한다.
- duplicate authority, summary, overall status, evidence snapshot, report ID/hash까지 Stage 10F semantics로 재계산한다.

### 2. Legacy writer가 Stage 10F report를 다시 legacy semantics로 검증

초기 writer는 검증 후 기존 Stage 10C writer를 호출했다. 기존 writer가 다시 legacy verifier를 실행하기 때문에 widened audit status report 저장이 실패할 수 있었다.

수정:

- Stage 10F writer를 독립 atomic writer로 분리했다.
- strong verifier를 통과한 report만 temp-file + fsync + `os.replace`로 기록한다.
- replace 실패 시 기존 target bytes를 보존하고 `TrustReconciliationError`로 normalize한다.

### 3. R0 integration test가 실제로는 R2 assessment를 사용

초기 integration fixture가 `routine_code`를 사용해 Stage 10A band가 R2였다.

결과:

- audit reconciliation 자체는 `RECONCILED`
- Stage 10E의 `verified_r0_independent_audit_assessment_count`는 올바르게 0

이것은 코어 결함이 아니라 fixture 오류였다.

수정:

- integration fixture를 `generated_artifact`로 변경해 실제 R0 assessment를 사용한다.

### 4. audit issuance가 assessment capture 이전으로 backdate될 수 있었음

Trust Root와 Grant validity만 검증하면 grant가 존재하는 시점에 아직 capture되지 않은 assessment를 대상으로 과거 `issued_at`을 선언하는 경로가 남을 수 있었다.

수정:

public issuance boundary:

```text
audit.issued_at >= assessment.captured_at
```

Stage 10C reconciliation boundary에서도 동일 조건을 별도 check로 재검증한다.

```text
issued_after_assessment
```

따라서 lower-level artifact를 직접 구성해도 reconciliation에서는 fail closed한다.

### 5. source replay와 writer에서 broad exception contract가 남음

초기 hardening verifier가 source replay에 `except Exception`을 사용하고 writer도 raw exception을 재전파했다.

위험:

- CLI error contract 외부로 예상치 못한 implementation exception이 노출될 가능성
- write failure normalization 불일치

수정:

- known Trust/Audit/Comparison/input exception만 source-replay failure로 normalize한다.
- atomic replace `OSError`는 `TrustReconciliationError`로 normalize한다.

### 6. audit semantic rehash escalation

외부 source replay 없이 report 내부의 `independent_provenance_verified=true`만 바꾸고 outer hash를 다시 계산하는 공격을 고려했다.

수정:

`independent_provenance_verified`를 다음 full conjunction에서 재계산한다.

```text
authority_source_declared
source_present
artifact_valid
authority_registry_valid
project_match
assessment_match
trust_report_match
revision_match
outcome_reference_match
issuer_match
issued_after_assessment
issued_before_outcome
verdict_match
authority_binding_valid
```

또한 verified authority projection에서:

- audit ID
- artifact SHA
- issuer ID
- Grant ID
- Trust Root ID
- authority key
- conclusive evidence ref count

를 다시 검증한다.

최종적으로 실제 truth authority는 exact source replay다. self-contained report verifier는 projection tamper를 막고, source replay는 source truth를 검증한다.

### 7. 동일 audit artifact 재사용에 의한 denominator inflation

Stage 10D는 distinct R0 assessment 기준 audit coverage를 사용하지만 동일 artifact를 여러 conclusive Outcome에 재사용하면 Outcome 수가 증가할 수 있다.

수정:

Independent Audit authority key:

```text
audit:<artifact_sha256>
```

기존 Stage 10C duplicate-authority logic을 그대로 적용해 재사용된 conclusive authority를 `DUPLICATE_AUTHORITY`로 만든다.

### 8. exact Outcome reference가 audit ID 또는 SHA 하나만으로도 충분한지 검토

하나만 요구하면 다른 artifact로 identity ambiguity가 생길 수 있다.

수정:

Outcome evidence refs에 다음 두 값이 **모두** 있어야 한다.

```text
audit_id
artifact_sha256
```

### 9. issuer identity 바꿔치기

artifact가 valid grant를 참조하더라도 Stage 10B Outcome actor가 다른 사람일 수 있다.

수정:

```text
Outcome.actor == artifact.issuer_subject
```

및 exact issuer/grant/root binding을 함께 요구한다.

### 10. future evidence backfill

audit artifact가 Outcome 이후 생성되었는데 과거 Outcome authority로 사용되는 경우를 검토했다.

수정:

```text
audit.issued_at <= outcome.occurred_at
```

을 hard check로 유지한다.

### 11. retroactive revocation

issuer compromise가 나중에 발견되어 과거 grant까지 무효화해야 할 수 있다.

구현:

- `retroactive=true` revocation을 명시적으로 허용
- `effective_at` 이전 audit만 유효
- exact replay 시 현재 authority registry의 revocation semantics를 적용

따라서 과거에 reconcile됐던 report도 authority registry 변경 후 source replay에서 stale/invalid가 된다.

## Deliberately preserved limitations

### Repository-backed provenance, not external cryptographic provenance

Trust Root `fingerprint`는 repository metadata다. 외부 PKI signature 또는 hardware-backed key proof가 아니다.

### Internally ordered timestamps, not externally signed timestamps

Stage 10F는 timestamp 사이의 순서를 검증하지만 RFC 3161 TSA 같은 외부 timestamp authority를 사용하지 않는다.

### Evidence refs are attestations

arbitrary external evidence ref의 내용 자체를 Stage 10F가 fetch/verify하지 않는다.

### Root-wide revocation is not a separate object

현재 revocation unit은 Issuer Grant다. 하나의 Trust Root 아래 모든 grant를 폐기하려면 각 grant를 revoke해야 한다. dedicated root revocation은 후속 hardening 후보다.

## Safety authority conclusion

Stage 10F 구현은 Independent Audit를 단순 event count에서 repository-backed replayable authority로 승격시키는 데 필요한 최소 계약을 제공한다.

그러나 다음은 여전히 금지된다.

```text
automatic pilot activation
GitHub auto approval
auto merge
auto label/comment
pilot_authorized=true
automation_authorized=true
```

Stage 10F PASS는 audit provenance path의 구현 PASS이며 실제 pilot eligibility 또는 activation PASS가 아니다.
