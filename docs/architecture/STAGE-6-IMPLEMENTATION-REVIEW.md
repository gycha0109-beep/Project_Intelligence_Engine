# Stage 6 Implementation Review

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

권위 기준선: PR #13 HEAD `f171129935b6617ed5d69983b50f07fab2399b3c`

## 구현 결과

- local JSON/YAML Evaluation Dataset과 상대 artifact 경계를 추가했다.
- 기존 `analyze_change()`를 baseline·challenger approved Rule 집합에 동일하게 실행한다.
- 직접 변경·영향 파일, review pack, required test, matched Rule, protected hard signal을 정규화한다.
- 전체 및 development·validation·holdout split별 precision·recall·exact match·protected accuracy를 계산한다.
- protected negative regression, repeatability, holdout 존재, 최소 precision·recall을 hard Gate로 사용한다.
- dataset·policy·evaluator·outcome·report identity를 canonical SHA-256으로 고정한다.
- PASS report를 candidate Rule metadata에 원자적으로 연결한다.
- 기존 Rule schema 1.0에서는 evaluation 없는 승인도 허용하되 명시적 warning을 발생시킨다.
- 별도 `pie-eval` CLI와 frozen application request/result를 추가했다.
- 기존 `pie`, `urs`, Ledger, Defect Registry, artifact schema, dependency, product version은 변경하지 않았다.

## 구현 리뷰 중 발견·보완

### IR-1 — holdout 없이 PASS 가능

초기 Gate는 holdout case가 있을 때만 holdout threshold를 검사했다. development·validation case만으로도 승인 가능한 상태였다.

**조치:** `holdout_present`를 독립 hard condition으로 추가했다. holdout이 없으면 report는 생성되지만 Gate는 `FAIL`이다.

### IR-2 — evaluator 변경이 evaluation identity에 반영되지 않음

초기 `evaluation_id`는 dataset·policy·threshold만 사용했다. 분석 알고리즘이 변경되어 outcome이 달라져도 동일 evaluation ID가 재사용될 수 있었다.

**조치:** evaluator name, evaluator contract version, PIE product version을 report와 evaluation natural key에 포함했다.

### IR-3 — validation 후 원본 경로 표현 사용

Dataset validator는 Windows separator를 정상 경로로 검증했지만 실행·지표 계산에는 정규화 전 원본을 사용했다. 같은 경로가 표현 차이 때문에 FP/FN으로 계산될 수 있었다.

**조치:** 검증된 Dataset을 정규화 projection으로 변환한 뒤 descriptor·실행·지표 계산에 사용한다.

### IR-4 — 기본 metric threshold가 0

초기 API와 CLI 기본값은 precision·recall `0.0`이었다. protected regression만 없으면 성능이 없는 challenger도 PASS할 수 있었다.

**조치:** 기본 precision·recall threshold를 모두 `1.0`으로 변경했다. 사용자가 명시적으로 완화할 수 있으나 report에 threshold가 고정된다.

### IR-5 — failure-path oracle 부족

초기 suite는 정상 비교와 일반 tamper를 검증했지만 재해시된 내부 변조, 비결정 실행, symlink 입력, 0분모, atomic replace 실패를 직접 고정하지 않았다.

**조치:** 별도 hardening suite를 추가해 모두 fail-closed로 검증했다.

## 안전성 검토

- dataset root 밖 absolute·traversal·symlink artifact를 거부한다.
- Graph와 approved Rule file은 기존 validator를 그대로 사용한다.
- 한 case라도 입력·실행 오류가 발생하면 report를 쓰지 않는다.
- report와 candidate metadata write는 temp file, fsync, `os.replace`를 사용한다.
- replace 실패 시 기존 target과 candidate file을 보존하고 temporary file을 제거한다.
- outcome hash만 재계산한 변조는 재계산 metrics·comparison·Gate 검증에서 탐지한다.
- outer report hash까지 재계산한 변조도 evaluation ID 또는 재계산 projection 차이로 탐지한다.
- automatic label 생성이나 AI judge가 없으므로 사람이 부여한 기대값을 우회하지 않는다.
- protected negative regression은 다른 metric 향상으로 상쇄되지 않는다.

## 남은 제한

- authoritative label이 제공되지 않아 Journey Connect 12개 PR 실데이터는 이번 PR에 임의로 생성하지 않았다.
- 초기 protected result는 graph 누락과 unconfigured Rule pack을 정규화한 hard signal이며 전체 protected snapshot executor를 대체하지 않는다.
- report SHA-256은 무결성 digest이지 서명자 신원을 증명하는 전자서명이 아니다.
- `verify-report`는 self-contained report 내부 무결성을 검증하며 원본 dataset·policy 파일을 다시 실행하지 않는다.
- evaluation metadata는 Rule schema 1.0에서 advisory이며 Stage 7 이후 별도 schema 전환 전까지 승인 필수값이 아니다.
- remote executor, dataset registry, Policy Registry, AI judge는 후속 단계 대상이다.

## 판정

구현 리뷰: `PASS`

검증된 hardening 코드 HEAD: `f507c61491b5950dc16f0966420e633a6b206564`

Stage 6 hardening workflow에서 focused Evaluation Lab suite, 전체 repository regression, `pie-eval`·기존 `pie` smoke가 통과한 뒤 제품 변경만 위 HEAD에 반영됐다. 임시 적용 workflow와 script는 이후 제거했다.
