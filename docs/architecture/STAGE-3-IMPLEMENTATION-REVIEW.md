# Stage 3 Implementation Review

상태: `PASS_PENDING_FINAL_CI`

## 검토 결과

- 기존 `run.json.run_id`, PR 산출물 4개, source·impact·diff hash는 유지됐다.
- Review Run과 PR 분석이 동일한 deterministic Run·Artifact identity primitive를 사용한다.
- `identity.json`은 원본 파일에서 재생성 가능한 sidecar이며 삭제가 원본 손실을 만들지 않는다.
- Run key에는 timestamp·absolute path·random UUID가 포함되지 않는다.
- Artifact key는 Run key, relative path, content SHA-256으로 결정된다.
- artifact 목록과 manifest hash는 canonical ordering을 사용한다.
- identity와 기존 SHA manifest 사이의 재귀 관계를 피하기 위해 identity와 manifest 파일을 상호 목록에서 제외했다.
- relative path traversal과 artifact root 밖 symlink를 fail-closed한다.
- legacy Review Run은 identity 파일이 없어도 기존 검증을 통과하며 sync 시 additive identity로 업그레이드된다.
- SQLite, schema migration, CLI command, dependency, workflow 변경은 없다.
- 임시 적용 workflow·script는 최종 diff에서 제거됐다.

## 리뷰 중 발견·수정

기존 테스트와 외부 fixture는 실제 Git SHA 대신 `head123` 같은 placeholder head 값을 사용할 수 있었다. 첫 구현은 이를 안정 source revision으로 강제 해석해 기존 PR 분석을 실패시켰다.

수정 후 정책:

1. valid Git SHA이면 `git:<sha>` 사용
2. 비정규·placeholder head이면 `source_sha256` 사용
3. 둘 다 없으면 `unresolved`

이로써 실제 Git SHA는 우선 보존하면서 기존 source document의 느슨한 head 필드 계약도 깨지지 않는다.

## 잔여 경계

- external ID는 full SHA-256의 128-bit prefix이며 full key digest도 함께 보존한다.
- Attempt identity는 Stage 4 Ledger schema에서 별도 설계한다.
- `identity.json`은 현재 파일 snapshot이며 append-only audit log가 아니다.
- source revision이 `unresolved`인 legacy Run은 source identifier를 통해 안정적으로 재import된다.

## 판정

구현 리뷰: `PASS`

최종 Gate는 문서 포함 exact HEAD의 Python 3.11·3.13·3.14 CI 완료 후 확정한다.
