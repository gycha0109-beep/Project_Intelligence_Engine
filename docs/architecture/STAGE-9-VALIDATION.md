# Stage 9 Validation

상태: `PASS`

권위 기준선: PR #16 HEAD `7d4de5a37295d6154158f715a383fd4e7f44d0a9`

최종 검증 HEAD: `783f6de0ca0d97709ae5b5bdfaac460b19f23514`

GitHub Actions run: `30101785712`

## 검증 범위

- Python 3.11, 3.13, 3.14 full unittest matrix
- source/package schema asset synchronization
- existing `urs version`
- Journey Connect, Bejewely, BuildMap, generic-webapp profile validation
- sample Finding validation
- wheel build including `pie-buildmap`
- metadata-only sample Run export
- JSON Schema 2020-12 validation
- optional Evidence Ledger source replay
- BuildMap consumer idempotent import fixture
- raw GitHub discussion, patch, log, credential-like path redaction
- Claim, Evidence, Finding, Defect와 Decision 자유문 비노출
- Finding→Defect와 Defect→Artifact relationship preservation
- stable export ID across generated time and idempotent Ledger reimport
- source fingerprint, projection hash, export ID와 export hash tamper detection
- malformed reference, reordered array, injected field와 path traversal hardening
- symlink input/output rejection
- atomic output rollback

## 결과

- Python 3.11: `PASS`
- Python 3.13: `PASS`
- Python 3.14: `PASS`
- full regression: `PASS`
- schema validation: `PASS`
- asset sync: `PASS`
- CLI/profile/Finding smoke: `PASS`
- wheel build: `PASS`
- BuildMap consumer fixture: `PASS`
- redaction fixture: `PASS`
- source replay: `PASS`
- final code diff cleanup: `PASS`

## 확인된 회귀 없음

- 기존 `pie`, `urs`, Ledger, Defect, Evaluation, Policy와 Reground 명령 의미 유지
- 기존 artifact와 Ledger schema 유지
- dependency와 제품 버전 유지
- source/package asset drift 없음
- raw discussion 기본 제외 유지
- 최종 코드 HEAD에 temporary workflow, patch script와 diagnostic log 없음

## 최종 판정

Stage 9 validation: `PASS`

문서와 Architecture index를 포함한 HEAD `783f6de0ca0d97709ae5b5bdfaac460b19f23514`에서 GitHub Actions run `30101785712`가 Python 3.11·3.13·3.14 전체 matrix와 wheel build를 통과했다. 이 문서 상태를 반영한 마지막 exact HEAD도 동일 matrix로 재검증한다.
