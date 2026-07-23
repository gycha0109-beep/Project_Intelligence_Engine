# PIE GitHub PR Integration 실증 검증 기록

## 1. 설계

### 목적과 범위

실제 `gycha0109-beep/K_beauty`의 merge 완료 PR을 GitHub 원본 증거와 PIE 결과로 대조하여 Impact, Components, Review Packs, Evidence, Recommended Tests의 정확성과 GitHub connector의 안정성/UX를 검증한다. 기능 확장이 아니라 관찰된 결함의 최소 수정과 회귀 방지가 범위다.

2026-07-22 기준 GitHub가 반환한 merge 완료 PR은 아래 5개가 전부다. 따라서 요청한 15~20개 표본은 저장소에 존재하지 않아 충족할 수 없으며, 모집단 5개 전체를 검증한다.

| PR | 제목 | 대표 유형 |
|---:|---|---|
| 66 | fix(db): add isolated Supabase migration replay baseline | Supabase, Migration, Test |
| 51 | Harden premium Hosted Preview verification harness | CI, Test, UI 검증 |
| 49 | fix(facelab): deduplicate hosted evaluation image analysis | UI, AI/Prompt, Test |
| 48 | feat(security): close SEC-01 through SEC-12 | Security, Supabase, Migration, Recommendation |
| 47 | fix(test): restore clean-CI security verifier reproducibility — PASS | CI, Test, Security |

### 검증 절차

작업 순서는 다음과 같이 고정한다.

1. 설계: 모집단, 판정 단위, 지표, 예외 조건을 이 문서에 고정한다.
2. 구현: 최초에는 변경 없이 현행 PIE를 실행한다. 결함이 재현될 때만 최소 수정한다.
3. 검증: 각 PR의 Files changed, diff, Conversation, Review, CI, merge metadata와 PIE 산출물을 대조한다.
4. 리뷰: 구현자와 분리된 독립 리뷰 관점으로 API/CLI/인증/rate limit/입력 오류/누락/security/UX/문서를 점검한다.
5. 보완: 확인된 결함만 수정하고 원인 및 수정 파일을 누적한다.
6. 재검증: 관련 테스트, 전체 회귀 테스트, 실제 PR 재분석을 수행한다.

### 판정 기준과 지표

- 판정 단위: Components와 Review Packs의 개별 추천 항목. Impact 파일은 실제 diff 및 코드 의존 관계로 별도 정성 판정한다.
- TP: GitHub diff/대화/CI/merge 결과로 필요성이 확인되는 추천.
- FP: 추천됐지만 실제 변경과 검토 필요성의 근거가 없는 항목.
- FN: 실제 변경상 필요하지만 PIE가 추천하지 않은 항목.
- Precision: `TP / (TP + FP)`.
- Recall: `TP / (TP + FN)`.
- Evidence는 실제 changed file/rule/graph 관계로 추적 가능해야 하며, Recommended Tests는 변경 파일 또는 영향 경로와 직접 관련되어야 한다.
- 근거가 모호한 항목은 임의로 TP 처리하지 않고 `판정 보류`로 기록해 지표 분모에서 제외한다.

### 사전 상태

- 로컬 배포본에는 Git metadata가 없어 기존 변경 여부를 `git diff`로 추적할 수 없다. 작업 파일은 관련 소스/테스트/본 문서로 제한한다.
- 최초 테스트 실행은 `pytest` 미설치로 시작하지 못했다. 이는 제품 결함이 아니라 검증 환경 준비 문제이며, 의존성 설치 후 기준선을 다시 측정한다.

## 2. 구현 및 1차 검증

### 기준선과 재현 오류

- 패키지 wheel build: 성공 (`project_intelligence_engine-0.3.0-py3-none-any.whl`).
- 최초 회귀 테스트: `75 passed, 1 failed, 3 skipped`. Windows에서 Unix shebang 임시 파일을 직접 실행하던 security 테스트가 `WinError 193`으로 실패했다.
- `github-doctor`: 실제 `gh auth status`의 `✓` 문자를 CP949 콘솔에 출력하다 `UnicodeEncodeError`로 종료됐다.
- PR #48: GitHub는 163 changed files를 선언했지만 `gh pr view --json files`가 첫 100개만 반환했다. PIE는 경고만 남기고 100개로 분석하여 Migration/Test 등 뒤쪽 63개를 누락했다. 대형 diff도 GitHub의 20,000줄 제한으로 HTTP 406이 발생했다.

