# Stage 10D Validation

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

기준선: PR #19 HEAD `c3a9facd6e2f530dfea069cb092636be734cee2e`

## 검증 범위

- observation policy schema validation
- R0 safe cohort + non-R0 unsafe challenge threshold-satisfied case
- missing unsafe challenge denominator => R0 FNR null / insufficient evidence
- R0 unsafe Outcome => threshold blocked
- `WORKFLOW_ACCEPTED` exclusion from reviewed count
- `generated_at` cannot inflate evidence span
- embedded policy/check rehash tamper detection
- valid registry/policy source mutation replay mismatch detection
- policy/report input symlink rejection
- report output symlink rejection and CLI exit 3 normalization
- atomic replace failure preserves existing report bytes
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

각 job에서 다음이 모두 성공했다.

- `pip install -e .`
- `python scripts/sync_package_assets.py`
- `python -m unittest discover -s tests -v`
- 기존 `urs` version/profile/Finding validations
- `pip wheel . --no-deps --wheel-dir dist-ci`

### Hardening implementation

HEAD `b9e1c1b8b1a3e3c5088b9a1474be882211ee0519`

GitHub Actions:

- run #647
- run ID `32084469804`
- Python 3.11: SUCCESS
- Python 3.13: SUCCESS
- Python 3.14: SUCCESS

이 run에는 다음 hardening이 포함됐다.

- all-band unsafe challenge denominator correction
- embedded policy semantic verification
- valid source replay mutation test
- output symlink error normalization
- atomic output preservation test
- final design contract alignment

## Terminal Safety Assertions

현재 검증은 다음을 보장한다.

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
source_reconciliation.required_before_pilot=true
source_reconciliation.verified_in_this_stage=false
```

Threshold 만족은 pilot authorization이 아니다.

## 최종 확인 대기

Implementation review·validation·architecture index 최종화가 포함된 exact HEAD에서 Python 3.11·3.13·3.14 matrix를 다시 실행한다. 해당 run이 통과하면 Stage 10D validation을 `PASS`로 확정한다.
