# Trust Generic Policy Token D2 Authoritative Promotion

## 상태

이 문서는 `GENERIC_POLICY_TOKEN_ACCESS_CONTROL_COLLISION` D2 shadow calibration을 authoritative Trust risk semantics로 승격하는 후보 계약을 기록합니다.

- authoritative pre-D2 main: `30b05828e1b3227e9f721cd00c65a2d3a96ef33f`
- D2 shadow evidence head: `519b0a52957edea1281fceff6628c2208afa2252`
- shadow result: `D2_SHADOW_CALIBRATION_PASS`
- promotion branch: `feat/trust-generic-policy-token-authority`
- merge: NOT AUTHORIZED

## 결함

현재 pack selector는 경로 토큰 `policy` 또는 `policies` 하나만으로도 다음 두 pack을 동시에 선택할 수 있습니다.

- `data.rls`
- `application.authorization`

Trust v1.1은 두 pack의 동시 선택을 `REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS`라는 독립 corroboration으로 해석합니다. 그 결과 Recommendation/Raking 등 일반 도메인의 `candidate-policy.ts`, `ranking-policy.ts` 같은 R2 코드가 실제 RLS 또는 authorization-control-plane 근거 없이 R3로 올라갈 수 있습니다.

## v1.2 authoritative rule

`TRUST_RISK_MODEL_VERSION = 1.2`는 다음 경우에만 `AUTHORIZATION_RLS` corroboration을 중화합니다.

1. 동일 non-documentation path가 `application.authorization`과 `data.rls` 양쪽에 선택되고,
2. 그 path에 `policy` 또는 `policies`가 존재하며,
3. 아래 독립 authority token이 존재하지 않고,
4. generic collision path를 제거한 뒤 별도의 authorization path와 별도의 RLS path가 모두 남지 않는 경우.

독립 authority token:

- `rls`
- `supabase`
- `auth`
- `authentication`
- `session`
- `jwt`
- `middleware`
- `controller`
- `route`
- `routes`
- `api`
- `endpoint`

이 교정은 pack selection 자체를 변경하지 않습니다. Review routing은 유지되고, Trust risk corroboration에서만 self-correlation을 제거합니다.

## 버전 호환성

- unversioned legacy risk model: 기존 동작 유지
- Trust risk model `1.1`: 기존 D1/documentation semantics 및 기존 generic-policy corroboration 동작 유지
- Trust risk model `1.2`: v1.1 + D2 correction

`trust-report.schema.json`은 `risk_model_version`으로 `1.1`과 `1.2`를 모두 허용합니다. 기존 v1.1 report는 v1.1 semantics로 검증 및 source replay되어야 합니다.

## Synthetic discriminator

D2 shadow fixture의 다음 일반 도메인 shape는 v1.2에서 R3 -> R2가 예상됩니다.

- `src/recommendation/candidate-policy.ts`
- `src/ranking/ranking-policy.ts`
- `src/domain/access-control-policy.ts`

다음 control은 유지되어야 합니다.

- explicit RLS: R3
- explicit Supabase: R3
- explicit auth: R3
- independent API + RLS: R3
- Supabase migration: R3
- documentation: R1
- PIE verifier/policy authority: R4

또한 generic-policy-only case에서 v1.1의 `AUTHORIZATION_OR_MIGRATION_CHANGE` hard gate는 corroboration 때문에 trigger되지만, v1.2에서는 해당 self-corroboration만으로 trigger되어서는 안 됩니다. 실제 RLS/auth/migration case의 hard gate는 계속 trigger되어야 합니다.

## Wave 1 regression boundary

Wave 1은 새 blind holdout이 아니라 이미 공개된 historical regression corpus입니다.

- seen: 23
- frozen historical holdout: 11
- total: 34

Promotion acceptance 조건:

- v1.2 acceptable: 34/34
- v1.2 underclassification: 0
- v1.1 -> v1.2 band delta across Wave 1: 0

이 결과는 D2가 기존 Wave 1을 손상하지 않는다는 regression 근거일 뿐, 새로운 blind generalization 근거가 아닙니다. Wave 1에는 독립 blind R4 sample이 없으므로 blind R4 generalization claim을 만들지 않습니다.

## 명시적 비변경

- `packs.py` selector semantics 변경 없음
- task-class band 변경 없음
- path-band taxonomy 변경 없음
- workflow semantics 변경 없음
- hard-gate 규칙 자체 변경 없음
- profile 변경 없음
- R4 semantic under-detection remediation 없음
- MasterV-specific high-risk semantic blind spot remediation 없음
- automation authorization 없음
- pilot authorization 없음
- Stage10K HUMAN_DECISION 없음
- Software Factory / BuildMap scope 확장 없음

## Governance

이 promotion 후보는 계속 `REPORT_ONLY`입니다.

- `automation_authorized = false`
- `maximum_automation_band = NONE`
- pilot authorization 없음

CI 성공은 merge 권한이 아닙니다. 이 branch/PR을 main에 반영하려면 별도 명시적 merge 승인이 필요합니다.
