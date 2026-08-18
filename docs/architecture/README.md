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
9. [STAGE-2A-GITHUB-TARGET-EXTRACTION.md](STAGE-2A-GITHUB-TARGET-EXTRACTION.md) — GitHub target·repository parser 분리 설계·리뷰·검증
10. [STAGE-2B-GITHUB-RUNNER-EXTRACTION.md](STAGE-2B-GITHUB-RUNNER-EXTRACTION.md) — GitHub CLI runner·retry 분리 설계·리뷰·검증
11. [STAGE-2C-REPOSITORY-BINDING.md](STAGE-2C-REPOSITORY-BINDING.md) — repository binding 설계·설계 리뷰
12. [STAGE-2C-IMPLEMENTATION-REVIEW.md](STAGE-2C-IMPLEMENTATION-REVIEW.md) — Stage 2C 구현 리뷰
13. [STAGE-2C-VALIDATION.md](STAGE-2C-VALIDATION.md) — Stage 2C 검증 결과
14. [STAGE-2D-COLLECTOR-BOUNDARIES.md](STAGE-2D-COLLECTOR-BOUNDARIES.md) — PR collector·pagination·discussion·source 조립 분리 설계
15. [STAGE-2D-IMPLEMENTATION-REVIEW.md](STAGE-2D-IMPLEMENTATION-REVIEW.md) — Stage 2D 구현 리뷰
16. [STAGE-2D-VALIDATION.md](STAGE-2D-VALIDATION.md) — Stage 2D 검증 결과
17. [STAGE-3-RUN-ARTIFACT-IDENTITY.md](STAGE-3-RUN-ARTIFACT-IDENTITY.md) — Run·Artifact identity 상세 설계와 설계 리뷰
18. [STAGE-3-IMPLEMENTATION-REVIEW.md](STAGE-3-IMPLEMENTATION-REVIEW.md) — Stage 3 구현 리뷰
19. [STAGE-3-VALIDATION.md](STAGE-3-VALIDATION.md) — Stage 3 검증 결과
20. [STAGE-4-EVIDENCE-LEDGER-FOUNDATION.md](STAGE-4-EVIDENCE-LEDGER-FOUNDATION.md) — SQLite Ledger schema·migration·import·rebuild 설계
21. [STAGE-4-IMPLEMENTATION-REVIEW.md](STAGE-4-IMPLEMENTATION-REVIEW.md) — Stage 4 구현 리뷰와 보완
22. [STAGE-4-VALIDATION.md](STAGE-4-VALIDATION.md) — Stage 4 검증 결과
23. [STAGE-5-DEFECT-REGISTRY.md](STAGE-5-DEFECT-REGISTRY.md) — Finding·Defect identity·lifecycle·registry 설계
24. [STAGE-5-IMPLEMENTATION-REVIEW.md](STAGE-5-IMPLEMENTATION-REVIEW.md) — Stage 5 구현 리뷰와 보완
25. [STAGE-5-VALIDATION.md](STAGE-5-VALIDATION.md) — Stage 5 검증 결과
26. [STAGE-6-EVALUATION-LAB.md](STAGE-6-EVALUATION-LAB.md) — Dataset·baseline/challenger·metric·Gate·report 설계
27. [STAGE-6-IMPLEMENTATION-REVIEW.md](STAGE-6-IMPLEMENTATION-REVIEW.md) — Stage 6 구현 리뷰와 보완
28. [STAGE-6-VALIDATION.md](STAGE-6-VALIDATION.md) — Stage 6 검증 결과
29. [STAGE-7-POLICY-REGISTRY.md](STAGE-7-POLICY-REGISTRY.md) — version·parent·evaluation·lifecycle Policy Registry 설계
30. [STAGE-7-IMPLEMENTATION-REVIEW.md](STAGE-7-IMPLEMENTATION-REVIEW.md) — Stage 7 구현 리뷰와 보완
31. [STAGE-7-VALIDATION.md](STAGE-7-VALIDATION.md) — Stage 7 검증 결과
32. [STAGE-8-REGROUND-FOUNDATION.md](STAGE-8-REGROUND-FOUNDATION.md) — Graph·Ledger freshness와 impacted recheck 설계
33. [STAGE-8-IMPLEMENTATION-REVIEW.md](STAGE-8-IMPLEMENTATION-REVIEW.md) — Stage 8 구현 리뷰와 보완
34. [STAGE-8-VALIDATION.md](STAGE-8-VALIDATION.md) — Stage 8 검증 결과
35. [STAGE-9-BUILDMAP-EXPORT.md](STAGE-9-BUILDMAP-EXPORT.md) — BuildMap metadata reference export와 redaction 설계
36. [STAGE-9-IMPLEMENTATION-REVIEW.md](STAGE-9-IMPLEMENTATION-REVIEW.md) — Stage 9 구현 리뷰와 보완
37. [STAGE-9-VALIDATION.md](STAGE-9-VALIDATION.md) — Stage 9 검증 결과
38. [STAGE-10A-TRUST-GATE-READINESS.md](STAGE-10A-TRUST-GATE-READINESS.md) — report-only Risk Band와 readiness evidence 설계
39. [STAGE-10A-IMPLEMENTATION-REVIEW.md](STAGE-10A-IMPLEMENTATION-REVIEW.md) — Stage 10A 구현 리뷰와 보완
40. [STAGE-10A-VALIDATION.md](STAGE-10A-VALIDATION.md) — Stage 10A 검증 결과
41. [STAGE-10B-DECISION-OUTCOME-AUDIT.md](STAGE-10B-DECISION-OUTCOME-AUDIT.md) — 사람 decision 수준과 Outcome Audit Registry 설계
42. [STAGE-10B-IMPLEMENTATION-REVIEW.md](STAGE-10B-IMPLEMENTATION-REVIEW.md) — Stage 10B 구현 리뷰와 보완
43. [STAGE-10B-VALIDATION.md](STAGE-10B-VALIDATION.md) — Stage 10B 검증 결과
44. [STAGE-10D-OPERATING-OBSERVATION-THRESHOLD-POLICY.md](STAGE-10D-OPERATING-OBSERVATION-THRESHOLD-POLICY.md) — R0 operating observation과 threshold policy 설계
45. [STAGE-10D-IMPLEMENTATION-REVIEW.md](STAGE-10D-IMPLEMENTATION-REVIEW.md) — Stage 10D 구현 리뷰와 안전 경계
46. [STAGE-10D-VALIDATION.md](STAGE-10D-VALIDATION.md) — Stage 10D 검증 결과
47. [STAGE-10C-SOURCE-OUTCOME-RECONCILIATION.md](STAGE-10C-SOURCE-OUTCOME-RECONCILIATION.md) — Trust source replay와 Outcome authority reconciliation 설계
48. [STAGE-10C-IMPLEMENTATION-REVIEW.md](STAGE-10C-IMPLEMENTATION-REVIEW.md) — Stage 10C 구현 리뷰와 temporal/source hardening
49. [STAGE-10C-VALIDATION.md](STAGE-10C-VALIDATION.md) — Stage 10C focused/full regression 검증 결과
50. [STAGE-10E-R0-PILOT-SAFETY-REVIEW.md](STAGE-10E-R0-PILOT-SAFETY-REVIEW.md) — Stage 10B/10C/10D evidence를 결합하는 report-only R0 pilot safety gate 설계
51. [STAGE-10E-IMPLEMENTATION-REVIEW.md](STAGE-10E-IMPLEMENTATION-REVIEW.md) — Stage 10E 구현 리뷰, authority composition, fail-closed hardening
52. [STAGE-10E-VALIDATION.md](STAGE-10E-VALIDATION.md) — Stage 10E focused/full regression 검증 범위와 safety interpretation
53. [STAGE-10F-INDEPENDENT-AUDIT-AUTHORITY.md](STAGE-10F-INDEPENDENT-AUDIT-AUTHORITY.md) — repository-backed Independent Audit Trust Root·Issuer Grant·Artifact authority 설계
54. [STAGE-10F-IMPLEMENTATION-REVIEW.md](STAGE-10F-IMPLEMENTATION-REVIEW.md) — Stage 10F 구현 리뷰, temporal/replay/rehash hardening
55. [STAGE-10F-VALIDATION.md](STAGE-10F-VALIDATION.md) — Stage 10F focused/integration/full regression 검증 범위
56. [STAGE-10G-R0-PILOT-ELIGIBILITY-EVIDENCE-RUN.md](STAGE-10G-R0-PILOT-ELIGIBILITY-EVIDENCE-RUN.md) — 실제 evidence package inventory와 Stage 10E exact replay 실행 계약
57. [STAGE-10G-IMPLEMENTATION-REVIEW.md](STAGE-10G-IMPLEMENTATION-REVIEW.md) — Stage 10G evidence/runtime boundary와 fail-closed 구현 리뷰
58. [STAGE-10G-VALIDATION.md](STAGE-10G-VALIDATION.md) — Stage 10G focused/full regression 및 committed-evidence 해석
59. [STAGE-10H-R0-EVIDENCE-ACQUISITION.md](STAGE-10H-R0-EVIDENCE-ACQUISITION.md) — 실제 runtime evidence acquisition workspace와 package population 계약
60. [STAGE-10H-IMPLEMENTATION-REVIEW.md](STAGE-10H-IMPLEMENTATION-REVIEW.md) — Stage 10H source-closure, replay, publication hardening 리뷰
61. [STAGE-10H-VALIDATION.md](STAGE-10H-VALIDATION.md) — Stage 10H implementation 검증과 external-evidence blocker 해석

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
- Stage 2A — GitHub Target Parsing Extraction: `PASS`, PR #7 검토 대기
- Stage 2B — GitHub CLI Runner Extraction: `PASS`, PR #8 검토 대기
- Stage 2C — Repository Binding Extraction: `PASS`, PR #9 검토 대기
- Stage 2D — Collector Boundary Extraction: `PASS`, PR #10 검토 대기
- Stage 3 — Run and Artifact Identity: `PASS`, PR #11 검토 대기
- Stage 4 — Evidence Ledger Foundation: `PASS`, PR #12 검토 대기
- Stage 5 — Defect Registry: `PASS`, PR #13 검토 대기
- Stage 6 — Evaluation Lab: `PASS`, PR #14 검토 대기
- Stage 7 — Policy Registry: `PASS`, PR #15 검토 대기
- Stage 8 — Reground Foundation: `PASS`, PR #16 검토 대기
- Stage 9 — BuildMap Export: `PASS`, PR #17 검토 대기
- Stage 10A — Trust Gate Readiness: `PASS`, PR #18 검토 대기
- Stage 10B — Decision Comparison & Outcome Audit Foundation: `PASS`, PR #19 Ready / unmerged
- Stage 10D — Operating Observation & Threshold Policy: `PASS`, PR #20 Ready / unmerged
- Stage 10C — Source Replay & Outcome Reconciliation: `PASS`, PR #21 merged into Stage 10D stacked branch
- Stage 10E — R0 Pilot Safety Review: `PASS`, PR #22 merged into Stage 10D stacked branch; merge commit `3614442ba0797e8b26f65daa7c9879ff8caa3934`
- Stage 10F — Independent Audit Authority Contract: `PASS`, PR #23 merged into Stage 10D stacked branch; merge commit `35697b32c1bc751b4831ea92756db44495e6c792`
- Stage 10G — R0 Pilot Eligibility Evidence Run: `PASS`, PR #24 merged into Stage 10D stacked branch; merge commit `0b705a5d9ca2dddd3e4e77bc7ddcd3f99417b5df`
- Stage 10H — R0 Evidence Acquisition & Runtime Package Population: implementation on PR #25; runtime acquisition currently `BLOCKED_EXTERNAL_EVIDENCE_REQUIRED`

