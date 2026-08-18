# Stage 10D Validation

상태: `PENDING_CI`

기준선: PR #19 HEAD `c3a9facd6e2f530dfea069cb092636be734cee2e`

검증 예정:

- observation policy schema validation
- R0 safe cohort + non-R0 unsafe challenge PASS case
- missing unsafe denominator => FNR null / insufficient evidence
- R0 unsafe Outcome => threshold blocked
- WORKFLOW_ACCEPTED exclusion from reviewed count
- generated_at cannot inflate evidence span
- embedded policy/check tamper detection
- registry/policy source replay mismatch detection
- symlink rejection
- report atomic write path
- `pie-trust` and `pie-trust-observation` CLI smoke
- root/package asset sync
- Python 3.11 / 3.13 / 3.14 full regression
- wheel build
