# Stage 10A Implementation Review

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

권위 기준선: PR #17 HEAD `cf4732bd78ca6d1e7ab78c44d0719285331d6803`

검증된 코드 HEAD: `d58b2c3264e986cd0ca02117c9156c4f0575d19e`

## 구현 결과

- explicit Task Class와 changed-path floor를 결합해 R0~R4를 결정적으로 계산한다.
- Project Profile의 `protected_paths`를 다시 계산하고 protected change를 별도 hard-gate advisory로 보존한다.
- required scenario, repository/head match, authorization·migration·deployment, verifier·Policy, rollback·replay 근거를 독립 hard gate로 계산한다.
- Evidence Ledger 전체 integrity 검증 후 project-local Run, Artifact, Claim, Evidence, Finding과 Decision 수를 projection한다.
- Defect Registry projection에서 lifecycle별 수, CLOSED resolution evidence와 REOPENED 경험을 집계한다.
- active Policy와 PASS Evaluation을 ID, report hash와 challenger ruleset hash로 연결한다.
- Reground report와 human-confirmed observation을 분리하고 TP, FP, TN, FN, coverage, precision, recall과 false-positive rate를 계산한다.
- 제공되지 않은 evidence는 valid `NOT_READY`로 처리하고, 제공됐지만 변조된 evidence는 report 생성 전에 fail closed한다.
- 결과는 `NOT_READY` 또는 `READY_FOR_HUMAN_COMPARISON`만 사용한다.
- 모든 report는 `mode=REPORT_ONLY`, `automation_authorized=false`, `maximum_automation_band=NONE`을 유지한다.
- request, evidence, snapshot과 report identity를 canonical SHA-256으로 보호한다.
- self-contained semantic verification과 optional source replay를 제공한다.
- symlink·traversal 방어와 atomic output을 적용한다.
- `pie-trust`, `pie trust-assess`, `pie validate-trust-report`를 additive하게 추가한다.
- 기존 Gate, Ledger schema, dependency와 제품 버전은 변경하지 않았다.

## 구현 리뷰 중 발견·보완

### IR-1 — 단일 고위험 파일명 누락

초기 path classifier는 `/auth/` 같은 디렉터리는 R3로 분류했지만 `src/auth.py`, `JwtService.kt`, `roles.sql` 같은 파일명은 일반 source로 분류할 수 있었다.

**조치:** auth, authentication, authorization, OAuth, JWT, role, RLS, permission, security, secret·token·credential·migration 파일명 신호를 R3 floor에 추가했다.

### IR-2 — 분모 없는 Reground 지표의 낙관적 기본값

양성 표본이 없을 때 precision·recall을 1.0으로, 음성 표본이 없을 때 false-positive rate를 0.0으로 계산하면 표본 부족이 readiness 통과로 오인될 수 있었다.

**조치:** 해당 분모가 없으면 metric을 `null`로 기록하고 threshold condition을 실패시킨다. fixture도 CURRENT와 STALE human label을 모두 포함하도록 보완했다.

### IR-3 — symbolic source revision 허용 가능성

request의 `source_revision`이 단순 non-empty string이라 `HEAD` 같은 이동 가능한 식별자가 stable report identity에 포함될 수 있었다.

**조치:** 기존 Run identity normalization을 재사용해 Git SHA 또는 `sha256:<digest>`만 허용하고 symbolic·`unresolved` revision을 거부한다.

### IR-4 — broken output symlink 우회

초기 symlink 검사는 path component가 존재할 때만 `is_symlink()`를 확인해 broken output symlink를 놓칠 수 있었다.

**조치:** 존재 여부와 무관하게 각 component의 symlink 상태를 확인한다.

### IR-5 — report 생성 검증 오류 exit code

`TrustVerificationError`가 상위 `TrustError` 처리에 먼저 잡히면 report integrity 오류도 input error 3으로 반환될 수 있었다.

**조치:** 검증 오류를 먼저 처리해 exit 4, source/input error는 exit 3으로 분리했다.

### IR-6 — main PIE CLI 실제 위임 회귀 부족

독립 `pie-trust`는 assess·verify 실행 테스트가 있었지만 기존 `pie`·`urs` 경로는 help smoke에 의존했다.

**조치:** `pie trust-assess`와 `pie validate-trust-report`의 실제 생성·검증 위임 테스트를 추가했다.

### IR-7 — duplicate relation 테스트 fixture ID 충돌

CURRENT·STALE 혼합 fixture로 확장한 뒤 duplicate relation 테스트가 기존 observation ID를 재사용해 relation 중복보다 ID 중복이 먼저 검출됐다.

**조치:** 중복 relation fixture의 observation ID를 별도로 부여했다. 제품 동작 변경은 없다.

## 안전성 검토

- Risk Band와 readiness는 합산 Trust Score가 아니라 독립 근거와 조건으로 표시된다.
- 낮은 Task Class 선언은 더 높은 path floor를 낮출 수 없다.
- hard gate는 readiness metric으로 상쇄되지 않는다.
- `READY_FOR_HUMAN_COMPARISON`은 자동 승인 권한이 아니다.
- R0도 이번 단계에서는 `HUMAN_CONFIRMATION_REQUIRED`다.
- Policy와 Evaluation은 active Policy reference가 정확히 일치할 때만 ready evidence가 된다.
- Reground accuracy는 별도 human-confirmed observation만 사용한다.
- human identity와 개별 label은 report에 복제하지 않고 dataset hash와 aggregate metrics만 남긴다.
- report에는 Ledger, Registry, Evaluation, Reground의 절대경로를 기록하지 않는다.
- source replay 없이 source truth가 증명됐다고 주장하지 않는다.
- 기존 Review Gate의 decision·exit code·merge 상태를 변경하지 않는다.

## 남은 제한

- Stage 10B human-confirmed decision comparison은 구현하지 않았다.
- R0 auto-pass pilot과 R1 conditional auto-approval은 시작하지 않았다.
- readiness threshold의 조직 승인·배포 lifecycle은 이번 단계 범위가 아니다.
- observation provenance는 이름과 timestamp를 source dataset에서 검증하지만 서명하지 않는다.
- SHA-256은 integrity를 제공하며 signer identity, encryption과 transport authentication은 제공하지 않는다.
- 중앙 서비스, multi-repository aggregation과 network delivery adapter는 없다.
- override audit와 emergency stop은 이후 단계다.
- Task Class·path classification은 보수적 deterministic policy이며 별도 Policy Registry versioning 대상이 될 수 있다.
- local file과 SQLite cross-process locking은 제공하지 않는다.

## 판정

구현 리뷰: `PASS`

GitHub Actions run `30108052100`에서 Python 3.11·3.13·3.14 전체 regression, 기존 CLI·profile·Finding 검증과 wheel build가 통과했다. 문서 포함 exact HEAD에서 동일 matrix를 재검증한다.
