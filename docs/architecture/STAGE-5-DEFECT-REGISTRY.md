# PIE Stage 5 — Defect Registry

기준일: 2026-07-24  
선행 기준선: PR #12 HEAD `9a59bf1d41b9c6b5be559957737f78b66d6d24f3`  
작업 브랜치: `agent/stage-5-defect-registry`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

특정 실행에서 관찰된 Finding과 여러 실행에 걸쳐 추적되는 Defect를 분리한다.

```text
Run artifact/findings.json
        ↓ validated projection
Ledger Finding
        ↓ explicit human/deterministic link
Defect Registry
        ↓ lifecycle event
OBSERVED → ... → CLOSED → REOPENED
```

Finding은 Run-local 관찰이다. Defect는 project-local 장기 객체다. 자동 유사도는 Defect 확정 권한을 갖지 않는다.

## 2. 권위 모델

Stage 4의 재구축 계약을 깨지 않기 위해 Defect 상태를 SQLite에만 저장하지 않는다.

```text
Run-local Finding authority = validated findings.json
Defect authority           = canonical defect-registry.json
SQLite Ledger              = rebuildable relational projection
```

규칙:

1. Defect mutation은 canonical registry JSON을 원자적으로 갱신한다.
2. Ledger는 registry file을 projection하고 source path·SHA-256을 기록한다.
3. DB 삭제 후 artifact directories와 registry JSON으로 전체 재구축할 수 있어야 한다.
4. registry write 성공 후 DB sync가 실패하면 registry가 권위이며 재동기화로 복구한다.
5. DB-only Defect mutation은 제공하지 않는다.

## 3. 범위

### 생성

```text
src/review_system/defects.py
src/review_system/defect_cli.py
tests/test_defects.py
tests/test_defect_registry_hardening.py
```

### 수정

```text
src/review_system/ledger.py
src/review_system/ledger_cli.py
pyproject.toml
docs/architecture/README.md
```

### 상세 기록

```text
docs/architecture/STAGE-5-IMPLEMENTATION-REVIEW.md
docs/architecture/STAGE-5-VALIDATION.md
```

## 4. 비목표

- finding-schema.json 또는 기존 findings.json 형식 변경
- 자동 similarity matching
- root cause 자동 추론
- GitHub Issue 자동 생성·동기화
- Rule Candidate 자동 생성
- Defect가 Gate를 자동 차단하도록 변경
- Attempt·Evaluation Lab·Policy Registry 구현
- 기존 `pie`·`urs`·`pie-ledger` 명령의 기존 출력 변경
- 외부 dependency 또는 제품 버전 변경
- 불확실한 역사적 결함 7건을 추측해 seed로 등록

역사 seed는 authoritative source가 확보된 뒤 별도 data-only migration으로 수행한다.

## 5. Migration 002

Stage 4 migration `001`을 수정하지 않고 append-only migration `002`를 추가한다.

```text
findings
registry_sources
defects
finding_defects
defect_events
defect_artifacts
```

### findings

- `finding_id`: `run_id + source_finding_id`로 계산한 deterministic ID
- `finding_key_sha256`: full natural key digest
- `run_id`: FK
- `source_finding_id`: 기존 findings.json `id`
- `title`, `category`, `severity`, `confidence`, `status`
- `scope_json`, `impact`, `recommended_action`
- `finding_sha256`: canonical source finding hash
- `artifact_id`: findings.json artifact FK
- `imported_at`
- UNIQUE `(run_id, source_finding_id)`

### registry_sources

- `project_id`: PRIMARY KEY
- `registry_path`: absolute local locator
- `registry_sha256`
- `imported_at`

한 project는 foundation 단계에서 하나의 canonical registry source만 허용한다.

### defects

- `defect_id`: `project_id + signature` deterministic ID
- `defect_key_sha256`: full natural key digest
- `project_id`
- `signature`: project 내 UNIQUE
- `title`, `category`
- `root_cause`: nullable
- `lifecycle_status`
- `first_seen_run_id`, `last_seen_run_id`: nullable FK
- `owner`, `resolution`: nullable
- `created_at`, `updated_at`

