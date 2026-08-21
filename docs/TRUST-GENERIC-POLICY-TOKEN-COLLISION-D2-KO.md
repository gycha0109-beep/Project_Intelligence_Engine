# Trust Generic Policy Token Collision D2 — Shadow Calibration

## 1. 목적

이 문서는 PIE Trust risk calibration의 독립 결함인 다음 항목에 대한 D2 shadow 검증 결과를 동결합니다.

```text
GENERIC_POLICY_TOKEN_ACCESS_CONTROL_COLLISION
```

이 Stage의 목적은 `policy` / `policies`라는 일반 도메인 용어가 실제 authorization 또는 RLS authority의 독립 증거 없이 Trust risk를 R3로 승격시키는 자기상관(self-corroboration) 문제를 분리하여 검증하는 것입니다.

이 문서는 authoritative runtime 변경을 승인하거나 수행하지 않습니다.

## 2. 기준 authority

```text
PIE main SHA
30b05828e1b3227e9f721cd00c65a2d3a96ef33f

Trust risk model
1.1

Mode
REPORT_ONLY
```

D2는 이미 main에 반영된 Wave 1 workflow semantics와 documentation precedence를 다시 열지 않습니다.

## 3. Root Cause

현재 `packs.py` token selection에는 다음 의미가 있습니다.

```text
rls / policy / policies / supabase
→ data.rls
→ application.authorization
```

Trust의 review-pack corroboration은 non-documentation 변경에서 다음 두 pack이 모두 선택되면 R3 semantic floor를 생성합니다.

```text
application.authorization
+
data.rls
→ REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS
→ R3
```

따라서 다음과 같은 ordinary domain file 하나가 있을 때:

```text
src/recommendation/candidate-policy.ts
```

`policy`라는 동일 generic token 하나가 두 pack을 동시에 선택하고, Trust가 이를 서로 독립적인 authorization + RLS evidence처럼 해석할 수 있습니다.

즉 문제는 다음과 같습니다.

```text
ONE_GENERIC_TOKEN
→ TWO_PACK_SELECTIONS
→ FALSE_INDEPENDENT_CORROBORATION
→ R2_PATH promoted to R3
```

이는 실제 authorization boundary, RLS implementation, migration 또는 security-control-plane 변경이 확인된 것이 아닙니다.

## 4. 실제 프로젝트 어휘와의 충돌

BEJEWELY / K_beauty에서는 `CandidatePolicy`가 Recommendation domain의 별도 semantic contract 이름으로 사용됩니다.

프로젝트의 여러 변경은 CandidatePolicy semantic change 여부를 Recommendation/runtime 변화와 별도 invariant로 관리하고 있습니다.

따라서 `candidate-policy`라는 명칭 자체를 다음과 동일시해서는 안 됩니다.

```text
RLS authority
authorization control plane
security boundary
```

D2는 이 domain-language collision을 일반화된 synthetic discriminator로 검증합니다.

## 5. Shadow Candidate Contract

Candidate contract:

```text
TRUST_GENERIC_POLICY_TOKEN_COLLISION_D2_SHADOW_V1
```

Candidate는 `packs.py` selector 자체를 변경하지 않습니다.

다음 조건에서만 `REVIEW_PACK_CORROBORATION:AUTHORIZATION_RLS` floor를 shadow projection에서 제거합니다.

1. 동일 non-documentation path가 `application.authorization`과 `data.rls` 양쪽에 선택됨
2. 그 dual selection이 `policy` / `policies` generic token으로 설명됨
3. 해당 path에 stronger authority token이 없음
4. generic collision path를 제거한 뒤에도 독립적인 authorization + RLS signal 조합이 남아 있지 않음

Stronger authority token에는 다음이 포함됩니다.

```text
rls
supabase
auth
authentication
session
jwt
middleware
controller
route
routes
api
endpoint
```

Candidate는 다른 risk floor를 낮추지 않습니다.

따라서 다음은 그대로 유지됩니다.

- explicit auth / RLS / Supabase signal
- migration path floor
- protected path floor
- workflow semantic floor
- R4 verifier/policy path
- task-class floor
- 다른 review-pack corroboration

