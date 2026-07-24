# PIE Stage 4 — Evidence Ledger Foundation

기준일: 2026-07-24  
선행 기준선: PR #11 HEAD `27717f00c689ee0ae7c8f0bfb440b1b61e7ccb2f`  
작업 브랜치: `agent/stage-4-evidence-ledger-foundation`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

Stage 3의 `identity.json`을 입력으로 사용하는 SQLite 관계 인덱스를 추가한다.

```text
Review Run / PR artifact directory
  └─ identity.json + original files
          ↓ validate
Evidence Ledger SQLite
  ├─ Run projection
  ├─ Artifact projection
  ├─ explicit Decision / Policy projection
  └─ future Claim / Evidence relation tables
```

Ledger는 원본 파일을 대체하지 않는다. DB를 삭제해도 원본 artifact directory에서 전부 재구축할 수 있어야 한다.

## 2. 범위

### 생성

```text
src/review_system/ledger.py
src/review_system/ledger_cli.py
tests/test_ledger.py
```

### 수정

```text
pyproject.toml
docs/architecture/README.md
```

### 상세 기록

```text
docs/architecture/STAGE-4-IMPLEMENTATION-REVIEW.md
docs/architecture/STAGE-4-VALIDATION.md
```

## 3. 비목표

- 기존 Review Run·PR artifact schema 교체
- artifact binary 또는 Markdown 본문을 SQLite에 복제
- 자동 Claim 의미 추론
- Finding·Defect Registry
- Attempt 영속화
- Rule evaluation·Policy Registry
- 네트워크 DB·ORM·외부 dependency 추가
- 기존 `pie` CLI command의 동작 변경
- 제품 버전 변경

## 4. 권위와 복구 모델

```text
authoritative source = artifact directory + identity.json
SQLite Ledger        = rebuildable relational projection
```

규칙:

1. import 전에 `validate_identity_manifest(..., require_complete=True)`를 반드시 통과한다.
2. Ledger는 absolute artifact root를 로컬 locator로 저장하지만 artifact 본문은 저장하지 않는다.
3. 같은 logical Run의 재import는 중복 row를 만들지 않고 projection을 갱신한다.
4. DB가 artifact root 내부에 있으면 self-indexing과 identity 순환이 발생하므로 거부한다.
5. rebuild는 임시 DB를 완전히 검증한 뒤 원자적으로 교체한다.
6. 기존 DB는 rebuild가 성공하기 전까지 보존한다.

## 5. 최초 schema

```sql
schema_migrations
runs
artifacts
claims
evidence
claim_evidence
decisions
policy_snapshots
```

### runs

- `run_id`: Stage 3 logical Run ID
- `run_key_sha256`: full natural-key digest, UNIQUE
- `project_id`
- `run_type`: `review` 또는 `pull_request`
- `source_revision`
- `source_identifier`
- `legacy_run_id`: 기존 Review Run directory ID 또는 PR 표시 ID
- `artifact_root`: 로컬 원본 directory locator
- `manifest_sha256`
- `imported_at`

### artifacts

- Stage 3 `artifact_id`와 `artifact_key_sha256`을 그대로 사용한다.
- `run_id` foreign key와 `(run_id, relative_path)` uniqueness를 둔다.
- content hash, media type, size만 저장한다.

### claims / evidence / claim_evidence

Stage 4에서 관계 구조만 고정한다. 자동 Claim 생성은 근거 의미가 합의되지 않았으므로 보류한다.

### decisions / policy_snapshots

Review Run에 명시적으로 존재하는 `gate-result.json`, `gate-policy.yml`만 projection한다. 새로운 판정을 생성하지 않는다.

## 6. Migration 규칙

- 표준 라이브러리 `sqlite3`만 사용한다.
- migration version과 SQL checksum을 `schema_migrations`에 기록한다.
- 적용된 version의 checksum이 코드와 다르면 fail-closed한다.
- foreign key를 모든 connection에서 활성화한다.
- `CREATE TABLE IF NOT EXISTS`는 crash recovery를 위한 재진입성에만 사용하며 checksum 검증을 대체하지 않는다.

## 7. API

