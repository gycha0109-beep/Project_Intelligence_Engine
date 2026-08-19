# PIE Stage 9 — BuildMap Export

기준일: 2026-07-24  
선행 기준선: PR #16 HEAD `7d4de5a37295d6154158f715a383fd4e7f44d0a9`  
작업 브랜치: `agent/stage-9-buildmap-export`  
상태: `PASS`

## 1. 목적

PIE의 Run, Artifact, Claim, Evidence, Finding, Defect, Decision과 Policy projection을 BuildMap이 중복 저장하지 않고 참조할 수 있는 최소 export 계약을 추가한다.

```text
verified Evidence Ledger
→ explicit Run selection
→ metadata-only projection
→ default and caller redaction
→ stable source fingerprint
→ idempotent export identity
→ buildmap-export.json
```

BuildMap export는 PIE 원본을 복제하는 archive가 아니다. BuildMap은 ID와 hash를 보존하고, 상세 원문은 PIE의 권위 artifact로 돌아가 확인한다.

## 2. 범위

### 신규

```text
schemas/buildmap-export.schema.json
src/review_system/assets/schemas/buildmap-export.schema.json
src/review_system/buildmap_export.py
tests/test_buildmap_export.py
tests/test_buildmap_export_hardening.py
```

### 수정

```text
src/review_system/cli.py
pyproject.toml
docs/architecture/README.md
```

### 비목표

- BuildMap 데이터베이스 쓰기
- network 전송 또는 event bus
- PIE artifact body 복제
- GitHub discussion, comment, review body export
- local absolute path export
- Ledger migration
- BuildMap 전용 UI 또는 importer 구현
- signer identity 또는 encryption
- background synchronization
- 기존 artifact/schema/CLI 의미 변경

## 3. 입력 계약

필수 입력:

```text
verified Evidence Ledger
project_id
run_id
output path
```

선택 입력:

```text
additional redaction path globs
generated_at
```

- `verify_ledger()` 전체 검증이 통과한 DB만 사용한다.
- 선택한 Run은 요청 project와 정확히 일치해야 한다.
- export는 Run 하나의 deterministic projection이다.
- Ledger의 `artifact_root`와 `imported_at`은 export identity에 포함하지 않는다.

## 4. Projection 계약

### Source

- `pie_run_uri`: `pie://runs/<run_id>`
- `run_id`
- `run_key_sha256`
- `run_type`
- `source_revision`
- 안전한 scheme의 `source_identifier`
- `manifest_sha256`

원본 source identifier가 허용 scheme과 안전한 URI 규칙을 통과하지 못하면 `pie_run_uri`로 대체하고 redaction metadata에 기록한다.

### Artifact reference

포함 필드:

```text
artifact_id
artifact_type
relative_path
sha256
media_type
size_bytes
```

artifact body와 absolute root는 포함하지 않는다.

### Claim

```text
claim_id
claim_type
status
policy_version
```

statement와 scope 원문은 제외한다.

### Evidence

```text
evidence_id
evidence_level
evidence_type
result_sha256
artifact_id
artifact_redacted
```

summary, result 원문, locator, producer 자유문은 제외한다.

### Finding

```text
finding_id
category
severity
confidence
status
defect_ids
artifact_id
artifact_redacted
finding_sha256
```

제목, impact, recommended action과 scope 원문은 제외한다.

### Defect

```text
defect_id
category
lifecycle_status
signature_sha256
first_seen_run_id
last_seen_run_id
artifact_refs: artifact_id + relation + artifact_redacted
```

제목, root cause, owner와 resolution 원문은 제외한다.

### Decision

```text
decision_id
decision_type
outcome
policy_version
decided_at
artifact_id
artifact_redacted
reason_refs
```

`reasons_json`은 message나 expression을 복제하지 않고 group과 reason ID만 추출한다.

### Policy snapshot

```text
policy_snapshot_id
policy_version
sha256
artifact_id
artifact_redacted
```

## 5. Redaction

기본 정책 ID는 `buildmap-default-1`이다.

기본 제외:

- `github-source.json`
- discussion/comment/review 원본 artifact
- patch와 diff
- log
- `.env`, secret, credential, token, key, pem 계열 경로

caller는 추가 glob을 지정할 수 있다. export에는 glob 원문을 저장하지 않고 canonical pattern set의 SHA-256만 저장한다.

Redaction metadata:

