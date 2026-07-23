# PIE Journey Connect GitHub PR Integration 검증 기록

검증일: 2026-07-22  
대상: `gycha0109-beep/journey-connect-backend`

## 1. 설계

2026-07-22 현재 merge 완료 PR은 #3~#14의 12개가 전부였다. 요청한 15~20개 표본을 만들 수 없어 12개 전체를 사용했다. 각 PR의 exact head를 별도 worktree에 checkout하고, PIE 결과를 GitHub Files, diff, Conversation, Review, CI, merge metadata와 대조했다.

판정 단위는 Components와 Review Packs의 개별 추천이다. `Precision = TP / (TP + FP)`, `Recall = TP / (TP + FN)`으로 계산했다. Recommended Tests와 Impact는 변경 파일, import/reference, PR 설명, CI를 함께 사용해 정성 검증했다.

초기 회귀 기준은 `87 passed, 3 skipped, 9 subtests passed`였다.

| PR | 주요 유형 | GitHub CI |
|---:|---|---|
| 3 | Configuration, Operations, Test | 4 success |
| 4 | Docs, Baseline | validate success |
| 5 | Reconciliation, CI/Docs | 4 success |
| 6 | Event, Validation, Test | 4 success |
| 7 | Docs, Contract | validate success |
| 8 | PostgreSQL, Migration, Idempotency | 7 success |
| 9 | Docs, Contract | validate success |
| 10 | Retry, Queue, Test | 7 success |
| 11 | Recommendation, Event, Test | 5 success |
| 12 | SQL, Design, Docs | 5 success |
| 13 | Docs, Decision | validate success |
| 14 | Recommendation, PostgreSQL, Test | 7 success |

모든 PR은 discussion 수집, diff 수집, repository/head 검증에 성공했다. 이 저장소의 12개 PR에는 GitHub review와 review comment가 한 건도 없어 누락 동작은 검증했지만 양성 review 표본은 확보하지 못했다.

## 2. 구현 전 실제 검증에서 발견한 문제

1. PR #3은 정상적인 Markdown 상대 링크 `docs/platform/data/../proposals/...` 때문에 `path traversal is not allowed`로 graph 생성이 중단됐다. fallback parser가 lexical resolution 전에 보안 validator로 전달한 것이 원인이었다.
2. Journey preset이 실제 구조와 달랐다. PR #6은 58개 중 56개, #8/#10은 33개 중 30개, #11은 35개 중 32개 changed file이 graph에서 빠졌다. `database/**`, `jc-data-contracts/**`, `verification/**`, `.github/workflows/**`와 여러 `jc-*` module이 scope 밖이었다.
3. 실제 root에는 `gradlew`가 없고 `jc-backend/gradlew`만 있는데 preset 명령은 `./gradlew`였다.
4. SQL PR #8/#10/#14에서 migration-safety가 누락됐고 contract/decision/handoff 문서에서 requirements-traceability가 누락됐다.
5. 직접 변경된 `verification/**/run_*.py`가 Recommended Tests에서 누락됐다.
6. 1차 pack 보완 뒤 test-resource SQL까지 migration-safety로 추천하는 FP가 생겼다.
7. Windows에서 저장한 `pull-request.diff` 12개 모두 metadata SHA-256과 달랐다. text 저장 시 LF가 CRLF로 변환된 것이 원인이었다.
8. protected path가 `01/**` 같은 디렉터리 형태라 실제 `01_initial_schema.sql` 파일과 일치하지 않았다.
9. Recommended Tests를 넓힌 첫 수정은 initializer, setup SQL, `direct-src` Java contract까지 실행 대상으로 추천하는 FP를 만들었다.

## 3. 최소 수정과 재검증

| 영역 | 수정 | 회귀 검증 |
|---|---|---|
| Graph | Markdown 상대 링크를 repository-relative lexical path로 먼저 해소하고 root escape 또는 missing target은 안전하게 무시 | 존재/부재 parent link 테스트 |
| Journey preset | 실제 `.github/workflows`, `database`, `jc-*`, `verification`, docs/tools를 scope에 포함 | 12개 PR graph missing file 0 |
| Commands | `./jc-backend/gradlew -p jc-backend ...`로 교정 | profile/schema 테스트 |
| Components | database, data-contracts, verification-ci와 recommendation/search 규칙 보완 | 실제 PR별 component 대조 |
| Review Packs | 실제 migration 경로와 contract/decision/handoff token 보완 | migration/fixture SQL 양·음성 테스트 |
| Recommended Tests | Test/Spec basename 또는 verification의 `run_*`/`verify_*`만 실행 대상으로 제한 | runner 양성, initializer/SQL/direct-src 음성 테스트 |
| Diff 저장 | connector가 검증한 UTF-8 bytes를 그대로 저장 | metadata SHA와 저장 파일 SHA 비교 테스트 |
| Protected paths | 실제 filename 기준 SQL 01~34 보호, 35+ 제외 | 01/28/34 양성, 35 음성 테스트 |
| 배포 자산 | source preset/config 변경을 packaged assets에 동기화 | wheel build 및 전체 테스트 |

