# PIE Stage 8 — Reground Foundation

기준일: 2026-07-24  
선행 기준선: PR #15 HEAD `f97b7367a66bb3a7b077536350d5f604bfb83fe9`  
작업 브랜치: `agent/stage-8-reground-foundation`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

기존 Project Graph가 기록한 파일 해시와 현재 저장소 파일을 비교하고, 검증된 Evidence Ledger에서 프로젝트의 마지막 Run을 조회해 stale relation과 impacted recheck 목록을 advisory report로 산출한다.

```text
Project Graph + repository files + verified Ledger
→ file snapshot comparison
→ file-to-file relation projection
→ CURRENT / STALE reasons
→ last verified Run
→ impacted recheck list
→ reground-report.json
```

초기 버전은 상태를 설명하고 재검증 대상을 제안한다. merge 차단, 자동 수정, background scheduler는 포함하지 않는다.

## 2. 범위

### 신규

```text
src/review_system/reground.py
src/review_system/reground_cli.py
tests/test_reground.py
tests/test_reground_hardening.py
```

### 수정

```text
pyproject.toml
docs/architecture/README.md
```

### 비목표

- Ledger migration 또는 DB 쓰기
- Graph schema 변경
- repository 전체 재index
- Graph에 없던 신규 파일 자동 탐지
- symbol·database object 의미 변화 판정
- 모든 문서의 semantic freshness 판정
- stale 즉시 merge block
- background scheduler
- remote repository fetch
- cryptographic signer identity
- 기존 `pie`, `urs`, Ledger, Defect, Evaluation, Policy CLI 변경

## 3. 입력 계약

### Project Graph

- 기존 schema `1.0`을 그대로 사용한다.
- `validate_project_graph()`를 통과해야 한다.
- file node의 `path`와 `sha256`을 recorded snapshot으로 사용한다.
- 초기 relation 범위는 source와 target이 모두 file node인 edge다.
- `imports`, `documents`, `likely_verifies` 등 edge type은 의미를 바꾸지 않고 그대로 보존한다.

### Repository root

- 실제 current file bytes를 SHA-256으로 계산한다.
- Graph path는 기존 `normalize_path()` 규칙으로 정규화한다.
- absolute path, traversal, symlink traversal, root escape를 거부한다.
- missing file은 예외로 중단하지 않고 stale reason으로 기록한다.

### Evidence Ledger

- `verify_ledger()`가 전체 통과한 read-only DB만 사용한다.
- `runs.project_id`가 요청 project와 같은 Run 중 `imported_at`, `run_id` 내림차순 첫 항목을 `last_verified_run`으로 사용한다.
- 해당 프로젝트 Run이 없으면 report는 생성하되 `NO_VERIFIED_RUN` warning을 기록한다.
- Reground는 Ledger를 수정하지 않는다.

## 4. 파일 상태

각 Graph file node는 다음 상태 중 하나다.

```text
CURRENT
CHANGED
MISSING
```

- `CURRENT`: current SHA-256 == Graph recorded SHA-256
- `CHANGED`: 파일은 존재하지만 SHA-256이 다름
- `MISSING`: Graph에는 있으나 current repository에 파일이 없음

상태 객체는 path, recorded hash, current hash, size와 reason을 포함한다.

## 5. Relation 상태

Graph edge `source → target`은 source가 target에 의존하거나 target을 문서화·검증하는 관계로 해석한다.

```text
CURRENT
STALE
```

### CURRENT

source와 target file이 모두 `CURRENT`다.

### STALE reasons

```text
SOURCE_CHANGED
SOURCE_MISSING
TARGET_CHANGED
TARGET_MISSING
```

한 relation에 여러 reason이 동시에 존재할 수 있다.

### impacted recheck

- source가 CHANGED/MISSING이면 source path를 재index 대상으로 추가한다.
- target이 CHANGED/MISSING이면 source path를 dependency recheck 대상으로 추가한다.
- 동일 path는 하나로 합치고, relation ID·reason·changed dependency를 누적한다.
- target 자체도 file snapshot의 stale file 목록에는 남지만 dependency recheck 대상은 source다.

## 6. Report 계약

```json
{
  "schema_version": "1.0",
  "report_id": "reground-...",
  "project_id": "...",
  "generated_at": "...",
  "graph": {
    "source": "project-graph.json",
    "graph_sha256": "..."
  },
  "ledger": {
    "database": "ledger.sqlite",
    "last_verified_run": {}
  },
  "summary": {
    "status": "CURRENT|STALE",
    "tracked_files": 0,
    "changed_files": 0,
    "missing_files": 0,
    "relations_checked": 0,
    "stale_relations": 0,
    "impacted_rechecks": 0
  },
  "files": [],
  "relations": [],
  "impacted_rechecks": [],
  "warnings": [],
  "snapshot_sha256": "...",
  "report_sha256": "..."
}
```

