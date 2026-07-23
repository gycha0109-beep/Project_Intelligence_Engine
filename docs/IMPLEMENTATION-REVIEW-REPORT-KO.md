# Project Intelligence Engine v0.2.0 구현·자체 리뷰 보고

## 1. 구현 결과

Universal Review System v0.1.1을 보존하면서 다음 계층을 추가했습니다.

- Project State capture
- 정적 Project Graph
- Change Impact Analyzer
- Parallel Change Comparator
- Review Pack routing integration
- Co-change Learning Candidate Engine
- Human Approval lifecycle
- JSON·Markdown reporting
- Bejewely component·candidate rule 예시

기존 `urs` 명령은 유지하고 새 기본 명령 `pie`를 추가했습니다.

## 2. 주요 구현 파일

```text
src/review_system/intelligence_config.py
src/review_system/intelligence_graph.py
src/review_system/intelligence_impact.py
src/review_system/intelligence_learning.py
src/review_system/intelligence_report.py
src/review_system/intelligence_state.py
schemas/intelligence-config.schema.json
schemas/project-rule.schema.json
bootstrap/.review/intelligence/*
intelligence/examples/*
tests/test_intelligence_*.py
```

## 3. 자체 리뷰에서 발견·해결한 문제

### PIE-R1 — 경로 정규화와 symlink alias

초기 구현은 일부 상대 경로 표현을 과도하게 정규화할 여지가 있었고, 저장소 내부를 가리키는 symlink alias가 중복 색인될 수 있었습니다.

조치:

- 절대 경로와 `..` 이탈 차단
- include·exclude·rule pattern 검증
- 경로 구성 요소 중 symlink가 있으면 색인 제외
- 외부·내부 symlink 회귀 테스트 추가

상태: **RESOLVED**

### PIE-R2 — 그래프 변조 검증 부재

초기 그래프는 해시를 생성했지만 분석 직전 무결성을 강제하지 않았습니다.

조치:

- canonical JSON 기반 `graph_sha256`
- `validate-graph` 추가
- `analyze-change`가 해시 불일치 시 중단
- 변조 회귀 테스트 추가

상태: **RESOLVED**

### PIE-R3 — 승인 규칙이 Profile 밖 Pack을 선택할 가능성

승인 규칙의 Pack이 프로젝트 Profile에 설정되지 않아도 선택될 수 있었습니다.

조치:

- Profile에 구성된 Pack만 선택
- 나머지는 `unconfigured_rule_packs`로 별도 보고

상태: **RESOLVED**

### PIE-R4 — 승인 규칙이 구조 그래프 근거를 덮어씀

같은 파일이 구조 그래프와 승인 규칙 양쪽에서 탐지되면 규칙 근거만 남았습니다.

조치:

- `sources[]`에 복수 근거 보존
- `structural_graph+approved_rule`로 병합 표시

상태: **RESOLVED**

### PIE-R5 — 검증 결과 XML을 실행 테스트로 오추천

규칙이 `verification/**`를 영향 범위로 지정하면 XML 테스트 결과까지 `required_tests`로 승격됐습니다.

조치:

- 실행 가능한 언어의 실제 test/spec source만 자동 추천
- 명시된 테스트 명령은 그대로 보존

상태: **RESOLVED**

### PIE-R6 — 파일명 기반 테스트 연결을 확정 사실로 분류

동일 stem 기반 테스트 연결은 heuristic인데 `verifies`로 강하게 표현됐습니다.

조치:

- 관계를 `likely_verifies`로 변경
- confidence 0.60
- evidence classification을 `inferred_structure`로 분리

상태: **RESOLVED**

### PIE-R7 — 후보 재탐색 시 사람의 승인·거절 이력 손실 가능성

후보 파일을 새 결과로 덮어쓰면 이전 결정이 사라질 수 있었습니다.

조치:

- stable candidate ID
- 승인·거절·폐기 상태 보존
- 최신 관측값은 `latest_observation`으로 누적

상태: **RESOLVED**

### PIE-R8 — 두 승인 파일의 부분 저장 위험

candidate와 approved 파일을 순차 저장하면 중간 실패 시 상태가 갈릴 수 있었습니다.

조치:

- approval lock
- 동일 디렉터리 임시 파일과 fsync
- pair update rollback

상태: **RESOLVED**

### PIE-R9 — 병렬 변경의 교차 도메인 관계 누락

P2 Core와 P2 DB처럼 파일·component가 분리되어도 동일한 도메인 Review Pack으로 수렴할 수 있는데 초기 비교기는 이를 `none`으로 처리했습니다.

조치:

- `review_packs`와 `matched_rules` overlap 추가
- domain Pack overlap에 더 높은 가중치 부여
- P2 Core ↔ P2 DB를 `medium`으로 재검증

상태: **RESOLVED**

## 4. 검증

- 기존 URS 회귀 + 신규 intelligence 테스트: **67/67 PASS**
- Python compileall: PASS
- Project Graph 변조 탐지: PASS
- 외부·내부 symlink 차단: PASS
- unsafe glob·path traversal 차단: PASS
- 후보 승인·거절 이력 보존: PASS
- Profile 밖 Pack 격리: PASS
- CLI index → validate → analyze E2E: PASS
- Wheel 비편집 설치: PASS
- 설치본 `pie`·`urs` 버전 0.2.0: PASS
- 설치본 내 schema·Bejewely example asset: PASS
- 설치본 index → validate → analyze E2E: PASS

Journey Connect P2 Reviewed ZIP 스모크:

- 색인 대상: **661개 파일**
- 그래프 관계: **3,839개**
- P2EvaluationEngine 변경 입력 인식: PASS
- Java import 기반 backend service 직접 영향 탐지: PASS
- 승인 규칙과 구조 근거 동시 보존: PASS
- Review Pack 3개 선택: PASS
- XML test-report 오추천 제거: PASS
- P2 Core ↔ canonical DB 공통 Review Pack 관계 탐지: MEDIUM

## 5. 현재 한계

- 정적 import와 규칙 기반이므로 reflection, runtime routing, generated code, external service 관계는 누락될 수 있습니다.
- JavaScript·TypeScript·Java·Kotlin 일부 추출은 완전한 compiler frontend가 아니라 보수적 정적 추출입니다.
- 공동 변경 규칙 후보는 인과 관계가 아닙니다.
- 실제 Bejewely Git history와 병렬 PR 전체를 아직 입력하지 않았습니다.
- GitHub PR 자동 수집·코멘트·Merge Gate 게시 기능은 없습니다.
- 추천 테스트를 자동 실행하지 않습니다.

## 6. 판정

**v0.2.0 기능 기준선: PASS**

단, Bejewely 실전 적용 기준선은 별도입니다. 실제 저장소와 PR 이력이 제공된 뒤 탐지율·오탐률을 측정해야 하며, 그 전까지 Advisory Mode가 적절합니다.