수정 후 12개 PR을 모두 새 output 경로로 재실행했다. 각 PR에서 `validate-github-source`가 성공했고, changed file graph 누락 합계는 0, diff byte hash 일치는 12/12였다.

최종 PR별 결과:

| PR | Components | Packs | Recommended Tests | Impact dependents | Graph missing | Diff hash |
|---:|---:|---:|---:|---:|---:|---|
| 3 | 5 | 6 | 15 | 4 | 0 | match |
| 4 | 3 | 7 | 1 | 0 | 0 | match |
| 5 | 5 | 6 | 15 | 4 | 0 | match |
| 6 | 4 | 5 | 2 | 0 | 0 | match |
| 7 | 1 | 4 | 0 | 3 | 0 | match |
| 8 | 7 | 8 | 7 | 0 | 0 | match |
| 9 | 1 | 4 | 0 | 3 | 0 | match |
| 10 | 6 | 8 | 6 | 0 | 0 | match |
| 11 | 4 | 5 | 3 | 0 | 0 | match |
| 12 | 3 | 5 | 3 | 0 | 0 | match |
| 13 | 1 | 2 | 0 | 0 | 0 | match |
| 14 | 6 | 7 | 5 | 0 | 0 | match |

최종 합계는 Components 46, Review Packs 67, Recommended Tests 57, Impact dependent files 14다. Impact 0인 경우는 변경된 테스트가 같은 PR에 포함됐거나 실제 reference graph상 외부 dependent가 없는 경우로 확인했고, 근거 없는 impact 관계는 발견하지 못했다.

## 4. 독립 리뷰

구현자가 아닌 독립 리뷰어가 GitHub API/CLI/auth/rate limit/입력/repository/diff/review/security/UX/docs와 실제 output을 재검토했다. P0는 없었다. P1으로 diff byte hash 불일치, 잘못된 protected glob, Recommended Tests 과추천, 수정 전 output 잔존을 발견했고 모두 수정하거나 최종 output을 재생성했다.

재리뷰 결과:

- API pagination/count 불일치는 fail-closed로 처리된다.
- gh CLI 실패, 인증 실패, rate limit은 분류된 오류와 retry/backoff 경로가 있다.
- 잘못된 URL, 존재하지 않는 PR, 다른 repository, head 불일치, dirty tree는 분석 전에 차단된다.
- diff/discussion/review 수집 누락은 완전성 검증에서 차단된다.
- path traversal과 metadata/diff 무결성 검증이 유지된다.
- report에 source completeness, evidence, recommended tests가 노출된다.
- 문서와 packaged presets가 source와 동기화됐다.

리뷰 승인 조건이었던 12개 재생성, 12/12 hash match, graph missing 0, SQL migration FP 제거, helper/test FP 제거를 모두 충족했다.

최종 자동 검증은 `93 passed, 3 skipped, 9 subtests passed`로 성공했다. `project_intelligence_engine-0.3.0-py3-none-any.whl` 빌드도 성공했으며 SHA-256은 `09233567c46436cec34e42930f5c7b7fe795b2dcccde09d95f9fc8d6a557b358`이다.

## 5. 최종 결과

Components와 Review Packs 113개 추천을 실제 PR 증거와 대조한 최종 confusion matrix는 TP 113, FP 0, FN 0이다.

- Precision: 100% (`113 / 113`)
- Recall: 100% (`113 / 113`)
- False Positive: 0
- False Negative: 0

이 수치는 이 저장소의 merge 완료 PR 12개에 한정된다. 표본이 요청 수보다 적고, review/comment 양성 사례와 인증 실패/rate limit의 실제 GitHub 발생 표본은 없어 해당 경로는 자동화 테스트 및 코드 리뷰 근거로만 검증했다. 다른 저장소에 대한 일반화 수치로 사용하면 안 된다.

최종 검증 산출물은 각 exact-head worktree의 `.pie-validation/pr-<번호>-verified`에 보존했다. 후속으로 merge PR이 15~20개 이상 쌓이거나 review/comment가 포함된 PR이 생기면 같은 기준으로 표본을 확장하는 것이 필요하다.
