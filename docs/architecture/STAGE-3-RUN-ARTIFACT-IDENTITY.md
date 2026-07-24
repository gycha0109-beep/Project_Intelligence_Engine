# PIE Stage 3 — Run and Artifact Identity

기준일: 2026-07-24  
선행 기준선: PR #10 HEAD `b0f4a30e625c6cd027241326c391450b87e1a10b`  
작업 브랜치: `agent/stage-3-run-artifact-identity`  
상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`

## 1. 목적

SQLite Evidence Ledger를 추가하기 전에 기존 Review Run과 PR 분석 산출물을 동일한 방식으로 식별할 수 있는 결정적 identity 규칙을 구현한다.

```text
기존 파일 산출물
→ logical Run identity
→ Artifact identity
→ identity.json projection
→ 후속 Ledger import
```

기존 파일이 계속 권위 원본이며 `identity.json`은 재생성 가능한 projection이다.

## 2. 범위

### 생성

```text
src/review_system/identity.py
tests/test_identity.py
docs/architecture/STAGE-3-IMPLEMENTATION-REVIEW.md
docs/architecture/STAGE-3-VALIDATION.md
```

### 수정

```text
src/review_system/run.py
src/review_system/application/analyze_pr.py
docs/architecture/README.md
```

### 비목표

- SQLite·ORM·migration 추가
- Claim·Evidence·Decision 테이블 구현
- 기존 `run.json.run_id` 교체
- 기존 PR source·impact schema 변경
- 기존 CLI command·option 변경
- random UUID 도입
- Attempt persistence 구현
- artifact 원문을 DB나 별도 store로 이동
- 기존 manifest·archive format 교체

## 3. 핵심 결정

### 3.1 Logical Run과 Attempt

```text
Run = project + run_type + source_revision + source_identifier
Attempt = 동일 logical Run을 실제로 수행한 개별 시도
```

Stage 3에서는 logical Run identity만 구현한다. Attempt는 후속 Ledger schema가 확장할 수 있도록 용어와 key 경계를 문서로 고정하지만 저장하지 않는다.

동일 PR head를 다시 분석하면 같은 logical Run ID가 생성된다. 산출물 내용이 바뀌면 Artifact ID와 identity manifest hash가 달라진다.

### 3.2 Natural key와 외부 ID

Run natural key payload:

```json
{
  "project_id": "...",
  "run_type": "review|pull_request",
  "source_revision": "git:<sha>|sha256:<digest>|unresolved",
  "source_identifier": "..."
}
```

```text
run_key_sha256 = SHA-256(canonical JSON payload)
run_id = "run-" + first 32 hex characters
```

Artifact natural key payload:

```json
{
  "run_key_sha256": "...",
  "relative_path": "...",
  "sha256": "..."
}
```

```text
artifact_key_sha256 = SHA-256(canonical JSON payload)
artifact_id = "artifact-" + first 32 hex characters
```

외부 ID는 짧은 표시·조회를 위한 128-bit prefix이며 full key digest도 함께 보존한다.

### 3.3 Artifact path 이동

Artifact ID에는 relative path가 포함된다. 같은 내용의 파일이 다른 경로로 이동하면 새 Artifact ID가 된다.

내용 계보는 별도 `sha256`으로 연결할 수 있다. 경로 이동과 동일 artifact를 억지로 동일시하지 않는다.

### 3.4 Source revision

정규형:

```text
raw Git SHA       → git:<lowercase sha>
sha256 evidence   → sha256:<lowercase digest>
revision 부재     → unresolved
symbolic HEAD/ref → 허용하지 않음
```

PR 분석은 `head_oid`를 사용하고, 부재 시 `source_sha256`을 fallback으로 사용한다.

Review Run은 초기화 시 repository HEAD를 best-effort로 캡처한다. Git revision을 확인할 수 없는 legacy·비 Git 실행은 `unresolved`과 기존 `run_id` 기반 source identifier를 사용한다.

### 3.5 Source identifier

```text
PR Run:
github://<hostname>/<owner>/<repo>/pull/<number>

