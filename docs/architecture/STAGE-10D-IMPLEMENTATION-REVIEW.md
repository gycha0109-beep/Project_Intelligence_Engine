# Stage 10D Implementation Review

상태: `IN_PROGRESS`

기준선: PR #19 HEAD `c3a9facd6e2f530dfea069cb092636be734cee2e`

## 현재 구현 범위

- R0-only report-only observation threshold policy schema
- R0 pilot-specific confusion matrix
- R0 safe cohort + all-band unsafe challenge denominator
- zero-tolerance observed R0 false negative policy floor
- evidence timestamp span
- embedded policy snapshot and report semantic verification
- source replay against Stage 10B registry + threshold policy
- `pie-trust` additive commands and `pie-trust-observation` entry point
- no pilot or automation authorization

## 구현 중 발견한 설계 결함

초기 설계는 R0 cohort 안에서 `minimum_confirmed_unsafe_count > 0`과 `maximum_confirmed_false_negatives = 0`을 동시에 요구했다. R0로 분류된 unsafe Outcome은 정의상 R0 pilot false negative이므로 이 조합은 논리적으로 통과 불가능했다.

교정:

- R0 안전 운영 표본은 R0 cohort에서 측정한다.
- unsafe challenge denominator는 모든 conclusive Outcome에서 측정한다.
- `predicted_risk_band=R0 AND outcome=UNSAFE`만 R0 false negative다.
- `predicted_risk_band>R0 AND outcome=UNSAFE`는 R0 pilot 관점의 true positive다.

이 구조로 "R0를 안전하게 통과시킨 표본"과 "unsafe를 R0 밖으로 밀어낸 challenge 표본"을 동시에 요구할 수 있다.

## 후속 리뷰 대기

- exact-head focused/full regression
- CLI/wheel/package asset 검증
- source replay hardening
- tamper/symlink/atomic path review
- docs 최종화