```python
initialize_ledger(database) -> Path
import_artifact_directory(database, directory, expected_run_type=None) -> dict
verify_ledger(database) -> dict
rebuild_ledger(database, directories) -> dict
show_run(database, run_id) -> dict | None
```

## 8. CLI

기존 대형 `pie` parser를 변경하지 않고 foundation 전용 entrypoint를 추가한다.

```text
pie-ledger init --database <path>
pie-ledger import-run <directory> --database <path>
pie-ledger import-pr <directory> --database <path>
pie-ledger verify --database <path>
pie-ledger rebuild <directory>... --database <path>
pie-ledger show-run <logical-run-id> --database <path>
```

이 경계는 기존 `pie` CLI의 출력·exit code 회귀 위험을 차단한다. 후속 호환 alias는 Ledger 계약 동결 후 별도 Stage에서 판단한다.

## 9. Failure 정책

- identity tamper, missing artifact, unexpected artifact: import 거부
- expected run type mismatch: import 거부
- duplicate import: idempotent update
- run ID/full key collision: fail-closed
- migration checksum mismatch: fail-closed
- corrupt DB: verify가 `valid=false`와 오류를 반환
- missing artifact root: verify 실패
- rebuild 중 한 directory 실패: 임시 DB 삭제, 기존 DB 유지
- DB inside artifact root: import·rebuild 거부

## 10. 설계 리뷰

### DR-1 — SQLite를 새 권위 원본으로 사용

**결정:** 금지. 현재 artifact portability와 Git/ZIP 보존 장점을 잃고 복구 경로가 DB에 종속된다.

### DR-2 — artifact 본문을 BLOB으로 저장

**결정:** 금지. 중복·DB 팽창·대용량 diff 문제를 만든다. Ledger는 metadata index다.

### DR-3 — Claim을 metrics와 보고서에서 자동 생성

**결정:** 보류. statement·scope·status 의미가 아직 고정되지 않았다. 빈 관계 table만 만든다.

### DR-4 — 모든 기존 artifact directory를 자동 탐색

**결정:** 보류. repository-wide scan은 잘못된 directory와 stale copy를 수집할 수 있다. rebuild 입력은 명시적 directory 목록이다.

### DR-5 — DB를 Run directory 내부 기본 생성

**결정:** 금지. DB 자체가 unexpected artifact가 되고 identity hash 순환을 만든다.

### DR-6 — SQLAlchemy 도입

**결정:** 제외. 초기 schema와 transaction 범위는 `sqlite3`로 충분하며 dependency·packaging 위험이 더 크다.

### DR-7 — import 시 기존 logical Run을 immutable로 취급

**결정:** 제외. Review Run은 sync·Gate 과정에서 같은 logical Run의 artifact projection이 완성된다. 재import는 해당 Run row와 하위 projection을 transaction 안에서 교체한다.

## 11. 검증 계획

1. empty DB initialization
2. migration replay와 checksum mismatch
3. foreign key 활성화
4. Review Run import
5. PR Run import
6. run type mismatch
7. duplicate idempotent import
8. artifact modified·missing·unexpected 차단
9. DB-inside-root 차단
10. explicit Gate Decision·Policy projection
11. verification of current artifact hashes
12. corrupt DB handling
13. atomic rebuild와 기존 DB 보존
14. `show-run` projection
15. CLI exit code·JSON output
16. Python 3.11·3.13·3.14 full regression
17. package asset sync, existing CLI/profile/finding smoke, wheel build

## 12. Rollback

Stage 4 변경을 revert하고 SQLite 파일을 삭제하면 기존 Review Run과 PR 분석은 영향을 받지 않는다. 원본 artifact schema migration은 없다.

## 13. Exit Criteria

- 최초 schema와 checksum migration이 존재한다.
- Review Run·PR identity directory를 idempotent하게 import한다.
- Ledger verify가 DB와 현재 원본 artifact의 불일치를 탐지한다.
- 명시적 directory 목록으로 atomic rebuild가 가능하다.
- 기존 artifact·CLI·dependency 계약이 유지된다.
- 전체 matrix와 targeted failure tests가 통과한다.