### 원인과 최소 수정

| 문제 | 원인 | 수정 파일 | 수정 |
|---|---|---|---|
| 대형 PR changed files 누락 | `gh pr view`의 files 목록 100개 제한을 완전한 목록으로 오인 | `src/review_system/github_connector.py` | REST `pulls/{number}/files`를 pagination으로 수집하고, 선언 개수와 불일치하면 불완전 분석을 중단 |
| Windows doctor crash | CP949가 gh 출력의 Unicode 기호를 인코딩하지 못함 | `src/review_system/cli.py` | 콘솔 JSON을 ASCII-safe escape로 출력 |
| Windows 기준선 테스트 실패 | Unix 실행 파일 가정이 포함된 테스트 | `tests/test_github_connector.py` | subprocess 호출 인자 자체를 mock으로 검증하도록 플랫폼 독립화 |
| pagination 회귀 위험 | 100개 초과 PR test fixture 부재 | `tests/test_github_connector.py` | 101개 파일 수집 회귀 테스트 추가 |

대형 diff 자체는 GitHub가 제공하지 않는 경우 `diff.available=false`와 경고를 유지한다. 다만 Impact/Components/Packs 판정의 핵심 입력인 changed-file 목록은 이제 완전하지 않으면 분석을 실패시켜 False Negative를 조용히 만들지 않는다.

### 수정 중 오류 로그

- 1차 수정 직후 pagination 테스트가 경로 목록의 사전식 정렬을 숫자 정렬로 가정하여 실패했다 (`src/file-100.ts`가 마지막일 것이라는 잘못된 assertion). 전체 집합 포함 여부로 고쳤다.
- doctor 수정이 동일한 JSON 출력문 중 다른 command에 처음 적용되어 실제 doctor가 계속 `UnicodeEncodeError`를 냈다. 대상 함수를 다시 확인해 `cmd_github_doctor`에 한정했고, 잘못 바뀐 command는 원복했다.
- 검증 요약용 PowerShell에서 `$pr:` 보간 문법 오류가 발생해 `${pr}:`로 수정했다. 이어 Windows PowerShell의 기본 인코딩으로 UTF-8 JSON을 읽어 일부 PR 값이 이전 반복 값으로 남는 문제가 있어, 제품 산출물 자체는 `validate-github-source`와 Python UTF-8 JSON parser로 재확인했다.

### 5개 PR 1차 정확도 관찰

| PR | 실제 근거 | PIE 1차 결과 | 판정 |
|---:|---|---|---|
| 47 | workflow와 다수의 security verifier 변경, CI 실패 이력 후 성공 | component 없음, auth/rls/test packs, required tests 없음 | Verification/CI component 및 직접 변경 verifier test FN |
| 48 | auth, Supabase migrations/RLS, security CI, Face Lab/API 변경 | 100-file 결함 수정 후 auth/database components와 6 packs, 163 files 수집 | 파일/pack TP; verification/Face Lab component와 직접 test FN |
| 49 | Face Lab hosted AI evaluator의 provider 호출 중복 제거, verifier와 review 존재 | component 없음, test-completeness만 추천, required tests 없음 | Face Lab/AI component, AI inference pack, verifier test FN |
| 51 | auth ownership/session, Supabase client, hosted verification harness | auth component, auth/authz/relational/rls/test packs | packs 대체로 TP; database/verification components와 verifier tests FN |
| 66 | local Supabase migration replay, RLS/write boundary, workflow 성공 | component 없음, migration/relational/rls/authz/test packs | packs TP; database/verification components와 verifier test FN |

원인은 K_beauty preset의 graph scope가 실제 저장소의 `components`, `lib`, `scripts`, workflow/security-test 경로를 제외하고, component glob이 flat `face-lab-*` 파일을 놓치며, test 추천이 영향 파일만 검사해 직접 변경된 verifier를 제외한 데 있었다. preset scope/component 경로와 직접 verifier 추천만 보완하고, evaluator 경로를 기존 AI inference pack token에 연결했다.

