# Stage 10B Implementation Review

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

권위 기준선: PR #18 HEAD `4f2fc0610213d01bc3471f67283d721b44922f0b`

## 구현 결과

- Stage 10A Trust report를 원문 복제 없이 assessment reference로 고정한다.
- `WORKFLOW_ACCEPTED`, `REVIEWED`, `AUDITED`를 구분한다.
- `WORKFLOW_ACCEPTED`는 reviewer alignment 분모에 포함하지 않는다.
- Human decision과 Outcome을 전역 append-only SHA-256 event chain으로 보존한다.
- provisional reviewer alignment와 confirmed outcome accuracy를 별도 projection으로 계산한다.
- conclusive Outcome 없는 사례는 SAFE나 정확도 분모로 간주하지 않는다.
- 독립 Audit actor가 기존 reviewed actor와 같으면 거부한다.
- SAFE/UNSAFE가 충돌하는 conclusive Outcome은 supersession 계약이 생기기 전까지 거부한다.
- R0/R1 미확정 assessment를 위한 deterministic Audit sample을 생성한다.
- `pie-trust`와 `pie-trust-comparison`에서 Registry lifecycle 명령을 제공한다.
- 기존 Gate·Ledger·Defect·Evaluation·Policy·Reground·BuildMap 의미는 변경하지 않는다.

## 구현 리뷰에서 발견하고 수정한 문제

1. Stage 10A risk band를 존재하지 않는 `task_advisory.risk_band`에서 읽던 projection 오독.
2. schema asset helper 호출 인자 불일치.
3. assessment ID를 outer hash만 갱신하면 바꿀 수 있던 문제.
4. event ID를 payload에 맞춰 다시 만들지 않아도 통과할 수 있던 문제.
5. 독립 Audit actor 제약이 write path에만 있고 self-contained verifier에 없던 문제.
6. 서로 반대인 SAFE·UNSAFE Outcome이 latest-wins로 덮일 수 있던 문제.
7. 분모가 없는 confirmed 지표가 숫자로 오인될 위험.
8. 임시 workflow 적용 순서가 PR CI보다 늦어 동일 실패가 반복된 문제. 권위 모듈을 직접 교체하고 임시 자산을 제거했다.

## 안전 경계

- 자동 PASS, 승인, merge, label, comment, branch write를 추가하지 않았다.
- 사용자의 `진행`·`다음 작업`은 자동으로 human review event가 되지 않는다.
- `REVIEWED`는 잠정 비교일 뿐 ground truth가 아니다.
- confirmed false negative는 conclusive Outcome이 있는 경우에만 계산한다.
- Registry는 파일 권위 원본이며 Ledger migration은 없다.

## 알려진 제한

- main `pie`·`urs` alias는 이번 Stage에 추가하지 않았다. 기능은 `pie-trust`와 `pie-trust-comparison`에 한정한다.
- Registry assessment를 원본 Trust report들과 다시 대조하는 bulk source replay는 미구현이다.
- Defect ID는 opaque reference이며 Defect Registry 존재성 검증은 후속 integration 범위다.
- cryptographic signer identity와 cross-process lock은 없다.
- Audit sample은 후보 선정이며 Outcome을 자동 생성하지 않는다.
- R0/R1 자동화는 금지 상태다.
