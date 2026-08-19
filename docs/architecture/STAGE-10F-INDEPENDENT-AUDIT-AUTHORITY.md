# Stage 10F — Independent Audit Authority Contract

## 목적

Stage 10F는 Stage 10C가 `INDEPENDENT_AUDIT` Outcome의 provenance를 실제 repository source에서 replay하고 검증할 수 있는 authority contract를 추가한다.

이 단계의 목적은 pilot을 활성화하는 것이 아니다. Stage 10E가 요구하는 `verified R0 Independent Audit` evidence를 만들 수 있는 최소 authority plane을 제공하는 것이다.

고정 경계:

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
```

## 배경

Stage 10D observation policy는 R0 pilot review 전에 distinct R0 assessment 기준 Independent Audit coverage를 요구한다.

Stage 10C의 기존 계약은 별도 audit authority source가 없었기 때문에 모든 `INDEPENDENT_AUDIT` Outcome을 다음과 같이 처리했다.

```text
PROVENANCE_UNVERIFIED
reconciled=false
```

Stage 10E는 이 상태를 의도적으로 hard blocker로 취급한다. Stage 10F는 이 blocker를 완화하는 것이 아니라, provenance를 검증할 수 있는 별도 source contract를 추가한다.

## Authority chain

```text
Trust Root
   ↓
Issuer Grant
   ↓
Independent Audit Artifact
   ↓
Stage 10B Outcome
   ↓
Stage 10C source replay
   ↓
RECONCILED | fail-closed status
```

### 1. Trust Root

Trust Root는 repository가 신뢰하는 audit issuer namespace를 정의한다.

주요 필드:

- `trust_root_id`
- `identity_kind`
- `subject`
- `fingerprint`
- `registered_at`
- `valid_from`
- `valid_until`
- `trust_root_sha256`

`valid_from < registered_at`는 허용하지 않는다.

### 2. Issuer Grant

Issuer Grant는 특정 issuer가 특정 Trust Root 아래에서 audit artifact를 발행할 수 있는 기간을 정의한다.

주요 필드:

- `grant_id`
- `issuer_id`
- `issuer_subject`
- exact `trust_root_id`
- exact `trust_root_sha256`
- `granted_at`
- `valid_from`
- `valid_until`
- `grant_sha256`

`valid_from < granted_at`는 허용하지 않는다.

### 3. Revocation

Issuer Grant는 explicit revocation record로 폐기할 수 있다.

- `effective_at`
- `recorded_at`
- `retroactive`
- `reason_codes`
- `revocation_sha256`

`retroactive=false`인 revocation은 `effective_at < recorded_at`를 허용하지 않는다.

`retroactive=true`이면 과거 발행 audit의 authority가 사후 무효화될 수 있으며, Stage 10C exact replay에서 다시 fail closed한다.

### 4. Independent Audit Artifact

Audit artifact는 다음 authority와 assessment evidence를 하나의 deterministic identity로 묶는다.

- `project_id`
- `assessment_id`
- `trust_report_id`
- `trust_report_sha256`
- `source_revision`
- `issuer_id`
- `issuer_subject`
- authority registry ID
- exact Trust Root ID/SHA
- exact Grant ID/SHA
- `verdict`
- `issued_at`
- `evidence_refs`
- fixed REPORT_ONLY flags
- `artifact_sha256`

Conclusive `SAFE` 또는 `UNSAFE` audit는 최소 하나의 evidence ref를 요구한다.

## Temporal contract

Stage 10F는 다음 시간 순서를 요구한다.

```text
registry.created_at
  <= trust_root.registered_at
  <= trust_root.valid_from

trust_root valid interval
  contains grant.valid_from / valid_until

grant.granted_at
  <= grant.valid_from

assessment.captured_at
  <= audit.issued_at
  <= outcome.occurred_at
```

또한 `audit.issued_at` 시점에 Trust Root와 Issuer Grant가 모두 유효해야 한다.

따라서 나중에 생성한 audit artifact로 과거 Outcome을 backfill하거나, assessment가 존재하기 전의 audit를 소급 생성해서 authority로 사용할 수 없다.

## Outcome binding

Stage 10C에서 Independent Audit가 `RECONCILED`되려면 다음이 모두 참이어야 한다.

1. assessment 자체가 Stage 10A source replay를 통과했다.
2. source manifest가 audit artifact와 authority registry를 명시한다.
3. 두 source가 존재하고 schema/semantic verification을 통과한다.
4. project가 일치한다.
5. artifact assessment ID가 Outcome 및 Stage 10B assessment와 일치한다.
6. Trust report ID/SHA가 일치한다.
7. source revision이 일치한다.
8. Outcome `evidence_refs`에 `audit_id`와 `artifact_sha256`가 모두 존재한다.
9. Outcome actor가 authorized issuer subject와 일치한다.
10. audit가 assessment capture 이후 발행됐다.
11. audit가 Outcome보다 늦게 발행되지 않았다.
12. audit verdict가 Outcome verdict와 일치한다.
13. exact root/grant hash binding이 유효하다.
14. audit 발행 시점에 grant가 유효하고 revocation에 의해 무효화되지 않았다.

하나라도 실패하면 `RECONCILED`가 아니다.

## Failure statuses

```text
no audit source mapping
  -> PROVENANCE_UNVERIFIED

