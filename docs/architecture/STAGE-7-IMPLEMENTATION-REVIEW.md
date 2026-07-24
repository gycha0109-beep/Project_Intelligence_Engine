# Stage 7 Implementation Review

상태: `PASS_PENDING_FINAL_EXACT_HEAD_CI`

권위 기준선: PR #14 HEAD `e3d9aedc8b66e53a2cae61a3c18fc9280137354a`

## 구현 결과

- file-authoritative Policy Registry JSON을 추가했다.
- approved Rule 집합을 immutable snapshot으로 포함하고 canonical ruleset SHA-256을 기록한다.
- Stage 6 PASS Evaluation report와 challenger ruleset hash를 Policy에 결합한다.
- project·semantic version·parent·ruleset hash·evaluation ID로 deterministic Policy ID를 생성한다.
- Registry·Policy·event hash와 previous-event hash chain을 추가했다.
- DRAFT → ACTIVE → SUPERSEDED → RETIRED lifecycle을 구현했다.
- 첫 활성 Policy는 root로 제한하고, 이후 활성화는 현재 active Policy의 직계 자식만 허용한다.
- 자식 활성화 시 parent supersession과 active materialized `approved-rules.yml` 갱신을 원자적으로 수행한다.
- active·superseded Policy retirement와 active view 비우기를 구현했다.
- compare·verify·list·show·materialize 기능과 별도 `pie-policy` CLI를 추가했다.
- 기존 `pie`, `urs`, `pie-eval`, Ledger, Defect Registry, artifact schema, dependency, 제품 버전은 변경하지 않았다.

## 구현 리뷰 중 발견·보완

### IR-1 — Registry·Policy ID 자연키 재검증 누락

초기 verifier는 외부 hash만 재검증해, 공격자가 ID를 바꾸고 모든 상위 hash를 다시 계산하면 forged ID를 탐지하지 못했다.

**조치:** project 기반 Registry ID와 project·version·parent·ruleset·evaluation 기반 Policy ID를 verifier가 재계산한다.

### IR-2 — parent Policy보다 낮거나 같은 semantic version 허용

초기 build는 version 중복만 차단했으며 parent보다 낮은 후속 Policy를 생성할 수 있었다.

**조치:** child semantic version이 parent version보다 반드시 커야 하며 build와 verifier 양쪽에서 검사한다.

### IR-3 — evaluation report reference traversal

초기 verifier는 report reference가 비어 있지 않은지만 확인했다. rehash된 `../` 경로가 Registry 내부 검증을 통과할 수 있었다.

**조치:** absolute, drive-qualified, empty, traversal reference를 구조 검증 단계에서 거부하고 Registry directory 안의 report만 허용한다.

### IR-4 — lifecycle metadata와 event projection 불일치

초기 verifier는 event transition과 최종 status는 확인했지만 approval actor/time, effective time, superseded target, retirement metadata가 해당 event와 같은지 강제하지 않았다.

**조치:** metadata와 APPROVED·ACTIVATED·SUPERSEDED·RETIRED event를 상호 대조하며 BUILT 중복과 역행 timestamp도 거부한다.

### IR-5 — atomic two-file partial replacement

Registry 갱신 후 materialized view 교체가 실패하면 둘이 불일치할 수 있다.

**조치:** 기존 bytes를 보존하고 두 target 중 하나라도 실패하면 이미 교체된 target을 복구한다. 회귀 테스트에서 두 번째 replace 실패를 주입했다.

## 안전성 검토

- Registry, Rule, Evaluation report, materialized target의 symlink 경로를 거부한다.
- Evaluation report는 Stage 6 전체 verifier와 PASS Gate를 통과해야 한다.
- report challenger hash와 embedded ruleset hash가 다르면 build를 중단한다.
- active Policy는 최대 하나이며 `active_policy_id` projection과 일치해야 한다.
- missing parent, parent cycle, stale parent activation, duplicate version·identity를 fail-closed한다.
- immediate activation만 허용하며 future-effective scheduler는 추가하지 않았다.
- active retirement에는 materialized view 경로를 필수로 요구한다.
- Registry JSON이 권위 원본이며 materialized Rule file은 언제든 active snapshot에서 재생성할 수 있다.

## 남은 제한

- SHA-256은 내용 무결성을 제공하지만 서명자 신원을 증명하지 않는다.
- Policy Registry는 로컬 파일 기반이며 remote distribution·locking을 제공하지 않는다.
- future-effective activation과 background scheduler는 지원하지 않는다.
- 기존 `approve-rule`은 호환성을 위해 독립적으로 남아 있으며 Policy Registry 사용을 강제하지 않는다.
- Evaluation evidence는 실제 human-labeled dataset 품질에 의존한다.

## 판정

구현 리뷰: `PASS`

검증된 hardening 코드 HEAD: `9980bff910bb8f524d27836c052c726ab5c30291`

GitHub Actions run `30085741670`에서 Python 3.11·3.13·3.14 전체 regression과 wheel build가 통과했다. 최종 문서 포함 exact HEAD에서 같은 matrix를 재검증한다.
