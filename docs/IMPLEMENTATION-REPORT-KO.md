# Universal Review System v0.1.1 구현·보완 보고

## 1. 완료

v0.1.0 기준선을 자체 검토한 뒤, 실전 프로젝트 온보딩 전에 필요한 계약·실행 흐름 보완을 `v0.1.1`로 반영했습니다.

### Profile

- Stack Profile 실제 상속 구현
- 다중 상속 및 순환 참조 차단
- 프로젝트 명령의 Stack 기본 명령 덮어쓰기
- 언어·프레임워크·Pack 목록 안정적 합성
- `review.exclude_packs` 지원
- `.review/stacks/` 프로젝트 전용 Stack 지원
- resolved profile 출력

### Finding·Evidence

- E3+ 명령/위치와 실제 결과 필수화
- P0/P1 verification 필수화
- 빈 scope 차단
- `REJECTED` confidence/status 상호 일치 검증
- `FIXED`를 검증 전 중간 상태로 허용
- `RESOLVED` E5 필수화
- `ACCEPTED` owner·reason·review date 필수화
- P0 residual-risk 수용 금지

### Gate

- Finding 기반 severity별 metric 재계산
- 프로젝트 `gate.block_on` 반영
- `ACCEPTED`를 blocker가 아닌 residual risk로 계산
- `FIXED`지만 E5 미검증인 blocker를 HOLD 처리
- 기존 v0.1.0 metric 입력 하위 호환
- 수동 metric과 derived metric 불일치 보고

### Run

- source/resolved profile 동시 보존
- Pack 버전 lock 생성
- candidate/challenge/verification 산출물 추가
- `findings.json` → `run.json` 동기화
- run directory 일관성 검증
- archive 전 Finding·Profile·Pack lock·Gate·policy·보호 기준선 일관성 차단
- 초기 manifest와 최종 archive manifest 의미 분리
- 상대 경로 manifest 검증 보정
- run 내부 ZIP 생성 차단

### Protected Baseline

- 보호 경로 파일 목록 및 SHA-256 스냅샷
- 추가·삭제·수정 구분 검증
- Gate directory 계산 시 자동 반영

### Change Review

- 원시 substring 대신 path token·확장자 기반 Pack 선택
- 선택 Pack별 근거 파일 출력
- `capitalization.ts`가 `api` 파일로 오분류되는 유형 차단

### Packaging

- Stack Profile을 Wheel asset에 포함
- 소스 asset과 Wheel package asset의 drift 테스트 추가
- 런타임 버전을 단일 `VERSION` 자산에서 조회

## 2. 수정된 주요 파일

```text
src/review_system/profile.py
src/review_system/baseline.py
src/review_system/gate.py
src/review_system/run.py
src/review_system/validation.py
src/review_system/packs.py
src/review_system/merge.py
src/review_system/cli.py
src/review_system/version.py
core/*.json
core/default-gate-policy.yml
profiles/stacks/*.yml
templates/challenge-log.md
templates/verification-log.md
orchestrator/SKILL.md
docs/*.md
tests/*.py
```

## 3. 검증

- 단위·계약 테스트: **53/53 PASS**
- 예제 Profile resolved validation: Journey Connect, Bejewely, BuildMap, Generic Web App PASS
- 프로젝트 로컬 Stack 상속 PASS
- Stack 순환·미존재 차단 PASS
- accepted/fixed/resolved Gate 의미 검증 PASS
- 보호 기준선 추가·삭제·수정 탐지 및 symlink·경로 이탈 차단 PASS
- 상대 경로 manifest 검증 및 manifest 경로 이탈 차단 PASS
- Finding merge 후 즉시 재사용 가능한 배열 출력 PASS
- Gate policy 중복 규칙·빈 PASS 계약 차단 PASS
- package asset drift 검증 PASS
- 실제 end-to-end PASS → 보호 경로 변경 후 FAIL 전환 PASS
- Wheel 비편집 설치본 Profile/Gate/Archive/Manifest PASS

## 4. 보완으로 해결한 v0.1.0 주요 문제

| 문제 | v0.1.1 처리 |
|---|---|
| `inherits`가 문서에만 있고 실행되지 않음 | effective profile resolver 구현 |
| Stack 기본 Pack의 실제 적용·버전 고정 없음 | 합성 및 `packs.lock.json` 추가 |
| accepted finding이 blocker로 집계됨 | residual risk로 분리 |
| 수정 완료와 검증 완료를 구분하지 못함 | `FIXED`/`RESOLVED` 단계 분리 |
| Finding 파일과 Run metric 수동 중복 관리 | `sync-run` 추가 |
| 보호 기준선 플래그만 존재 | 실제 SHA-256 snapshot/verify 추가 |
| Pack 라우팅 substring 오탐 | token 기반으로 교체 |
| merge 결과가 Finding 입력 계약과 불일치 | findings/conflicts 출력 분리 |
| 초기 manifest가 최종 무결성처럼 보임 | initial/final manifest 분리 |

## 5. 현재 경계

v0.1.1은 검토 통제 기반선이며 다음은 아직 구현하지 않았습니다.

- 저장소 코드의 LLM 자동 분배
- 명령 실행 샌드박스 및 표준 로그 수집
- 호출 그래프 기반 Change Impact Analyzer
- GitHub PR comment·merge gate
- 검토 시스템 탐지율·오탐률 Benchmark
- 프로젝트 Finding을 Pack 규칙으로 자동 승격하는 Knowledge Base

## 6. 다음 재개 지점

다음 단계는 기능을 더 넓히기 전에 Journey Connect 저장소에 `.review/`를 실제 삽입하고 첫 Full Review를 수행하여 다음을 검증하는 것입니다.

1. Profile과 보호 경로가 실제 구조에 맞는지
2. Recommendation/Search Pack의 체크 깊이가 충분한지
3. Explorer·Challenger·Verifier 산출물이 중복 없이 작동하는지
4. Gate가 기존 P0~P2 기준선과 충돌하지 않는지
5. 실전에서 발견된 결함을 범용 Pack에 승격할 수 있는지