mapping exists but file missing
  -> SOURCE_MISSING

invalid artifact / authority registry
  -> SOURCE_VERIFICATION_FAILED

project mismatch
  -> PROJECT_MISMATCH

assessment / evidence reference mismatch
  -> OUTCOME_REFERENCE_MISMATCH

Trust report hash mismatch
  -> SOURCE_HASH_MISMATCH

source revision mismatch
  -> REVISION_MISMATCH

verdict mismatch
  -> OUTCOME_VERDICT_MISMATCH

issuer / temporal / authority binding failure
  -> PROVENANCE_UNVERIFIED

all checks pass
  -> RECONCILED
```

## Duplicate authority

Conclusive Independent Audit authority key:

```text
audit:<artifact_sha256>
```

동일 audit artifact를 둘 이상의 conclusive Outcome에 재사용하면 Stage 10C의 기존 duplicate-authority protection을 통해 해당 Outcome들이 `DUPLICATE_AUTHORITY`가 된다.

따라서 event 수를 늘려 Stage 10D/10E audit denominator를 부풀릴 수 없다.

## Stage 10E 연결

Stage 10E는 Stage 10F-aware Stage 10C exact replay 결과에서 실제 `reconciled=true`인 Independent Audit만 distinct R0 assessment 기준으로 계산한다.

```text
verified_r0_independent_audit_assessment_count
```

이 값이 Stage 10D policy threshold를 만족해야만 Stage 10E의 다음 check를 통과할 수 있다.

```text
NO_CONCLUSIVE_PROVENANCE_UNVERIFIED
VERIFIED_R0_INDEPENDENT_AUDIT_THRESHOLD
```

그러나 모든 gate가 통과해도 결과는 최대 다음 상태다.

```text
ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

이는 pilot 권한이 아니다.

## CLI

Standalone:

```text
pie-trust-audit new-audit-authority
pie-trust-audit add-audit-trust-root
pie-trust-audit authorize-audit-issuer
pie-trust-audit revoke-audit-issuer
pie-trust-audit issue-independent-audit
pie-trust-audit verify-audit-authority
pie-trust-audit verify-independent-audit
```

동일 command는 `pie-trust` subcommand로도 제공된다.

Stage 10C/10E 기존 CLI는 Stage 10F authority-aware replay layer로 라우팅된다.

## 명시적 비목표와 신뢰 모델 한계

### 외부 PKI가 아니다

`fingerprint`는 repository-governed provenance metadata다. Stage 10F는 이를 X.509, WebPKI, hardware key, externally verified digital signature로 검증하지 않는다.

따라서 Stage 10F는 cryptographic non-repudiation을 주장하지 않는다.

### 외부 trusted timestamp가 아니다

`created_at`, `registered_at`, `granted_at`, `issued_at`, `recorded_at`은 artifact 내부 시간이다. Stage 10F는 이들의 상호 순서와 hash binding을 검증하지만 외부 timestamp authority에 의해 서명된 시간은 아니다.

repository history와 authority file 전체를 rewrite할 수 있는 공격자가 완전히 새 hash chain을 만든 경우를 외부적으로 증명하는 단계는 아니다.

### evidence ref content validator가 아니다

Audit artifact의 `evidence_refs`는 issuer가 audit 근거로 attestation한 reference다. Stage 10F는 ref의 존재·binding을 artifact identity에 포함하지만 arbitrary external ref 내용을 별도로 fetch하거나 의미적으로 검증하지 않는다.

### pilot activation이 아니다

Stage 10F는 GitHub approval, merge, label, comment, branch write, pilot activation, 자동 PASS를 수행하지 않는다.

## 다음 경계

Stage 10F가 검증된 audit provenance 경로를 제공한 뒤에도 실제 pilot activation은 별도 계약이어야 한다.

후속 후보:

```text
R0 Pilot Activation Contract
```

단, activation contract를 적용하기 전에 실제 Stage 10E evidence package가 `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW`에 도달하는지 exact source replay로 확인해야 한다.
