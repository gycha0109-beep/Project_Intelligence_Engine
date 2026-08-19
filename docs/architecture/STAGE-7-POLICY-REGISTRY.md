# PIE Stage 7 — Policy Registry

기준일: 2026-07-24  
선행 기준선: PR #14 HEAD `e3d9aedc8b66e53a2cae61a3c18fc9280137354a`  
작업 브랜치: `agent/stage-7-policy-registry`  
상태: `PASS`

## 1. 목적

개별 `approved-rules.yml` 파일을 그대로 승인 단위로 사용하던 구조에, 평가 증거와 계보를 포함한 versioned Policy Registry를 추가한다.

```text
approved Rule set + PASS Evaluation report
→ immutable policy snapshot
→ explicit approval/activation
→ active materialized approved-rules.yml
→ supersession / retirement audit
```

Registry JSON이 권위 원본이며 기존 `approved-rules.yml`은 active Policy의 materialized view로 유지한다.

## 2. 범위

### 신규

```text
src/review_system/policy_registry.py
src/review_system/policy_cli.py
tests/test_policy_registry.py
tests/test_policy_registry_hardening.py
```

### 수정

```text
pyproject.toml
docs/architecture/README.md
```

### 비목표

- 기존 Rule schema `1.0` 교체
- 기존 `approve-rule`, `pie-eval`, `pie`, `urs` 동작 변경
- remote registry·server·background activation
- cryptographic signer identity
- Ledger migration
- future-effective scheduler
- automatic policy generation
- AI judge

## 3. 권위 구조

```json
{
  "schema_version": "1.0",
  "registry_id": "...",
  "project_id": "...",
  "active_policy_id": "policy-...",
  "policies": [
    {
      "policy_id": "policy-...",
      "version": "1.2.0",
      "parent_policy_id": "policy-...",
      "status": "ACTIVE",
      "ruleset": {
        "sha256": "...",
        "rules": {"schema_version": "1.0", "rules": []}
      },
      "evaluation": {
        "evaluation_id": "...",
        "report": "evaluation.json",
        "report_sha256": "...",
        "decision": "PASS",
        "challenger_policy_sha256": "..."
      },
      "approval": {},
      "effective_at": "...",
      "superseded_by": null,
      "retirement": null,
      "events": [],
      "policy_sha256": "..."
    }
  ],
  "registry_sha256": "..."
}
```

## 4. Identity와 무결성

- `ruleset.sha256`은 normalized approved Rule object의 canonical JSON SHA-256이다.
- Evaluation report는 Stage 6 verifier를 통과하고 Gate가 `PASS`여야 한다.
- Evaluation report의 `challenger_policy.sha256`은 `ruleset.sha256`과 일치해야 한다.
- `policy_id`는 project, semantic version, parent, ruleset hash, evaluation ID의 digest다.
- 각 lifecycle event는 payload hash와 이전 event hash를 포함하는 hash chain이다.
- `policy_sha256`은 자기 hash field를 제외한 Policy 전체 canonical digest다.
- `registry_sha256`은 자기 hash field를 제외한 Registry 전체 canonical digest다.
- verifier는 hash만 확인하지 않고 status, active projection, parent lineage, event sequence를 재계산한다.

## 5. Lifecycle

```text
DRAFT
→ ACTIVE
→ SUPERSEDED
→ RETIRED
```

### build

- approved Rule file과 PASS evaluation report로 `DRAFT` snapshot 생성
- semantic version, project ID, created-by, created-at 필수
- root Policy는 parent가 없어야 한다.
- 후속 Policy는 parent ID를 명시한다.
- version과 policy ID 중복을 거부한다.

### approve / activate

- `DRAFT`만 승인 가능
- 첫 Policy는 parent가 없어야 한다.
- 기존 active Policy가 있으면 새 Policy의 parent는 정확히 현재 active Policy여야 한다.
- 기존 active Policy는 `SUPERSEDED`, 새 Policy는 `ACTIVE`가 된다.
- approval, effective date, lifecycle events를 기록한다.
- Registry와 materialized `approved-rules.yml`을 한 transaction 성격으로 원자적 교체한다.

### retire

- `ACTIVE` 또는 `SUPERSEDED` Policy만 retire 가능
- actor, timestamp, reason 필수
- active Policy retirement 시 `active_policy_id`는 null이 된다.
- materialized view 경로가 주어지면 빈 approved Rule set으로 원자 갱신한다.
- 재활성화는 초기 범위에서 허용하지 않는다.

## 6. CLI

별도 entrypoint `pie-policy`를 추가한다.

