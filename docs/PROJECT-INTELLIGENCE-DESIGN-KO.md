# Project Intelligence Engine v0.2 설계 기준선

## 1. 정의

Project Intelligence Engine은 코드, 문서, 프로젝트 규칙, 변경 이력, 검증 증거와 사람의 결정을 연결하여 **현재 변경의 영향과 필요한 검토 범위**를 산출하는 개발 운영 지능 계층입니다.

CI는 빌드·테스트·스캔을 실행합니다. 이 엔진은 CI를 대체하지 않고 다음을 판단합니다.

- 무엇이 직접 변경됐는가
- 정적 구조상 어떤 파일이 변경된 요소를 사용하거나 검증하는가
- 승인된 프로젝트 규칙상 어디를 함께 검토해야 하는가
- 병렬 변경끼리 어떤 근거로 겹치는가
- 과거 공동 변경 패턴이 새 규칙 후보로 볼 가치가 있는가

## 2. 지식 분류

| 분류 | 출처 | 용도 |
|---|---|---|
| Confirmed change | Git diff 또는 명시적 파일 목록 | 직접 변경 |
| Confirmed structure | 파싱된 import, 선언, SQL 참조 | 영향 분석 |
| Inferred structure | 파일명 기반 테스트 연결 등 | 경고·추천만 |
| Approved rule | 사람이 승인한 프로젝트 규칙 | 영향·Pack·테스트 추천 |
| Candidate rule | 변경 이력의 공동 발생 패턴 | 승인 대기 |
| Unknown | 그래프에 없거나 증거 부족 | 미확인 표시 |

## 3. 안전 경계

- 후보 규칙은 자동으로 승인되지 않습니다.
- 승인되지 않은 규칙은 Gate에 영향을 주지 않습니다.
- 승인 규칙이 요구한 Pack이 프로젝트 Profile에 없으면 선택하지 않고 설정 불일치로 보고합니다.
- 테스트 명령은 실행하지 않고 추천만 합니다.
- 그래프 해시가 내용과 일치하지 않으면 분석을 중단합니다.
- 절대 경로, `..` 경로 이탈, symlink alias는 색인에서 차단합니다.
- 구조적 관계는 런타임 동작의 증명이 아닙니다.

## 4. 아키텍처

```text
Project Profile + Intelligence Config
                │
                ▼
       Static Project Graph
                │
      ┌─────────┴─────────┐
      ▼                   ▼
 Git change set      Approved rules
      │                   │
      └─────────┬─────────┘
                ▼
       Change Impact Report
                │
      ┌─────────┴──────────┐
      ▼                    ▼
Review Pack routing   Parallel change comparison

Historical change sets
          │
          ▼
Co-change candidates → Human approval → Approved rules
```

## 5. 현재 구현 범위

- Python AST import·symbol extraction
- JavaScript/TypeScript 정적 import·선언 extraction
- Java/Kotlin package·import·declaration extraction
- SQL object definition·reference extraction
- Markdown local-link extraction
- component path mapping
- direct dependent BFS
- direct dependency listing
- approved-rule matching
- configured Review Pack routing
- parallel change overlap scoring
- asymmetric co-change candidate discovery
- rule approval audit and decision preservation
- Project State snapshot

## 6. 의도적으로 제외한 범위

- LLM 모델 학습·파인튜닝
- GitHub API 실시간 PR 수집
- 자동 Merge·자동 코드 수정
- 런타임 reflection·dynamic dispatch 완전 해석
- 명령 실행 샌드박스
- 의미론적 충돌 완전 판정
- 조직 단위 권한·멀티테넌시

## 7. 다음 확장 조건

다음 단계는 실제 Bejewely 저장소의 여러 PR 이력을 입력하여 오탐률과 누락률을 측정한 후 결정합니다. 측정 없이 자동 차단이나 모델 학습으로 확장하지 않습니다.
