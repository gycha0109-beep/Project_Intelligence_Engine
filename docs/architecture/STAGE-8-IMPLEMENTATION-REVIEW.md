# Stage 8 Implementation Review

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

권위 기준선: PR #15 HEAD `f97b7367a66bb3a7b077536350d5f604bfb83fe9`

검증된 코드 HEAD: `92429f89d3d727fc51f87e65ac38c8b4692c2dac`

## 구현 결과

- 기존 Project Graph schema `1.0`을 재사용해 tracked file snapshot을 읽는다.
- Graph file node의 recorded SHA-256과 current repository raw bytes SHA-256을 비교한다.
- file state를 `CURRENT`, `CHANGED`, `MISSING`으로 산출한다.
- file-to-file Graph edge를 `CURRENT` 또는 `STALE` relation으로 projection한다.
- source·target change/missing reason을 개별적으로 보존한다.
- changed dependency의 source와 changed/missing file 자체를 impacted recheck 목록으로 집계한다.
- Evidence Ledger 전체 검증이 통과한 뒤 project별 최신 Run을 read-only 조회한다.
- project Run이 없으면 `NO_VERIFIED_RUN` warning을 기록하되 report 생성을 허용한다.
- snapshot hash, deterministic report ID, report hash와 semantic verifier를 추가했다.
- 별도 `pie-reground analyze`, `pie-reground verify-report` CLI를 추가했다.
- STALE report도 advisory 결과이므로 정상 exit `0`을 유지한다.
- 기존 Graph·Ledger schema와 `pie`, `urs`, Ledger, Defect, Evaluation, Policy CLI는 변경하지 않았다.

## 구현 리뷰 중 발견·보완

### IR-1 — idempotent Ledger reimport가 snapshot identity를 바꾸는 문제

초기 snapshot payload에 `last_verified_run.imported_at` 전체를 포함했다. 동일 logical Run을 재import하면 source state가 같아도 snapshot hash와 report ID가 바뀔 수 있었다.

**조치:** snapshot에는 stable Run identity와 source fields만 포함하고 `imported_at`은 report metadata에만 유지한다. 같은 Graph·repository state와 logical Run이면 snapshot hash와 report ID가 유지된다.

### IR-2 — 재정렬·추가 field를 재해시하면 canonical report로 통과 가능

초기 verifier는 file·relation의 의미는 재계산했지만 list ordering과 unknown field를 canonical projection과 직접 대조하지 않았다.

**조치:** file과 relation을 허용 field만으로 다시 구성하고 정렬한 뒤 raw report projection과 완전 일치시킨다. reorder 또는 injected field는 외부 hash를 다시 계산해도 실패한다.

### IR-3 — `verify-report` CLI가 safe report loader를 우회

초기 CLI는 `load_data()`를 직접 호출해 self-contained 검증은 했지만 report input path의 symlink 검사를 우회했다.

**조치:** `load_reground_report()`를 사용하고 verification failure와 path/runtime failure의 exit code를 분리한다.

### IR-4 — Graph file node ID와 normalized path 자연키 불일치

기존 Graph validator는 file node path를 정규화하지만 `file:<path>` ID와 path 일치까지 강제하지 않는다. 불일치 Graph는 relation projection을 모호하게 만들 수 있었다.

**조치:** Reground 입력 경계에서 file node ID가 normalized path의 `file:<path>`와 정확히 일치해야 한다.

### IR-5 — hash와 size의 서로 다른 read 시점

초기 구현은 streaming hash 후 별도 `stat()`으로 size를 읽었다. 동시 변경 시 서로 다른 snapshot을 기록할 가능성이 있었다.

**조치:** 한 번의 raw-byte read에서 SHA-256과 byte count를 함께 계산한다.

### IR-6 — hardening test의 잘못된 기대

file status를 조작해도 verifier는 recorded/current hash에서 실제 status를 재계산하므로 기존 impacted 목록은 여전히 올바르다. 초기 테스트는 impacted mismatch까지 요구했다.

**조치:** status·reason·summary mismatch를 검증하도록 테스트를 수정했다. 제품 동작 변경은 없었다.

## 안전성 검토

- Graph와 Ledger는 symlink component가 없는 regular file이어야 한다.
- repository root와 tracked file은 symlink traversal·absolute·parent traversal·root escape를 거부한다.
- missing tracked file은 stale evidence로 기록하되 symlink나 directory 대체는 입력 오류로 처리한다.
- Ledger DB는 SQLite integrity, FK, migration, Run artifact와 registry projection을 모두 검증한 뒤 조회한다.
- duplicate normalized file path와 duplicate relation natural key를 거부한다.
- report verifier는 file status, relation reason, impacted list, summary, warning, snapshot, report ID와 report hash를 재계산한다.
- report output은 temporary file, fsync, atomic replace를 사용한다.
- STALE은 advisory이며 자동 merge block으로 사용하지 않는다.

## 남은 제한

- Graph 생성 당시 없던 신규 repository file은 초기 범위에서 탐지하지 않는다.
- symbol, component, database object 등 비파일 node relation은 warning count만 남기고 freshness 판정에서 제외한다.
- Ledger의 `imported_at`은 최신 Run 정렬 metadata이며 cryptographic provenance가 아니다.
- Ledger 전체 검증은 원본 artifact root가 접근 가능한 상태를 요구한다.
- self-contained report verification은 source replay가 아니다.
- SHA-256은 내용 무결성을 제공하지만 signer identity를 증명하지 않는다.
- local file과 SQLite에 대한 cross-process locking은 제공하지 않는다.

## 판정

구현 리뷰: `PASS`

GitHub Actions run `30090607168`에서 Python 3.11·3.13·3.14 전체 regression과 wheel build가 통과했다. 문서 포함 최종 exact HEAD에서 같은 matrix를 재검증한다.
