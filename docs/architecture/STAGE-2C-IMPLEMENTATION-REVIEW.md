# Stage 2C Implementation Review

상태: `PASS_PENDING_FINAL_CI`

- repository 선택·정규화·불일치 차단만 `github.binding`으로 이동했다.
- 인증, API 호출, pagination, discussion, source JSON, diff, hash는 변경하지 않았다.
- 기존 `github_connector`의 target·runner public import는 유지된다.
- URL target은 current repository 조회 없이 처리된다.
- 숫자 target은 기존처럼 current repository를 사용하고 실패 시 fail-closed한다.
- GitHub Enterprise의 `gh --repo` argument가 유지된다.
- application의 local HEAD·dirty-worktree 검증은 변경하지 않았다.
- 자동 적용 script, workflow, trigger는 최종 diff에서 제거됐다.
- 최종 변경 범위는 문서 3개, source 3개, test 1개다.

최종 Gate는 exact-head Python 3.11·3.13·3.14 CI 통과 후 확정한다.