### finding_defects

- `finding_id`, `defect_id`
- `match_method`: `manual` 또는 `deterministic_signature`
- `confidence`: 0.0~1.0
- `approved_by`
- `linked_at`
- composite PK

자동 similarity proposal은 이 테이블에 확정 link로 기록하지 않는다.

### defect_events

append-only lifecycle·link audit log다.

- `event_id`
- `defect_id`
- `event_type`
- `status_from`, `status_to`
- `actor`, `reason`, `occurred_at`
- registry event payload hash

### defect_artifacts

- `defect_id`, `artifact_id`
- `relation`: `reproducer`, `diagnostic`, `mitigation`, `verification`, `resolution_evidence`
- `linked_by`, `linked_at`, `note`

## 6. Finding projection

Review Run import에서 identity manifest에 `findings.json`이 존재하는 경우:

1. `validate_findings_file`을 통과해야 한다.
2. 각 source finding을 deterministic `finding_id`로 변환한다.
3. 같은 Run 재import는 upsert한다.
4. source에서 사라진 Finding이 Defect에 연결되지 않았다면 stale row를 삭제한다.
5. 연결된 Finding이 source에서 사라지면 history 손실을 추측하지 않고 import를 fail-closed한다.
6. PR Run에 findings.json이 없으면 Finding 0건으로 정상 처리한다.

## 7. Registry JSON 계약

```json
{
  "schema_version": "1.0",
  "project_id": "demo",
  "defects": [],
  "finding_links": [],
  "events": [],
  "artifact_links": [],
  "registry_sha256": "..."
}
```

- 모든 배열은 stable key로 정렬한다.
- `registry_sha256`은 자신을 제외한 canonical JSON SHA-256이다.
- duplicate ID, dangling reference, invalid lifecycle, unsafe field는 mutation·sync 전에 거부한다.
- temp file write + `os.replace`로 원자 저장한다.

## 8. Lifecycle

```text
OBSERVED
→ REPRODUCED
→ CLASSIFIED
→ RULE_CANDIDATE
→ MITIGATED
→ VERIFIED
→ CLOSED
→ REOPENED
→ REPRODUCED
```

허용 전이:

- `OBSERVED → REPRODUCED`
- `REPRODUCED → CLASSIFIED`
- `CLASSIFIED → RULE_CANDIDATE | MITIGATED`
- `RULE_CANDIDATE → MITIGATED`
- `MITIGATED → VERIFIED`
- `VERIFIED → CLOSED`
- `CLOSED → REOPENED`
- `REOPENED → REPRODUCED`

안전 규칙:

- lifecycle 건너뛰기 금지
- 같은 상태 재전이 금지
- `CLOSED`에는 non-empty resolution과 `resolution_evidence` artifact link가 필요하다.
- `REOPENED`에는 재발 이유가 필요하다.
- root cause는 nullable이며 CLASSIFIED도 category classification만으로 허용한다.
- transition은 append-only event를 생성한다.

## 9. API

```python
initialize_defect_registry(path, project_id) -> Path
create_defect(registry, database, *, signature, title, category, actor, ...) -> dict
link_finding(registry, database, *, finding_id, defect_id, match_method, confidence, approved_by) -> dict
link_defect_artifact(registry, database, *, defect_id, artifact_id, relation, linked_by, note=None) -> dict
transition_defect(registry, database, *, defect_id, target_status, actor, reason, resolution=None) -> dict
sync_defect_registry(database, registry) -> dict
verify_defect_registry(database, registry) -> dict
show_defect(database, defect_id) -> dict | None
list_defects(database, *, project_id=None, status=None) -> list[dict]
```

## 10. CLI

기존 CLI 계약을 보호하기 위해 전용 entrypoint를 추가한다.

