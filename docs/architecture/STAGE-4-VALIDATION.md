# Stage 4 Validation

상태: `PASS`

권위 기준선: PR #11 HEAD `27717f00c689ee0ae7c8f0bfb440b1b61e7ccb2f`

검증된 구현 HEAD: `dd599c1dd55b80edc715a2f5a263f7116a78c05d`

## 검증 대상

- empty SQLite initialization
- migration replay·checksum mismatch
- foreign-key constrained initial schema
- Review Run·PR Run type-safe import
- idempotent duplicate import
- modified artifact import rejection
- DB-inside-artifact-root rejection
- explicit Gate Decision·Policy projection
- Claim·Evidence preservation during reimport
- source artifact change detection
- Run·Decision projection DB tamper detection
- corrupt database reporting
- atomic rebuild and original DB preservation
- duplicate logical Run root rejection
- `pie-ledger` init·import·verify·show-run exit contract
- existing full repository regression

## CI 결과

초기 구현 HEAD `4b1eae4ad982518b33839ee0fb63f0b68cdba199`의 run `30072805020`이 Python 3.11·3.13·3.14 전체 단계를 통과했다.

구현 리뷰 보완 HEAD `dd599c1dd55b80edc715a2f5a263f7116a78c05d`의 run `30073170029`도 다음을 모두 통과했다.

- package install: PASS
- package asset synchronization: PASS
- full unit/regression suite: PASS
- existing `urs version`: PASS
- four profile validations: PASS
- finding validation: PASS
- wheel build including `pie-ledger` entrypoint: PASS

Architecture index와 본 검증 기록을 포함한 마지막 exact HEAD도 같은 Python matrix로 검증한다. 해당 final HEAD SHA와 workflow run은 PR #12 본문을 권위 기록으로 사용한다.

최종 Gate: `PASS`
