# Stage 2D Implementation Review

상태: `PASS_PENDING_FINAL_CI`

## 검토 결과

- `github_connector.py`는 공개 import와 `doctor()`를 유지하는 compatibility facade로 축소됐다.
- `collect_pull_request`의 명령 순서는 기존과 동일하다.
  1. target·repository binding
  2. authentication
  3. `gh pr view`
  4. changed-file pagination
  5. optional diff
  6. PR number·repository response 검증
  7. discussion endpoints
  8. source artifact assembly·hash
- changed-file count mismatch는 기존처럼 fail-closed한다.
- changed-file pagination 실패 시 기존 fallback·warning·fatal 분기가 유지된다.
- diff 실패는 기존처럼 warning이며 collection 전체 실패가 아니다.
- discussion endpoint 일부 실패 시 `gh pr view` 데이터 fallback과 warning을 유지한다.
- source schema, field names, list ordering, canonical SHA-256 규칙을 유지한다.
- `collect_pull_request`, `refresh_source_hash`, `validate_pull_request_source`, target·runner imports의 legacy 경로를 유지한다.
- local HEAD·dirty-worktree 검증과 application boundary는 변경하지 않았다.
- dependency, version, schema file, preset, workflow 변경은 없다.
- 임시 적용 script·workflow·trigger는 생성하지 않았다.

## 모듈별 책임

- `pagination.py`: `gh api --paginate --slurp` parsing과 오류 반환
- `discussion.py`: discussion endpoint 수집·compact·partial warning
- `source.py`: source artifact 조립·hash·validation
- `collector.py`: command ordering과 failure policy
- `github_connector.py`: compatibility facade와 doctor

## 리뷰 중 확인한 위험

### Mutable JSON payload

`DiscussionEvidence`는 frozen container지만 내부 JSON dict는 mutable하다. 현재 source artifact가 dict/list 계약이므로 deep immutable 전환은 schema·사용성 변경을 일으켜 보류했다.

### Private helper migration

기존 private helper의 외부 사용 여부를 검색했고 저장소 내부 참조는 발견되지 않았다. 공개 함수만 facade에 유지했다.

### Source timestamp

production path는 기존과 동일하게 UTC ISO timestamp를 생성한다. deterministic source unit test에서만 명시적 timestamp injection을 사용한다.

## 판정

구현 리뷰: `PASS`

최종 Gate는 문서 포함 exact HEAD의 Python 3.11·3.13·3.14 CI 완료 후 확정한다.