```text
pie-defect init --registry <path> --project-id <id>
pie-defect create --registry <path> --database <db> ...
pie-defect link-finding --registry <path> --database <db> ...
pie-defect link-artifact --registry <path> --database <db> ...
pie-defect transition --registry <path> --database <db> ...
pie-defect show <defect-id> --database <db>
pie-defect list --database <db> [--project-id] [--status]
pie-defect sync --registry <path> --database <db>
pie-defect verify --registry <path> --database <db>
```

`pie-ledger rebuild`에는 repeatable `--defect-registry`만 추가한다. 기존 positional directory와 출력은 유지한다.

## 11. 설계 리뷰

### DR-1 — Defect를 SQLite에만 저장

**결정:** 금지. Stage 4의 DB 재구축·삭제 안전 계약을 깨뜨린다. canonical registry JSON을 둔다.

### DR-2 — Finding ID를 기존 `id` 그대로 사용

**결정:** 금지. 서로 다른 Run에서 같은 source ID가 재사용될 수 있다. Run-scoped deterministic ID를 사용한다.

### DR-3 — 유사 제목·category로 자동 연결

**결정:** 금지. false merge가 장기 결함 이력을 오염시킨다. manual 또는 deterministic signature link만 허용한다.

### DR-4 — Defect 생성 시 root cause 필수

**결정:** 제외. 관찰 단계에서 root cause를 강제하면 추측을 저장하게 된다.

### DR-5 — source finding 삭제 시 cascade

**결정:** 연결되지 않은 stale projection만 삭제한다. Defect와 연결된 Finding 삭제는 fail-closed한다.

### DR-6 — CLOSED 후 row 수정으로 REOPEN

**결정:** 금지. append-only event와 명시적 `REOPENED` 상태를 사용한다.

### DR-7 — 기존 7개 결함을 기억 기반으로 seed

**결정:** 금지. repository에 authoritative fixture가 없으므로 사실을 추측하지 않는다.

### DR-8 — registry와 DB의 분산 transaction

**결정:** registry file을 먼저 원자 저장하고 DB를 projection한다. DB sync 실패는 stale 상태로 검출되며 재동기화 가능하다.

## 12. 검증 계획

1. migration 001→002와 checksum replay
2. existing Stage 4 DB upgrade
3. valid findings projection
4. duplicate source finding ID rejection
5. invalid findings import rollback
6. idempotent finding reimport
7. unlinked stale finding deletion
8. linked stale finding fail-closed
9. registry canonical hash·ordering
10. deterministic Defect ID
11. duplicate signature idempotence/conflict
12. cross-project finding/artifact link rejection
13. manual link approval requirement
14. lifecycle valid/invalid transitions
15. CLOSED resolution evidence requirement
16. REOPENED reason requirement
17. append-only event preservation
18. registry/DB tamper detection
19. rebuild with registry source
20. rebuild failure preserves existing DB
21. CLI exit code·JSON output
22. Python 3.11·3.13·3.14 full regression
23. package asset sync, existing CLI/profile/finding smoke, wheel build

## 13. Rollback

- Stage 5 code를 revert해도 migration 001 DB와 기존 artifact는 유지된다.
- migration 002가 적용된 DB는 이전 code에서 unsupported migration으로 fail-closed하므로 rollback 시 DB backup 또는 Stage 4 artifact 기반 rebuild를 사용한다.
- canonical defect-registry.json은 독립 파일로 보존된다.

## 14. Exit Criteria

- Finding과 Defect가 별도 table·identity·lifecycle을 갖는다.
- Run import가 validated findings를 idempotent하게 projection한다.
- Defect mutation이 canonical registry와 append-only events를 보존한다.
- CLOSED·REOPENED safety rule이 강제된다.
- artifact directories와 registry JSON으로 Ledger를 재구축할 수 있다.
- 기존 CLI·artifact·dependency·version 계약이 유지된다.
- 전체 matrix와 targeted failure tests가 통과한다.
