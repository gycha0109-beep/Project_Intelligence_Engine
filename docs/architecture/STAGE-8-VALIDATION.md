# Stage 8 Validation

상태: `PASS`

권위 기준선: PR #15 HEAD `f97b7367a66bb3a7b077536350d5f604bfb83fe9`

검증된 코드 HEAD: `92429f89d3d727fc51f87e65ac38c8b4692c2dac`

## 검증 대상

- unchanged tracked file과 file relation `CURRENT`
- changed dependency target의 `TARGET_CHANGED` stale reason
- changed source의 `SOURCE_CHANGED` stale reason
- missing source·target의 개별 stale reason
- changed/missing file과 dependent source의 impacted recheck aggregation
- verified Ledger의 project별 최신 Run 선택
- project Run 부재 시 `NO_VERIFIED_RUN` warning
- 다른 project Run 제외
- invalid·tampered Ledger fail-closed
- invalid·tampered Graph fail-closed
- Windows path normalization
- absolute·parent traversal·root escape·symlink traversal 거부
- duplicate normalized file path·relation natural key 거부
- non-file edge 제외와 warning count
- deterministic snapshot hash·report ID·report hash
- idempotent Ledger reimport time이 snapshot identity를 변경하지 않음
- rehashed file status·relation·summary·recheck tamper 탐지
- reordered·extended projection tamper 탐지
- report input·output symlink 거부
- atomic output replace failure 시 기존 bytes 보존
- `pie-reground` CURRENT·STALE advisory exit `0`
- report verification failure exit `4`, input/runtime failure exit `3`
- 기존 repository 전체 regression
- package asset synchronization
- 기존 CLI/profile/finding validation
- wheel build including `pie-reground`

## 검증 이력

1. 초기 구현 HEAD `773d98867fc500fd12c3f973395dba39052a2232`의 CI에서 hardening test 1개가 실패했다.
2. 실패 원인은 제품 결함이 아니라 verifier가 실제 hash에서 status를 재계산하는 동작과 테스트 기대가 불일치한 것이었다.
3. 테스트 기대를 수정하고, 구현 리뷰에서 stable snapshot identity·canonical projection·safe CLI input·Graph file natural ID·single-read hash/size를 보완했다.
4. 임시 diagnosis·hardening workflow, patch script와 log를 모두 제거했다.
5. 깨끗한 코드 HEAD `92429f89d3d727fc51f87e65ac38c8b4692c2dac`의 GitHub Actions run `30090607168`이 Python 3.11·3.13·3.14에서 통과했다.
6. 각 job은 package install, asset sync, full unit/regression, `urs version`, 4개 profile, finding validation과 wheel build를 모두 완료했다.

## 판정

Stage 8 기능·회귀 검증: `PASS`

이 문서와 Architecture index가 포함된 마지막 exact HEAD에서 동일 matrix를 재검증하며, 최종 run은 PR 본문을 권위 기록으로 사용한다.
