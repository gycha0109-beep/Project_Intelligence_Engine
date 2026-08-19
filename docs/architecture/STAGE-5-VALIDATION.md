# Stage 5 Validation

상태: `PASS`

권위 기준선: PR #12 HEAD `9a59bf1d41b9c6b5be559957737f78b66d6d24f3`

검증된 코드 HEAD: `d7711308e7a9eb4912148657736eb6746fcac6b3`

## 검증 대상

- append-only migration `001 → 002`
- migration checksum replay와 unknown migration fail-closed
- validated Review Run Finding projection
- duplicate Finding import idempotence
- invalid findings transaction rollback
- unlinked stale Finding deletion
- Defect-linked stale Finding 삭제 거부
- deterministic Defect ID와 signature conflict
- canonical registry ordering·hash
- event hash·event ID·creation ordering
- explicit Finding·Artifact link와 project boundary
- lifecycle 허용·금지 transition
- CLOSED resolution·resolution evidence
- REOPENED recurrence reason
- registry·Ledger projection tamper detection
- Run 조회의 Finding projection
- registry 포함 atomic rebuild
- duplicate project registry source rejection
- `pie-defect` init·sync·verify·list·show exit contract
- 기존 전체 repository regression

## 검증 이력

1. 초기 integration run `30074520279`에서 event hash 입력 불일치를 발견했다.
2. 수정 후 focused·full Python 3.11 run `30075436093`이 통과했다.
3. 구현 리뷰 hardening에서 event ID, CREATED ordering, CLOSED validator, migration upgrade와 CLI contract를 보강했다.
4. 임시 workflow·script·diagnostic log를 제거한 코드 HEAD `d7711308e7a9eb4912148657736eb6746fcac6b3`의 run `30075607439`이 Python 3.11·3.13·3.14에서 모두 통과했다.
5. 구현 리뷰·검증 문서와 Architecture index를 포함한 HEAD `bac95a21dc81e094f5e3124eaa0a9db216a2fe6e`의 run `30075765879`도 동일한 matrix를 통과했다.

각 matrix job은 다음 단계를 완료했다.

- package install: PASS
- package asset synchronization: PASS
- full unit/regression suite: PASS
- existing `urs version`: PASS
- four profile validations: PASS
- finding validation: PASS
- wheel build including `pie-defect`: PASS

## 최종 판정

Stage 5 Gate: `PASS`

최종 상태 기록을 포함한 PR HEAD도 동일한 matrix로 재검증한다. PR 본문에 기록된 exact-head run을 최종 권위 검증으로 사용한다.
