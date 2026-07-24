# Stage 10A Validation

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

권위 기준선: PR #17 HEAD `cf4732bd78ca6d1e7ab78c44d0719285331d6803`

검증된 코드 HEAD: `d58b2c3264e986cd0ca02117c9156c4f0575d19e`

GitHub Actions run: `30108052100`

## 검증 범위

- Python 3.11, 3.13, 3.14 full unittest matrix
- source/package schema asset synchronization
- existing `urs version`
- Journey Connect, Bejewely, BuildMap, generic-webapp profile validation
- sample Finding validation
- wheel build including `pie-trust`
- Trust request, Reground observation과 Trust report JSON Schema 2020-12 validation
- deterministic R0~R4 classification
- Task Class보다 높은 changed-path floor
- Profile protected path matching
- required scenario, repository/head, high-risk, verifier, Policy/Evaluation, rollback/replay hard-gate advisory
- missing evidence valid `NOT_READY`
- invalid supplied Ledger·Policy·Evaluation·Reground evidence fail closed
- active Policy와 PASS Evaluation ID·hash·ruleset binding
- human-confirmed Reground TP·FP·TN·FN, coverage, precision, recall과 false-positive rate
- positive 또는 negative denominator 부재 시 nullable metric과 readiness failure
- stable source revision enforcement
- stable report identity across generated time
- risk, hard gate, readiness와 report hash tamper detection
- optional request·profile·evidence source replay
- standalone `pie-trust` assess·verify
- main `pie` assess·validate delegation
- symlink·broken symlink·path traversal rejection
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
- ready evidence fixture: `PASS`
- missing evidence NOT_READY fixture: `PASS`
- R3 protected migration fixture: `PASS`
- R4 verifier fixture: `PASS`
- Policy/Evaluation mismatch fixture: `PASS`
- Reground mixed-label metric fixture: `PASS`
- source replay: `PASS`
- tamper and file-safety hardening: `PASS`
- temporary workflow, patch script와 diagnostic log cleanup: `PASS`

## 확인된 회귀 없음

- 기존 `pie`, `urs`, Gate, Ledger, Defect, Evaluation, Policy, Reground와 BuildMap 명령 의미 유지
- 기존 Gate decision과 exit code 유지
- 기존 artifact와 Ledger schema 유지
- dependency와 제품 버전 유지
- source/package asset drift 없음
- 자동 승인·merge·GitHub write 경로 없음
- report-only constant 유지

## 최종 판정

Stage 10A code validation: `PASS`

Architecture index와 최종 리뷰 문서가 포함된 exact HEAD의 GitHub Actions matrix를 통과한 뒤 PR을 Ready for review로 전환한다.