- `snapshot_sha256`는 generated time과 report hash를 제외한 source state projection의 canonical digest다.
- `report_id`는 project, graph hash, last verified Run identity, snapshot hash의 deterministic digest다.
- `report_sha256`는 자기 field를 제외한 report 전체 canonical digest다.
- verifier는 hash만 대조하지 않고 file status, relation status, summary, impacted recheck와 report ID를 재계산한다.
- self-contained report 검증은 source replay와 구분한다.

## 7. CLI

별도 entrypoint `pie-reground`를 추가한다.

```text
pie-reground analyze
pie-reground verify-report
```

### analyze

필수 입력:

```text
--project-id
--repository-root
--graph
--ledger
--output
```

유효한 CURRENT 또는 STALE advisory report는 모두 exit `0`이다. stale은 자동 merge failure로 취급하지 않는다.

### verify-report

- valid report: `0`
- input/runtime error: `3`
- report verification failure: `4`

## 8. 설계 리뷰

### DR-1 — current repository를 다시 Graph index해 전체 graph diff 생성

**보류.** 기존 Graph 생성 설정의 include/exclude/component 정의가 Graph artifact에 보존되지 않는다. 초기 버전은 기존 file node snapshot만 비교한다.

### DR-2 — Ledger에 reground 상태를 저장하는 migration 추가

**기각.** Stage 8은 advisory report foundation이다. 운영 경험 없이 DB projection을 먼저 고정하지 않는다.

### DR-3 — source가 바뀌면 target도 impacted로 표시

**기각.** edge는 source가 target에 의존하는 방향이다. target 변경은 source 재검증을 요구하지만 source 변경이 target 재검증을 자동 의미하지는 않는다.

### DR-4 — target 변경만 relation stale로 처리

**기각.** source 변경도 기존 relation 자체가 여전히 유효한지 재index해야 하므로 relation을 stale로 기록한다.

### DR-5 — Ledger가 없거나 invalid여도 Graph stale 결과만 생성

**제한.** 프로젝트 Run 부재는 warning으로 허용하지만 DB 자체가 invalid하면 `last verified Run`이라는 표현을 사용할 수 없으므로 fail-closed한다.

### DR-6 — stale report를 CLI failure로 사용

**기각.** Migration Plan의 초기 범위는 advisory이며 즉시 merge block을 명시적으로 제외한다.

### DR-7 — symbol·database object edge 포함

**보류.** 초기 hash 기준은 file bytes다. 비파일 node의 semantic fingerprint는 후속 설계가 필요하다.

## 9. 안전 규칙

- Graph와 Ledger input의 symlink component를 거부한다.
- repository root 자체와 tracked path의 symlink traversal을 거부한다.
- output symlink를 거부한다.
- Graph validation과 Ledger integrity·migration·artifact verification을 선행한다.
- duplicate normalized file path와 duplicate relation natural key를 거부한다.
- current file은 binary 여부와 무관하게 raw bytes SHA-256으로 비교한다.
- report write는 temporary file + fsync + atomic replace를 사용한다.
- atomic replace 실패 시 기존 output bytes를 유지한다.

## 10. 검증 계획

1. unchanged file relation → CURRENT
2. changed dependency target → STALE + source recheck
3. changed relation source → STALE + source reindex
4. missing source·target reasons
5. multiple reasons·duplicate recheck aggregation
6. latest verified project Run selection
7. project Run 없음 warning
8. 다른 project Run 제외
9. invalid/tampered Ledger 거부
10. invalid/tampered Graph 거부
11. Windows path normalization
12. traversal·absolute·symlink path 거부
13. non-file edge 제외
14. report identity·snapshot·report hash 재계산
15. rehashed summary/relation/recheck tamper 탐지
16. atomic output rollback
17. CLI exit contract
18. Python 3.11·3.13·3.14 full matrix
19. existing CLI/profile/finding validation
20. wheel build including `pie-reground`

## 11. Exit Criteria

- known changed dependency fixture에서 relation이 STALE이 되고 source가 impacted recheck에 포함된다.
- unchanged relation은 CURRENT다.
- Graph path와 raw-byte hash normalization이 기존 규칙과 회귀하지 않는다.
- 검증된 Ledger에서 last verified project Run을 산출한다.
- impacted recheck 목록이 reason과 relation provenance를 보존한다.
- report tamper가 rehash 여부와 관계없이 fail-closed된다.
- 기존 CLI·artifact·Ledger·Defect·Evaluation·Policy 계약 회귀가 없다.
- 최종 diff에 임시 workflow·script·trigger·log가 없다.

## 12. Rollback

Stage 8 변경을 revert하면 별도 advisory CLI와 report 기능만 제거된다. Graph, Ledger, 기존 artifact와 DB schema는 변경하지 않으므로 data migration rollback은 없다.