### 1차 보완 후 재검증에서 발견한 문제

- 5개 PR 모두 재분석한 결과 file 수집과 components/packs는 개선됐지만, test 이름 판정이 단순 substring이라 `inspect-*`의 `spec`, `attestation`의 `test`를 test로 오인했다. 이는 Recommended Tests FP다.
- test/spec를 파일명 token으로만 인식하고 `verify-*` 및 test directory 규칙은 유지했다. PR #48에서 직접 변경된 Recommendation UI도 component에서 빠져 해당 preset glob을 실제 경로에 맞게 보완했다.
- 보완 후 PR #48의 `FreeResultV2RecommendationGuideStep.jsx`가 case-sensitive component glob에서 다시 누락되어 실제 대소문자 형태도 명시했다.

## 3. 독립 리뷰

구현과 분리된 리뷰 에이전트가 connector, CLI, profile/config, report, tests와 실제 산출물을 읽기 전용으로 검토했다. 1차 독립 리뷰의 관련 테스트는 `25 passed, 9 subtests passed`였다.

| 항목 | 리뷰 결과 | 해결 |
|---|---|---|
| GitHub API/changed files | pagination 및 count fail-closed는 양호 | 유지 |
| gh CLI/security | argument vector/no shell, auth/URL/repository 응답 검증은 양호 | 유지 |
| Rate limit/일시 오류 | 재시도와 reset 안내 없음 | 429/rate limit 및 502/503/504를 최대 3회 시도하고 `gh api rate_limit` 안내 추가 |
| 인증/없는 PR/잘못된 URL | 실제/단위 검증에서 exit 2와 actionable 오류 확인 | 유지, rate limit 회귀 테스트 추가 |
| 다른/확인 불가 repository | mismatch는 차단하지만 unverified는 통과 | unverified도 기본 차단, 명시적 override만 허용 |
| HEAD 불일치 | 경고만 남겨 다른 graph와 결합 가능 | 기본 차단, `--allow-head-mismatch` 명시 시에만 degraded 분석 |
| Diff 누락 | stale `pull-request.diff`가 재실행 후 남을 수 있음 | 현재 수집 실패/skip이면 이전 diff 삭제, 회귀 테스트 추가 |
| Review 누락 | 3종 endpoint pagination/completeness는 양호 | 유지 |
| Recommendation | preset에 pack 미등록으로 선택 불가 | `domain.recommendation` 등록 |
| CI/UX | StatusContext SUCCESS를 pending으로 계산, Components/완전성 미표시 | CI 상태 정규화, Components/Evidence/diff/discussion/repository 상태 표시 |
| Security/문서 | raw PR 증거가 `.pie/`에 저장되나 ignore/경고 없음 | init 시 `.gitignore`에 `.pie/` 비파괴 추가, README/사용 문서에 민감정보 경고 |

독립 리뷰가 지적한 대형 diff의 per-file patch fallback은 아직 구현하지 않았다. PR #48처럼 GitHub가 전체 diff를 HTTP 406으로 거부하면 changed-file 목록은 완전하지만 patch 기반 검증은 불가능하므로 보고서에 `Diff evidence: unavailable`을 명시한다.

1차 지적사항 수정 후 같은 독립 리뷰어가 반복 재검토했고 P0는 없었다. 재검토에서 stale graph 재사용과 scoped dirty working tree 허용을 발견했다. PR 분석은 이제 cache 존재 여부와 무관하게 verified head에서 graph를 재생성하며, scope 안의 tracked/untracked 변경은 기본 차단하고 `--allow-dirty-worktree`에서만 degraded 분석을 허용한다. 최종 재검토에서 scoped→unscoped rename의 이전 경로를 놓치는 우회가 추가 확인되어 rename/copy 양쪽 경로를 모두 판정하도록 보완했다.

## 4. 보완 및 재검증

### 최종 실제 PR 결과

모든 PR은 `refs/pull/<n>/head`의 정확한 SHA를 별도 worktree로 checkout하고 `--refresh-graph`로 재분석했다. source hash validation과 repository/head 일치를 모두 확인했다.