## 6. Synthetic Discriminator Matrix

### Band가 변경되는 case

| Case | Current | D2 Candidate |
|---|---:|---:|
| `src/recommendation/candidate-policy.ts` | R3 | R2 |
| `src/ranking/ranking-policy.ts` | R3 | R2 |
| `src/domain/access-control-policy.ts` | R3 | R2 |

세 case 모두 generic `policy` token의 자기상관만으로 R3가 만들어지는 shape입니다.

### Negative control

| Case | Candidate |
|---|---:|
| explicit RLS path | R3 |
| explicit Supabase path | R3 |
| explicit auth path | R3 |
| independent API + RLS signals | R3 |
| Supabase migration | R3 |
| documentation policy name | R1 |
| PIE verifier/policy authority | R4 |

`supabase/migrations/..._policy.sql`은 `supabase`와 migration이라는 독립 high-risk signal이 있으므로 generic-policy-only collision으로 판정하지 않습니다.

## 7. Wave 1 Regression

D2 candidate는 기존 frozen Wave 1을 새로운 human holdout으로 사용하지 않습니다.

Wave 1은 이미 label-open 및 authoritative promotion이 끝난 historical regression corpus로만 사용됩니다.

재생 범위:

```text
seen = 23
frozen holdout = 11
total = 34
```

D2 shadow 결과:

```text
Wave1 acceptable = 34 / 34
Wave1 underclassification = 0
Wave1 current -> D2 candidate band changes = 0
```

즉 D2 candidate는 이미 검증된 Wave 1 authoritative result를 변경하지 않습니다.

## 8. CI Evidence

초기 CI:

```text
CI #1189
run 32535077145
```

초기 실패는 `D2-CONTROL-MIGRATION` fixture의 `expected_collision` 값 하나가 잘못 설정된 것이 원인이었습니다.

실제 classifier는 `supabase`를 stronger authority token으로 정확히 식별하여 `collision=false`를 반환했고, effective band는 기대대로 R3를 유지했습니다.

Candidate implementation 또는 Wave 1 regression 실패가 아니었습니다.

Fixture correction commit:

```text
b46ddbcce6c094080f82285abab0bc0a49429f12
```

교정 후 CI:

```text
CI #1191
run 32535174417
Python 3.11 = SUCCESS
Python 3.13 = SUCCESS
Python 3.14 = SUCCESS
```

통과 범위:

- full unittest
- D2 synthetic discriminator matrix
- explicit authority negative controls
- Wave 1 34-sample regression
- package asset sync
- profile validation
- findings validation
- wheel build

## 9. Authority Ceiling

현재 D2 결과의 authority는 다음과 같습니다.

```text
D2_SHADOW_CALIBRATION = PASS
AUTHORITATIVE_TRUST_MUTATION = NO
PACK_SELECTOR_MUTATION = NO
HUMAN_BLIND_HOLDOUT_CLAIM = NO
AUTOMATION_AUTHORIZED = NO
PILOT_AUTHORIZED = NO
STAGE10K_HUMAN_DECISION = NO
```

현재 `trust.py`와 `packs.py`는 D2 때문에 변경되지 않았습니다.

## 10. 별도 남은 결함

D2는 다음 문제를 해결하거나 재평가하지 않습니다.

```text
R4_SEMANTIC_UNDERDETECTION
PROJECT_SPECIFIC_HIGH_RISK_SEMANTIC_BLIND_SPOT
```

특히 MasterV-specific semantic gap과 R4 semantic detection은 별도 calibration / evidence track으로 유지합니다.

## 11. 결론

D2 shadow candidate는 다음을 입증했습니다.

```text
generic policy token self-corroboration can be removed
without lowering explicit authority controls
without changing any Wave 1 authoritative band
without introducing a Wave 1 underclassification
```

따라서 D2는 **bounded authoritative-promotion 검토가 가능한 shadow-calibrated candidate** 상태입니다.

단, authoritative `trust.py` 또는 pack-selection semantics로의 승격은 별도 명시적 승인 없이 수행하지 않습니다.
