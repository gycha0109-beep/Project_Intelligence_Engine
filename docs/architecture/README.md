# PIE Architecture Baseline

이 디렉터리는 PIE의 현재 구현과 Control Plane 확장 방향에 대한 권위 기준선을 보존한다.

기준일: 2026-07-23  
기준 브랜치: `main`  
기준 커밋: `c8578aa2c8096b3f0fa7652248c078702a94d023`  
기준 제품 버전: `0.3.0`

## 문서

1. [CURRENT-STATE.md](CURRENT-STATE.md) — 현재 코드·계약·저장·검증 구조
2. [TARGET-STATE.md](TARGET-STATE.md) — 목표 Control Plane과 도메인 모델
3. [GAP-ANALYSIS.md](GAP-ANALYSIS.md) — 현재와 목표 사이의 격차·우선순위
4. [MIGRATION-PLAN.md](MIGRATION-PLAN.md) — 기존 계약을 보존하는 단계별 구현 순서
5. [STAGE-0-VALIDATION.md](STAGE-0-VALIDATION.md) — Stage 0 설계·구현 리뷰와 검증 결과
6. [STAGE-1-APPLICATION-BOUNDARY.md](STAGE-1-APPLICATION-BOUNDARY.md) — AnalyzePullRequest application boundary 설계·리뷰·검증
7. [STAGE-1B-INDEX-ANALYZE-BOUNDARY.md](STAGE-1B-INDEX-ANALYZE-BOUNDARY.md) — IndexProject·AnalyzeChange application boundary 설계·리뷰·검증
8. [STAGE-1C-RULE-GATE-BOUNDARY.md](STAGE-1C-RULE-GATE-BOUNDARY.md) — ApproveRule·CalculateGate application boundary 설계·리뷰·검증

## 권위 규칙

- 실제 코드와 schema가 문서보다 우선한다.
- 문서에 기록된 기준 commit 이후 코드가 변경되면 Current State의 일부는 stale할 수 있다.
- 목표 구조는 한 번에 구현하는 최종 파일 목록이 아니라 책임과 의존성 방향을 고정한다.
- Migration Plan의 각 Stage는 상세 설계와 별도 검증 없이 자동 승인되지 않는다.
- 이전 버전별 설계·구현 보고서는 역사 기록이며, 현재 구조 판단에는 이 디렉터리를 우선한다.

## 현재 진행 상태

- Stage 0: `PASS`, PR #1 검토 대기
- Stage 1A — AnalyzePullRequest Application Boundary: `PASS`, PR #2 검토 대기
- Stage 1B — IndexProject / AnalyzeChange Application Boundaries: `PASS`, PR #4 검토 대기
- Stage 1C — ApproveRule / CalculateGate Application Boundaries: `PASS`, PR #6 검토 대기

## 다음 단계

남은 CLI orchestration을 점검해 Application Boundary Extraction을 동결한 뒤 Evidence Ledger 단계로 진입한다.
