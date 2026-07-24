# Stage 4 Implementation Review

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

## 구현 결과

- SQLite Ledger는 Stage 3 `identity.json`의 관계 projection이며 artifact 본문을 저장하지 않는다.
- 최초 migration은 version과 SQL SHA-256 checksum을 기록한다.
- `runs`, `artifacts`, `claims`, `evidence`, `claim_evidence`, `decisions`, `policy_snapshots` schema가 생성된다.
- Review Run과 PR Run을 expected type으로 분리해 import할 수 있다.
- 같은 logical Run 재import는 row를 중복 생성하지 않는다.
- explicit `gate-result.json`과 `gate-policy.yml`만 Decision·Policy로 projection한다.
- `verify_ledger`는 SQLite integrity, foreign key, migration, Run natural key, identity manifest, Artifact, Decision, Policy를 원본과 대조한다.
- rebuild는 임시 DB 검증 완료 후 `os.replace`로 교체한다.
- `pie-ledger` 전용 entrypoint를 추가해 기존 `pie` parser와 출력 계약을 변경하지 않았다.
- 외부 dependency와 제품 버전은 변경하지 않았다.

## 구현 리뷰 중 발견·보완

### IR-1 — 재import가 미래 Claim·Evidence를 삭제

초기 구현은 Run projection을 갱신하면서 아직 자동 생성하지 않는 Claim·Evidence row까지 삭제했다.

**조치:** Claim·Evidence는 보존하고 Artifact를 ID 기준 upsert한다. 현재 manifest에서 사라진 Artifact만 삭제하며 해당 Artifact에 연결된 Evidence는 foreign key `ON DELETE SET NULL`로 stale 연결을 제거한다.

### IR-2 — DB 내부 Decision·Policy 의미 변조 미탐지

초기 `verify`는 SQLite 구조와 Run·Artifact만 대조해 Decision outcome 또는 Policy metadata가 직접 수정돼도 탐지하지 못했다.

**조치:** 현재 원본 `gate-result.json`·`gate-policy.yml`에서 expected projection을 재계산하고 DB row 전체를 비교한다. Run natural-key field도 모두 대조한다.

### IR-3 — Windows read-only SQLite URI

`file:{path.as_posix()}`는 Windows drive path 해석이 구현 의존적일 수 있다.

**조치:** `Path.as_uri()` 기반 read-only URI로 교체했다.

## 무결성·안전 검토

- identity manifest가 modified·missing·unexpected artifact를 보고하면 import를 시작하지 않는다.
- Ledger DB를 artifact root 내부에 두는 self-indexing 구성을 거부한다.
- run ID와 full natural key가 충돌하면 transaction을 rollback한다.
- migration checksum mismatch와 unknown migration을 fail-closed한다.
- rebuild 입력에 같은 logical Run의 서로 다른 root가 있으면 stale copy 선택을 추측하지 않고 실패한다.
- corrupt DB는 `verify`에서 예외를 노출하지 않고 `valid=false`로 보고한다.
- rebuild 실패 시 기존 DB를 교체하지 않는다.

## 남은 제한

- `artifact_root`는 로컬 absolute locator이므로 directory 이동 후에는 rebuild가 필요하다.
- Claim·Evidence 관계는 schema만 존재하며 자동 의미 projection은 후속 Stage 대상이다.
- Attempt와 cross-run Defect는 저장하지 않는다.
- SQLite file 동시 writer는 busy timeout 이후 실패하며 별도 daemon queue는 없다.

## 판정

구현 리뷰: `PASS`

검증된 보완 구현 HEAD: `dd599c1dd55b80edc715a2f5a263f7116a78c05d`

GitHub Actions run `30073170029`에서 Python 3.11·3.13·3.14 전체 단계가 통과했다. 문서와 Architecture index를 포함한 마지막 HEAD를 같은 matrix로 재검증한 뒤 최종 Gate를 확정한다.