## Stage 10G evidence boundary

Stage 10G does not manufacture evidence required to pass Stage 10E. It inventories a supplied evidence root and only invokes the existing authority-aware Stage 10E path when the package is complete.

Canonical top-level package:

```text
comparison-registry.json
reconciliation-sources.json
reconciliation-report.json
observation-policy.json
observation-report.json
```

The Stage 10G start snapshot contains no committed R0 evidence package. However `.pie/` and `.review-runs/` are gitignored, so this only establishes committed-repository absence, not global runtime-evidence absence.

## Stage 10H acquisition boundary

Stage 10H does not convert workflow acceptance into safety evidence and does not use samples as runtime truth. A genuine acquisition workspace must provide:

```text
acquisition-attestation.json
comparison-registry.json
reconciliation-sources.json
observation-policy.json
<full reconciliation source closure>
```

Stage 10H regenerates reconciliation and observation reports, runs Stage 10G in staging, binds every package byte in a path/SHA manifest, and publishes only after exact source replay succeeds.

Current connected authority surfaces do not contain that genuine workspace, so runtime acquisition remains:

```text
BLOCKED_EXTERNAL_EVIDENCE_REQUIRED
```

This is distinct from Stage 10H implementation status.

Only a real package whose Stage 10G exact replay reaches:

```text
ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

may proceed to a separately designed activation contract.

그 전까지 다음 고정값은 변경하지 않는다.

```text
automation_authorized=false
pilot_authorized=false
```

실제 pilot activation은 별도 `R0 Pilot Activation Contract`와 명시적 사람 승인 이후에만 가능하다.
