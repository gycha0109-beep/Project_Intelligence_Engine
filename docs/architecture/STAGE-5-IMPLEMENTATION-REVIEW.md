# Stage 5 Implementation Review

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

## 구현 결과

- validated `findings.json`을 Run-local Finding으로 Ledger에 projection한다.
- Finding ID는 `logical run_id + source finding id`의 deterministic digest다.
- Defect는 `project_id + signature`의 deterministic identity를 사용한다.
- canonical `defect-registry.json`이 Defect lifecycle의 권위 원본이며 SQLite는 재구축 가능한 projection이다.
- migration `002`는 migration `001`을 수정하지 않고 Finding·Defect 관계 table을 추가한다.
- 같은 Run·Finding·Defect 재수집은 중복 row를 만들지 않는다.
- source에서 사라진 연결되지 않은 Finding은 제거하고, Defect에 연결된 Finding 삭제는 fail-closed한다.
- lifecycle transition은 허용 graph만 통과하며 append-only event를 생성한다.
- `CLOSED`는 resolution과 `resolution_evidence` Artifact를 요구한다.
- `REOPENED`는 명시적 재발 이유를 요구한다.
- `pie-defect` 전용 CLI를 추가하고 기존 `pie`·`urs` 계약은 변경하지 않았다.
- Ledger rebuild는 명시적 Defect Registry를 함께 projection할 수 있다.

## 구현 리뷰 중 발견·보완

### IR-1 — event hash 검증 입력 불일치

초기 구현은 event hash를 `event_id` 생성 전 payload에서 계산했지만 검증에서는 `event_id`를 포함해 재계산했다. 모든 Defect 생성이 거부되는 결함이었다.

**조치:** event hash 검증은 `event_id`와 `event_sha256`을 제외한 canonical payload를 사용한다.

### IR-2 — event ID 자체 변조 미탐지

hash만 일치하면 `event_id`가 임의 값으로 바뀌어도 통과할 수 있었다.

**조치:** `event_id == event-{event_sha256[:32]}`를 강제한다.

### IR-3 — CREATED 이전 link event 허용

link event가 Defect 생성 event보다 앞서도 lifecycle status만 최종적으로 맞으면 검증될 수 있었다.

**조치:** CREATED 이전의 모든 non-CREATED event를 거부한다.

### IR-4 — CLOSED 원본 불변식이 mutation API에만 존재

transition API는 resolution evidence를 강제했지만, registry 파일을 재해시한 경우 validator가 CLOSED 불변식을 재검증하지 않았다.

**조치:** registry validator도 CLOSED resolution·resolution_evidence를 독립적으로 검증한다.

### IR-5 — Run 조회에서 Finding 누락

Finding이 저장돼도 `show_run()` 결과에는 노출되지 않았다.

**조치:** Run 조회 결과에 정렬된 `findings` 배열을 포함한다.

### IR-6 — 검증 범위 부족

초기 테스트는 기본 lifecycle을 검증했지만 migration 001→002 upgrade, event ID 변조, CLOSED 재해시 우회, 전용 CLI exit contract를 직접 고정하지 않았다.

**조치:** 별도 hardening suite를 추가했다.

## 안전성 검토

- invalid findings import는 transaction 전체를 rollback한다.
- Defect-linked stale Finding은 자동 삭제하지 않는다.
- cross-project Finding·Artifact reference는 registry sync 전에 거부한다.
- 같은 project의 서로 다른 canonical registry path는 추측하지 않고 거부한다.
- registry write는 temp file + `os.replace`로 원자화한다.
- registry와 DB가 어긋나면 registry가 권위이며 sync로 복구한다.
- DB rebuild는 Run artifact와 registry 검증 완료 후 원자 교체한다.
- automatic similarity는 확정 link를 만들지 않는다.
- 기존 artifact schema, dependency, version은 변경하지 않았다.

## 남은 제한

- historical Defect seed는 authoritative source가 없어 이번 단계에서 생성하지 않았다.
- root cause 자동 추론과 Rule Candidate 연결은 후속 단계 대상이다.
- registry mutation과 DB projection은 하나의 filesystem/database transaction이 아니며, DB sync 실패 시 재동기화가 필요하다.
- multi-writer coordination은 SQLite busy timeout 수준이며 daemon queue는 없다.

## 판정

구현 리뷰: `PASS`

검증된 코드 HEAD: `d7711308e7a9eb4912148657736eb6746fcac6b3`

GitHub Actions run `30075607439`에서 Python 3.11·3.13·3.14의 전체 regression, package asset sync, 기존 CLI/profile/finding smoke와 wheel build가 통과했다.