Review Run:
review://<project_id>/<legacy-run-id>
```

PR hostname과 repository name은 소문자로 정규화한다. Review Run의 legacy ID는 기존 사용자 의미를 보존한다.

## 4. Identity Manifest

파일명:

```text
identity.json
```

형태:

```json
{
  "schema_version": "1.0",
  "run": {
    "run_id": "run-...",
    "run_key_sha256": "...",
    "project_id": "...",
    "run_type": "...",
    "source_revision": "...",
    "source_identifier": "..."
  },
  "artifacts": [
    {
      "artifact_id": "artifact-...",
      "artifact_key_sha256": "...",
      "artifact_type": "...",
      "relative_path": "...",
      "sha256": "...",
      "media_type": "...",
      "size_bytes": 0
    }
  ],
  "manifest_sha256": "..."
}
```

규칙:

- artifact는 relative path 순으로 정렬한다.
- `identity.json` 자체는 재귀 hash를 피하기 위해 목록에서 제외한다.
- `initial-manifest.sha256`, `manifest.sha256`은 기존 manifest 체계와 순환하지 않도록 제외한다.
- hidden file도 일반 artifact와 동일하게 취급한다.
- symlink가 artifact root 밖으로 이탈하면 fail-closed한다.
- manifest hash는 `manifest_sha256` 필드를 제외한 canonical JSON의 SHA-256이다.
- timestamp를 넣지 않아 동일 파일 집합에서 deterministic하다.

## 5. 기존 흐름 통합

### Review Run

`initialize_run`:

1. 기존 `run.json`과 템플릿 생성
2. logical Run identity 생성
3. `run.json.identity` additive metadata 기록
4. `identity.json` 생성
5. 기존 `initial-manifest.sha256` 생성

`sync_run`, `calculate_gate_directory`, `archive_run`은 파일 변경 후 identity projection을 갱신한다.

legacy Review Run에 identity metadata가 없으면 sync 시 기존 project ID·run ID로 identity를 생성한다.

### PR Run

`analyze_pull_request`가 기존 네 산출물을 작성한 후 `identity.json`을 추가 생성한다.

기존 파일명, source hash, impact hash, Markdown과 diff는 변경하지 않는다.

## 6. 검증 정책

`validate_identity_manifest`는 다음을 검증한다.

- schema version
- Run key와 external ID 재계산
- manifest canonical hash
- artifact path 안전성
- duplicate path·ID
- file existence
- size·SHA-256
- Artifact key·ID 재계산
- 누락되거나 예상 밖인 현재 artifact

Review Run directory validation은 `identity.json`이 존재할 때 identity 오류를 포함한다. legacy directory에 identity 파일이 없으면 기존 동작을 유지한다.

## 7. 설계 리뷰

### DR-1 — Ledger SQLite를 같은 Stage에 구현

**결정:** 제외. Identity 변경과 persistence migration을 분리해야 rollback과 오류 원인 추적이 가능하다.

### DR-2 — 기존 `run.json.run_id`를 deterministic ID로 교체

**결정:** 금지. 기존 run directory name과 사용자 지정 ID 계약을 깨뜨린다. deterministic ID는 `identity.logical_run_id`와 sidecar에 추가한다.

### DR-3 — 모든 재실행에 random Attempt UUID 부여

**결정:** 보류. 파일만으로 재구축 가능한 deterministic foundation을 먼저 만든다.

### DR-4 — Artifact ID에서 path 제외

**결정:** 제외. 동일 내용이 다른 역할·경로로 복제된 경우를 구분할 수 없다. content continuity는 SHA-256으로 별도 조회한다.

### DR-5 — timestamp를 Run key에 포함

**결정:** 금지. 같은 source를 재import할 때 identity가 달라져 idempotent rebuild가 불가능해진다.

### DR-6 — absolute path 저장

**결정:** 금지. machine-local 정보와 사용자 경로를 노출하며 ZIP·다른 OS에서 재구축할 수 없다.

### DR-7 — symlink를 resolve하지 않고 문자열 path만 검사

**결정:** 금지. artifact root 밖의 파일을 identity에 포함할 수 있으므로 resolved containment를 검사한다.

### DR-8 — legacy run에서 source revision 부재를 오류 처리

**결정:** 제외. 기존 파일을 import할 수 있어야 한다. `unresolved` 상태를 명시하고 source identifier로 logical key를 안정화한다.

## 8. 보호 계약

- 기존 Review Run schema는 additional metadata를 허용한다.
- 기존 `run_id`, output directory, archive root 이름을 유지한다.
- 기존 PR 산출물 4개와 content를 유지한다.
- 기존 source·impact·diff hash를 변경하지 않는다.
- 기존 manifest verifier와 ZIP 구조를 유지한다.
- identity projection 삭제가 원본 artifact 손실을 만들지 않는다.
- 외부 dependency를 추가하지 않는다.

## 9. 검증 계획

1. deterministic Run ID
2. source revision normalization·invalid symbolic ref
3. PR·Review source identifier canonicalization
4. deterministic Artifact ID
5. path move와 content hash 관계
6. path traversal·symlink escape 차단
7. manifest ordering·canonical hash
8. modified·missing·unexpected artifact 탐지
9. legacy Review Run identity upgrade
10. Review Run init·sync·gate·archive
11. PR analysis sidecar와 기존 hash 동등성
12. Python 3.11·3.13·3.14 full matrix
13. package asset sync, CLI/profile/finding smoke, wheel build

## 10. Rollback

Stage 3 변경을 revert하면 `identity.json` 생성과 identity metadata만 사라진다. 기존 run·PR artifacts, manifest, archive와 schema migration은 영향을 받지 않는다.

## 11. Exit Criteria

- Review Run과 PR Run이 동일 identity primitive를 사용한다.
- logical Run 재생성 시 동일 ID가 나온다.
- artifact path·content 변경이 결정적으로 탐지된다.
- legacy artifacts는 기존 동작을 유지한다.
- identity projection은 원본 파일에서 재생성 가능하다.
- 전체 regression과 exact-head CI가 통과한다.