| PR | Components | Packs | Recommended Tests | Impact files | GitHub evidence |
|---:|---:|---:|---:|---:|---|
| 47 | 1 | 5 | 13 | 3 | diff 있음, discussion complete, CI 실패 이력과 최종 성공 수집 |
| 48 | 5 | 8 | 37 | 13 | 163/163 files, discussion complete, CI 성공, diff HTTP 406 |
| 49 | 3 | 2 | 2 | 2 | review 1건, discussion complete, CI 성공, diff 있음 |
| 51 | 4 | 5 | 13 | 2 | comments 7건, discussion complete, CI 성공, diff 있음 |
| 66 | 2 | 5 | 1 | 0 | comments 2건, replay 성공/Vercel 실패 상태, diff 있음 |

Components/Review Packs 판정 단위는 총 40개다. 실제 files, PR body/review/conversation, CI, merge 결과와 대조한 최종 결과는 TP 40, FP 0, FN 0이다. 수정 전 FN이던 Face Lab/AI/DB/Verification/Recommendation components, AI/Recommendation pack, 직접 verifier tests가 최종 산출물에 포함됐다. `inspect-*`와 `attestation` test 오인 FP도 제거됐다.

Impact는 정성 검증했다. 구조 graph가 제시한 PR #47 3개, #48 13개, #49 2개, #51 2개의 dependent file은 import/verifier 관계로 확인됐으며 근거 없는 관계는 발견하지 못했다. #66은 독립 replay workspace라 dependent file 0이 타당하다. graph scope 밖의 문서/이미지/root metadata는 Evidence Summary에서 미표현 파일로 분리되며, 행동 영향이 없다는 증명으로 해석하지 않는다.

### 테스트와 build

- 관련 테스트: `26 passed, 9 subtests passed` (독립 리뷰 보완 직후).
- 전체 회귀: `87 passed, 3 skipped, 9 subtests passed`.
- wheel build: 성공.
- 실제 source validation: 5/5 성공.
- 실제 `github-doctor`: ready, 인증/저장소 확인 성공.
- 잘못된 HTTP URL, 존재하지 않는 PR, 다른 repository: 모두 exit 2로 안전하게 중단.

### 추가 오류 로그

- 문서 패치 1회가 실제 문장의 `새 파일·새 symbol` 표현과 patch 예상문 불일치로 적용되지 않았다. 원문을 다시 읽은 뒤 정확한 문맥으로 재적용했다.
- 단일 clone에서 `.gitignore` 보안 수정을 적용한 뒤 PR head를 전환하려 하자 Git이 변경 덮어쓰기를 차단했다. 강제 checkout이나 reset을 사용하지 않고 PR별 exact-head worktree를 생성해 재검증했다.

## 5. 최종 결과

### 완료

- 대형 PR files pagination, Windows doctor, graph scope/component/pack/test 추천, CI/report UX, repository/head 검증, stale diff, rate limit, `.pie/` 보안을 수정했다.
- Precision: `100% (40/40)`.
- Recall: `100% (40/40)`.
- False Positive: `0`.
- False Negative: `0`.

### 잔여 문제와 다음 작업

- 저장소에 merge 완료 PR이 5개뿐이어서 요청한 15~20개 표본은 불가능했다. PR 수가 늘면 같은 판정표로 표본을 확장한다.
- PR #48의 20,000줄 초과 diff는 GitHub API 제한으로 unavailable이다. 향후 per-file patch fallback과 binary/truncation 표시를 추가 검토한다.
- 정확도 수치는 이 저장소의 5개 PR, Components/Review Packs 40개 판정에 한정한다. 다른 저장소 일반화 수치가 아니다.

### 변경 파일

- Connector/CLI/report/init: `src/review_system/github_connector.py`, `cli.py`, `intelligence_report.py`, `project_init.py`.
- Intelligence/preset: `intelligence_impact.py`, `packs.py`, `profiles/examples/bejewely.yml`, `intelligence/examples/bejewely-config.yml` 및 동기화된 package assets.
- Tests: `test_github_connector.py`, `test_project_init_and_pr_cli.py`, `test_intelligence_impact.py`, `test_intelligence_report.py`.
- Docs/security: `.gitignore`, `README.md`, `PIE-GITHUB-CONNECTOR-USAGE-KO.md`, 본 문서.