```text
pie-policy build
pie-policy approve
pie-policy compare
pie-policy retire
pie-policy verify
pie-policy list
pie-policy show
pie-policy materialize
```

기존 `pie`와 `urs` parser에는 subcommand를 추가하지 않는다.

## 7. 설계 리뷰

### DR-1 — approved-rules.yml을 Registry 원본으로 사용

**기각.** mutable materialized file만으로는 version, parent, evaluation, supersession history를 보존할 수 없다.

### DR-2 — Policy snapshot에 Rule file path만 저장

**기각.** 파일 이동·변조 시 Registry 재현성이 깨진다. normalized Rule object를 snapshot 내부에 포함한다.

### DR-3 — evaluation reference만 저장하고 report Gate·hash를 신뢰

**기각.** Stage 6 verifier를 재사용하고 challenger ruleset hash까지 대조한다.

### DR-4 — approval과 activation을 분리하고 future scheduler 추가

**보류.** 초기 버전은 명시적 approval 시 즉시 ACTIVE로 전환한다. `effective_at`은 감사 metadata이며 미래 예약 실행은 지원하지 않는다.

### DR-5 — branch 형태 parent graph 허용

**제한.** DRAFT 생성은 임의 parent를 참조할 수 있으나 activation은 현재 active Policy의 직계 자식만 허용해 active lineage를 선형으로 유지한다.

### DR-6 — 기존 Rule approval을 Policy approval로 강제 전환

**기각.** 기존 `approve-rule` 호환성을 유지한다. Policy Registry는 별도 Control Plane 계층이다.

### DR-7 — SQLite를 권위 원본으로 사용

**기각.** Stage 4 원칙과 동일하게 파일이 권위 원본이어야 재구축과 코드 리뷰가 가능하다.

## 8. 안전 규칙

- registry, rules, report, materialized view의 symlink target을 거부한다.
- invalid semver, timestamp, project mismatch, missing parent, cycle을 fail-closed한다.
- PASS가 아닌 evaluation, ruleset hash mismatch를 거부한다.
- active Policy는 최대 1개다.
- `active_policy_id`와 Policy status projection이 불일치하면 검증 실패한다.
- status 변경에는 lifecycle event가 필요하다.
- atomic replace 실패 시 Registry와 materialized view의 기존 bytes를 복구한다.
- retirement reason은 빈 문자열을 허용하지 않는다.

## 9. 검증 계획

1. root DRAFT build
2. PASS evaluation과 ruleset hash binding
3. FAIL·tampered·mismatched evaluation 거부
4. semantic version·duplicate version·duplicate identity
5. first activation
6. child activation과 parent supersession
7. stale/non-active parent activation 거부
8. active materialized view 동등성
9. Policy·Registry·event hash tamper
10. parent cycle·missing parent·multiple active projection
11. active·superseded retirement
12. atomic two-file rollback
13. symlink·path safety
14. compare added/removed/changed Rules
15. CLI exit contract
16. Python 3.11·3.13·3.14 full matrix
17. existing CLI/profile/finding validation
18. wheel build including `pie-policy`

## 10. Exit Criteria

- Rule 집합이 versioned Policy snapshot으로 저장된다.
- active Policy의 parent lineage와 평가 증거를 추적할 수 있다.
- active 전환 시 기존 Policy가 원자적으로 supersede된다.
- `approved-rules.yml` materialized view가 active snapshot과 byte-equivalent 의미를 가진다.
- retirement와 audit event가 검증 가능하다.
- Registry와 Policy tamper가 fail-closed된다.
- 기존 CLI·artifact·Ledger·Defect·Evaluation 계약 회귀가 없다.
- 최종 diff에 임시 workflow·script·trigger·log가 없다.

## 11. 구현 결과

- 설계된 Registry·Policy·event identity와 lifecycle을 구현했다.
- 구현 리뷰에서 ID 재계산, parent version 증가, report traversal, lifecycle metadata projection 누락을 보완했다.
- 코드 HEAD `9980bff910bb8f524d27836c052c726ab5c30291`의 Python 3.11·3.13·3.14 matrix가 통과했다.
- 설계·리뷰·검증 문서 포함 HEAD `42d827c8af743f71749f5a43c80f8c8acf71c1af`의 matrix도 통과했다.
- 최종 상태 문서를 포함한 exact HEAD 결과는 PR #15에 기록한다.

## 12. Rollback

Stage 7 변경을 revert하면 기존 `approved-rules.yml` workflow와 Stage 6 Evaluation Lab은 그대로 남는다. Registry는 별도 파일 계층이므로 schema/data migration rollback이 필요 없다.
