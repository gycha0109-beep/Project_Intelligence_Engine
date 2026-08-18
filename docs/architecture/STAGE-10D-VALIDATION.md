# Stage 10D Validation

상태: `PASS`

기준선: PR #19 HEAD `c3a9facd6e2f530dfea069cb092636be734cee2e`

## 검증 범위

- observation policy schema validation
- R0 safe cohort + non-R0 unsafe challenge threshold-satisfied case
- missing unsafe challenge denominator => R0 FNR null / insufficient evidence
- R0 unsafe Outcome => threshold blocked
- `WORKFLOW_ACCEPTED` exclusion from reviewed count
- distinct-assessment independent Audit cardinality
- `generated_at` cannot inflate evidence span
- embedded policy/check rehash tamper detection
- malformed report schema fail-closed behavior
- valid registry/policy source mutation replay mismatch detection
- policy/report input symlink rejection
- report output symlink rejection and CLI exit 3 normalization
- atomic replace failure preserves existing report bytes
- repository sample policy validation
- `pie-trust` and `pie-trust-observation` CLI end-to-end
- root/package schema asset sync
- Python 3.11 / 3.13 / 3.14 full regression
- existing `urs` profile/Finding validation
- wheel build

## CI Evidence

### Initial implementation

HEAD `4e7f55d75416acb009110a4c490c9ce78a7252c4`

GitHub Actions:

- run #641
- run ID `32084224419`
- Python 3.11: SUCCESS
- Python 3.13: SUCCESS
- Python 3.14: SUCCESS

### First hardening

HEAD `b9e1c1b8b1a3e3c5088b9a1474be882211ee0519`

GitHub Actions:

- run #647
- run ID `32084469804`
- Python 3.11: SUCCESS
- Python 3.13: SUCCESS
- Python 3.14: SUCCESS

### Final code hardening

HEAD `20f13be01f2c5c768ae4a9100016473baf3bfedd`

GitHub Actions:

- run #659
- run ID `32084758761`
- Python 3.11: SUCCESS
- Python 3.13: SUCCESS
- Python 3.14: SUCCESS

각 matrix job에서 다음이 모두 성공했다.

- `pip install -e .`
- `python scripts/sync_package_assets.py`
- `python -m unittest discover -s tests -v`
- 기존 `urs` version/profile/Finding validations
- `pip wheel . --no-deps --wheel-dir dist-ci`

## Hardening Assertions

- R0 independent Audit threshold는 event 개수가 아닌 distinct R0 assessment 수다.
- unsafe challenge가 없으면 FNR은 `null`이며 threshold PASS가 아니다.
- R0+UNSAFE가 있으면 `THRESHOLD_BLOCKED`다.
- malformed report는 semantic verifier 예외를 발생시키지 않고 schema validation failure로 닫힌다.
- output symlink는 Stage 10D input error로 정규화된다.
- atomic replace 실패는 기존 report를 보존한다.
- valid registry/policy 변경도 source replay에서 탐지된다.
- sample policy는 report-only/R0/zero-miss invariant를 유지한다.

## Terminal Safety Assertions

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
source_reconciliation.required_before_pilot=true
source_reconciliation.verified_in_this_stage=false
```

Threshold 만족은 pilot authorization이 아니다.

Documentation-inclusive final exact-head CI authority는 PR #20 body에 기록한다.
