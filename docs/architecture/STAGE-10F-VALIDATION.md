# Stage 10F — Validation

## Validation objective

Stage 10F 검증은 다음을 증명하는 데 초점을 둔다.

1. Independent Audit authority identity가 deterministic하고 self-verifiable하다.
2. audit artifact가 exact Stage 10B assessment/Trust report/revision/issuer authority에 묶인다.
3. Stage 10C는 source replay 없이 Independent Audit를 `RECONCILED`로 만들지 않는다.
4. source mutation, temporal backfill, duplicate authority, semantic rehash가 fail closed한다.
5. Stage 10E가 verified Independent Audit를 distinct R0 assessment 기준으로 사용할 수 있다.
6. pilot/automation authority는 계속 false다.
7. 기존 PIE regression과 package build가 유지된다.

## Focused authority validation

`tests/test_trust_audit_authority.py`

검증 범위:

- authority registry deterministic identity/hash
- Trust Root registration/validity ordering
- issuer grant anti-backdating
- non-retroactive revocation ordering
- active grant audit issuance
- conclusive audit evidence requirement
- artifact mutation detection
- authority registry mutation detection
- retroactive revocation invalidation
- output symlink rejection

## Temporal and replay hardening

`tests/test_trust_audit_hardening.py`

검증 범위:

- `issued_at < assessment.captured_at` public issuance rejection
- assessment capture boundary issuance acceptance
- audit artifact mutation after report generation causes exact replay failure
- authority registry mutation after report generation causes exact replay failure
- Stage 10F atomic replace failure preserves existing bytes
- reconciliation report authorization flags remain false

## Stage 10C integration

`tests/test_trust_reconciliation_audit.py`

검증 범위:

- verified audit -> `RECONCILED`
- verified R0 audit -> Stage 10E projection count 증가
- legacy unmapped audit -> `PROVENANCE_UNVERIFIED`
- declared missing source -> `SOURCE_MISSING`
- audit ID + SHA both required in Outcome evidence refs
- issuer mismatch -> fail closed
- audit issued after Outcome -> fail closed
- audit issued before assessment capture -> fail closed through Stage 10F temporal projection
- verdict mismatch -> `OUTCOME_VERDICT_MISMATCH`
- retroactive revocation -> provenance invalidation
- same conclusive audit reused twice -> `DUPLICATE_AUTHORITY`
- semantic rehash cannot forge `independent_provenance_verified`

## Strong report verifier

Stage 10F verifier recomputes:

- assessment status/reconciled projection
- audit provenance conjunction
- audit base status
- non-audit legacy outcome base status
- conclusive flag
- duplicate-authority-adjusted status
- summary
- overall report status
- evidence snapshot SHA
- report ID
- report SHA

Verified audit authority projection additionally requires:

- audit ID
- artifact SHA
- issuer ID
- Grant ID
- Trust Root ID
- exact `audit:<artifact_sha256>` authority key
- conclusive evidence ref count

Self-contained semantic verification is not a replacement for source replay. Exact source replay remains the final evidence authority.

## CLI validation

New standalone command family:

```text
pie-trust-audit
```

Integrated command family:

```text
pie-trust <audit-subcommand>
```

Existing reconciliation and pilot-review CLIs are routed through Stage 10F authority-aware/hardened replay boundaries.

No command added in Stage 10F can set:

```text
automation_authorized=true
pilot_authorized=true
```

## Regression CI history

### Initial Draft CI

Run #805 / ID `32096650421`

한 integration test가 실패했다. 원인은 test fixture가 R0가 아니라 `routine_code -> R2` assessment를 사용한 것이었다. Audit reconciliation 자체는 정상 `RECONCILED`였고 Stage 10E가 해당 audit를 R0 denominator에 포함하지 않은 것이 올바른 동작이었다.

Fixture를 `generated_artifact -> R0`로 수정했다.

### Post-fixture CI

Run #811 / ID `32096829392`

- Python 3.11: SUCCESS
- Python 3.13: SUCCESS
- Python 3.14: SUCCESS
- full unittest: SUCCESS
- package asset sync: SUCCESS
- existing `urs` validations: SUCCESS
- wheel build: SUCCESS

### Hardening CI

Run #825 / ID `32097133871`

- Python 3.11: SUCCESS
- Python 3.13: SUCCESS
- Python 3.14: SUCCESS
- full unittest: SUCCESS
- package asset sync: SUCCESS
- existing `urs` validations: SUCCESS
- wheel build: SUCCESS

이 run 이후 replay/write error normalization과 documentation commit이 추가되므로 Stage 10F terminal authority는 PR body에 기록된 **documentation-inclusive final exact-head CI**를 사용한다.

## Asset integrity

Stage 10F root schemas와 packaged schema assets는 동일한 source contract를 유지해야 한다.

대상:

- `trust-audit-authority-registry.schema.json`
- `trust-independent-audit-artifact.schema.json`
- `trust-reconciliation-sources.schema.json`
- `trust-reconciliation-report.schema.json`

CI의 `scripts/sync_package_assets.py`가 root -> package asset synchronization regression을 검증한다.

## Safety interpretation

Stage 10F PASS의 의미:

```text
Independent Audit provenance contract implemented and regression-verified
```

Stage 10F PASS가 의미하지 않는 것:

```text
pilot authorized
automation authorized
R0 pilot active
external cryptographic identity verified
external trusted timestamp verified
audit evidence content independently adjudicated
```

## Terminal condition

Stage 10F를 terminal PASS로 선언하려면 최종 documentation-inclusive exact HEAD에서 다음이 모두 green이어야 한다.

```text
Python 3.11
Python 3.13
Python 3.14
full unittest discovery
package asset sync
existing urs validations
wheel build
```

그리고 PR은 Ready for Review이되 unmerged 상태를 유지한다.