```text
policy_id
content_included = false
raw_github_discussion_included = false
source_identifier_redacted
custom_patterns_sha256
omitted_artifacts counts by reason
```

누락 artifact ID나 경로 목록은 export하지 않는다.

## 6. Identity와 hash

### Source fingerprint

원본 Ledger의 선택 Run과 연결된 row를 canonicalize하여 계산한다.

- Run의 stable field
- 전체 Artifact metadata
- Claim, Evidence, ClaimEvidence
- Finding, Finding→Defect link와 linked Defect
- Defect→Artifact evidence link
- Decision과 Policy snapshot

`artifact_root`, `imported_at` 등 projection 재생성 시 변하는 local metadata는 제외한다. 민감 원문은 export에 노출하지 않지만 source fingerprint 계산에는 반영된다.

### Projection hash

다음을 canonical JSON으로 계산한다.

```text
schema version
project
safe source reference
metadata-only projection
redaction metadata
source fingerprint
```

`generated_at`, `export_id`, `export_sha256`는 제외한다.

### Export ID

```text
export_key = project_id + run_id + run_key_sha256 + projection_sha256
export_id = buildmap-<canonical sha prefix>
```

동일 Run, 동일 Ledger source state, 동일 redaction policy면 재실행 시간과 무관하게 같은 export ID가 생성된다.

### Export hash

`export_sha256` 자기 field를 제외한 export 전체의 canonical digest다.

## 7. 검증

Self-contained verifier는 다음을 재계산한다.

- JSON Schema 2020-12
- canonical array ordering
- path normalization과 traversal 차단
- opaque reference integrity
- Finding→Defect와 Defect→Artifact relationship projection
- reason reference projection
- redaction invariants
- projection SHA-256
- export ID
- export SHA-256

Source verifier는 Ledger 전체 검증 후 source fingerprint를 다시 계산한다.

## 8. CLI

Migration Plan 계약대로 기존 `pie`/`urs`에 additive command를 추가한다.

```text
pie export-buildmap
pie validate-buildmap-export
```

### export-buildmap

```text
--ledger
--project-id
--run-id
--output
--redact-path (repeatable)
--generated-at (optional)
```

### validate-buildmap-export

```text
export path
--ledger (optional source replay)
```

Exit:

- success: `0`
- input/runtime error: `2`
- integrity/schema/source mismatch: `4`

## 9. 설계 리뷰

### DR-1 — Artifact body를 export에 포함

**기각.** BuildMap이 PIE 원본을 중복 저장하게 되고 민감정보 범위가 확대된다.

### DR-2 — 모든 project Run을 한 export에 포함

**보류.** 초기 계약은 명시적 Run 하나로 고정한다. history export는 pagination과 incremental cursor 설계 이후 검토한다.

### DR-3 — Finding title과 Decision message 포함

**기각.** 자유문은 secret, 개인정보와 private discussion을 포함할 수 있다. 상태·분류·ID·hash만 export한다.

### DR-4 — Export ID에 generated time 포함

**기각.** 동일 source projection의 idempotent import를 방해한다.

### DR-5 — Ledger 일부 row만 읽고 export

**기각.** source fingerprint가 신뢰 가능하려면 Ledger 전체 integrity와 원본 artifact 검증을 먼저 통과해야 한다.

### DR-6 — raw GitHub discussion을 opt-out 방식으로 포함

**기각.** 초기 계약은 기본·강제 제외다. 향후 명시적 별도 consent schema가 없는 한 포함하지 않는다.

## 10. Exit Criteria

- sample Run export가 `buildmap-export.schema.json`을 통과한다.
- 동일 source projection 재실행에서 export ID가 동일하다.
- BuildMap consumer fixture가 ID/hash/reference만으로 import 가능하다.
- raw GitHub discussion과 sensitive artifact reference가 기본 제외된다.
- artifact body와 local absolute path가 export에 없다.
- source fingerprint가 PIE Ledger 원본과 재검증된다.
- outer rehash 후 의미 변조도 탐지된다.
- atomic output failure가 기존 bytes를 보존한다.
- 기존 CLI와 artifact 계약 회귀가 없다.
- Python 3.11, 3.13, 3.14 matrix와 wheel build가 통과한다.
- 최종 diff에 임시 workflow, script, trigger와 log가 없다.

## 11. Rollback

Stage 9 변경을 revert하면 export schema와 additive CLI만 제거된다. Ledger와 기존 artifact를 수정하지 않으므로 data migration rollback은 없다.
