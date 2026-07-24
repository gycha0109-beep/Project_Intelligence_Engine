# Stage 6 Validation

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

권위 기준선: PR #13 HEAD `f171129935b6617ed5d69983b50f07fab2399b3c`

검증 대상 코드 HEAD: `f507c61491b5950dc16f0966420e633a6b206564`

## 검증 대상

- Evaluation Dataset schema와 unique case ID
- development·validation·holdout split
- absolute path, traversal, missing artifact, symlink escape
- Windows separator 정규화
- Graph validator와 approved Rule validator 재사용
- baseline/challenger 동일 executor 실행
- deterministic outcome와 repeatability hard Gate
- changed scope·pack·test TP/FP/FN, precision, recall
- 0분모 metric 규칙
- overall 및 split별 exact match와 protected accuracy
- holdout 필수 Gate
- protected negative regression hard Gate
- same-policy zero delta
- evaluator contract가 evaluation identity에 참여
- outcome, report, metrics, comparison, Gate tamper detection
- atomic report write 실패 rollback
- atomic candidate attach 실패 rollback
- PASS report attach와 FAIL/tampered report 거부
- evaluation 없는 기존 Rule 승인 compatibility warning
- evaluation 있는 Rule 승인 no-warning
- `pie-eval` 0/2/3/4 exit contract
- 기존 전체 repository regression
- package asset synchronization
- 기존 CLI/profile/finding validation
- wheel build와 `pie-eval` packaging

## 검증 이력

1. 초기 구현 HEAD `12af36f186dfb6d19f9a8accdf5def8db1bccd8f`의 GitHub Actions run `30082458842`가 Python 3.11·3.13·3.14에서 통과했다.
2. 구현 리뷰에서 holdout 누락, evaluator identity 누락, path normalization projection 누락, metric 기본 threshold 0을 발견했다.
3. hardening suite를 추가하고 focused Evaluation tests, 전체 regression, `pie-eval --help`, 기존 `pie --help`를 통과한 변경만 HEAD `f507c61491b5950dc16f0966420e633a6b206564`에 반영했다.
4. 임시 적용 workflow와 script는 제품 diff에서 제거했다.

## 최종 판정 조건

설계·구현 리뷰·검증 문서와 Architecture index를 포함하고 임시 자산이 제거된 마지막 exact HEAD에서 다음 GitHub Actions matrix가 모두 통과하면 Stage 6 Gate를 `PASS`로 확정한다.

- Python 3.11
- Python 3.13
- Python 3.14
- full unit/regression suite
- package asset synchronization
- existing `urs version`
- four profile validations
- finding validation
- wheel build including `pie-eval`
