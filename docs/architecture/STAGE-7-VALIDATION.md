# Stage 7 Validation

상태: `PASS`

권위 기준선: PR #14 HEAD `e3d9aedc8b66e53a2cae61a3c18fc9280137354a`

검증 대상 코드 HEAD: `9980bff910bb8f524d27836c052c726ab5c30291`

## 검증 대상

- root DRAFT Policy build
- approved Rule schema와 embedded snapshot
- Stage 6 PASS Evaluation report 검증
- evaluation challenger hash와 ruleset hash binding
- deterministic Registry·Policy identity
- Registry·Policy·event canonical SHA-256
- previous-event hash chain
- semantic version 형식·중복·parent 증가 규칙
- first root activation
- current-active direct-child activation
- parent supersession과 child activation
- stale·non-active parent activation 거부
- single ACTIVE projection과 `active_policy_id`
- active materialized `approved-rules.yml` 동등성
- active view 재생성
- added·removed·changed Rule comparison
- active·superseded Policy retirement
- active retirement 시 empty materialized view
- missing parent·parent cycle·multiple active tamper
- Registry·Policy identity rehash tamper
- ruleset·event·approval·effective·supersession·retirement projection tamper
- unsafe report reference와 symlink path
- future effective date 거부
- two-file atomic replace rollback
- `pie-policy` build·approve·compare·retire·verify·list·show·materialize
- CLI success·input error·verification error exit contract
- 기존 repository 전체 regression
- package asset synchronization
- 기존 CLI/profile/finding validation
- wheel build including `pie-policy`

## 검증 이력

1. 초기 구현 HEAD `48818c65c3e07c6dc8d66212f46a401eec4dad35`의 GitHub Actions run `30084779155`가 Python 3.11·3.13·3.14에서 통과했다.
2. 구현 리뷰에서 Registry·Policy ID 재계산, parent semantic version, evaluation reference, lifecycle metadata projection 누락을 발견했다.
3. 검증기를 보완하고 focused hardening tests를 추가했다.
4. 임시 patch script와 workflow를 제거한 코드 HEAD `9980bff910bb8f524d27836c052c726ab5c30291`의 GitHub Actions run `30085741670`이 Python 3.11·3.13·3.14에서 통과했다.
5. 설계·구현 리뷰·검증 문서와 Architecture index를 포함한 HEAD `42d827c8af743f71749f5a43c80f8c8acf71c1af`의 run `30086022114`가 Python 3.11·3.13·3.14에서 통과했다.
6. 각 job은 package install, asset sync, full unit/regression, `urs version`, 4개 profile, finding validation, wheel build를 모두 완료했다.

## 최종 판정

Stage 7 Gate: `PASS`

최종 상태 문서를 포함한 exact HEAD에서도 동일한 GitHub Actions matrix를 재확인하며, 그 결과를 PR #15 본문에 권위 기록으로 남긴다.
