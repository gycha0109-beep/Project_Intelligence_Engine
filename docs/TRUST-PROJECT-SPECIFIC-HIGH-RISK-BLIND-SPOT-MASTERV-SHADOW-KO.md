# Trust Project-Specific High-Risk Blind Spot — MasterV Shadow Audit

## Status

- contract: `TRUST_PROJECT_SPECIFIC_HIGH_RISK_BLIND_SPOT_SHADOW_V1`
- PIE authority main: `7aa435f1b5afd208a05b222f5bed55da77d4c6e8`
- Trust risk model: `1.3`
- mode: `REPORT_ONLY`
- authority: `SHADOW_ONLY`
- `automation_authorized = false`
- `pilot_authorized = false`
- authoritative remediation: **not authorized**
- blind holdout claim: **not made**
- initial exact-head CI: **PASS — CI #1235 / run 32542757958**
- audit result: **HIGH_RISK_SEMANTIC_BLIND_SPOT_REPRODUCED**

이 audit의 목적은 MasterV라는 프로젝트 이름을 특별취급하는 규칙을 만드는 것이 아닙니다. 특정 프로젝트의 실제 고위험 의미가 generic Trust vocabulary에서 누락되는지 확인하고, 누락된다면 그 원인이 다른 프로젝트에도 적용 가능한 일반 semantic gap인지 분리하는 것입니다.

## 1. Evidence contamination boundary

Wave 1 corpus의 source cutoff는 `2026-08-21T03:00:00Z`입니다.

MasterV PR #3 (`MV-3`)은 이미 Wave 1 external-seen sample이므로 새로운 blind evidence가 아닙니다. 기존 human-frozen label은 다음과 같습니다.

```text
MV-3
expected = R3
semantic = release_security / signing_authority
```

따라서 이번 audit에서 MV-3은 **known seen anchor**로만 사용합니다.

PR #5, #7, #12는 Wave 1 cutoff 이후 source입니다. 다만 이번 audit을 위해 source를 열어 의미를 판정한 뒤 선택했으므로 이들 역시 blind holdout이라고 부르지 않습니다. 정확한 지위는 **post-Wave1 independent audit evidence, not blinded**입니다.

## 2. Replay ceiling

실제 GitHub patch에서 필요한 source line을 exact excerpt로 동결합니다. Audit test는 excerpt를 source-bound bounded diff로 재구성해 현재 v1.3 classifier를 재생합니다.

```text
replay = BOUNDED_EXACT_PATCH_EXCERPT_REPLAY
full original PR diff replay claim = NO
```

따라서 이 stage가 증명하는 것은 현재 classifier의 semantic discrimination behavior이며, 원본 PR 전체의 완전한 historical replay를 주장하지 않습니다.

## 3. Audit result

Initial exact-head CI #1235에서 source-inspection hypothesis가 그대로 재현되었습니다.

| Case | Evidence status | Policy expected | Trust v1.3 | Result |
|---|---|---:|---:|---|
| MV-3 signing trust-root anchor | Wave1 seen anchor | R3 | R2 | UNDERCLASSIFIED |
| MV-5 CRLF compatibility fix | post-Wave1 negative control | R2 | R2 | MATCH |
| MV-7 published updater acceptance verifier | post-Wave1 audit evidence | R4 | R3 | UNDERCLASSIFIED |
| MV-12 `deployment-surface.ts` | post-Wave1 path probe | R3 | R2 | UNDERCLASSIFIED |
| MV-12 legacy provider route guard | post-Wave1 path probe | R3 | R2 | UNDERCLASSIFIED |

```text
TOTAL_CASES = 5
UNDERCLASSIFIED = 4
MATCH = 1
OVERCLASSIFIED = 0
```

이 숫자는 MasterV 프로젝트 전체의 오류율을 의미하지 않습니다. 고위험 semantic boundary를 확인하기 위해 의도적으로 선택한 bounded audit corpus의 결과입니다.

## 4. MV-3 — known seen signing trust-root anchor

Production updater public signing authority를 새로운 key ID로 회전하고 native updater 및 Tauri release/bootstrap/RC config의 public trust root를 함께 변경합니다.

Frozen policy expectation:

```text
R3 — release security / signing authority
```

Observed v1.3:

```text
current = R2
result = UNDERCLASSIFIED
```

현재 path vocabulary에는 `signing`, `updater`, `public key`, `trust root` 자체를 high-risk R3로 올리는 일반 규칙이 없습니다. 이 miss는 새 evidence가 아니라 기존 Wave1 human-frozen R3 anchor의 재현입니다.

## 5. MV-5 — negative control

`desktop-rel-1-contract.mjs`가 Windows CRLF를 LF로 정규화하도록 한 줄 변경합니다.

Observed:

```text
release context != release authority mutation
expected = R2
current = R2
result = MATCH
```

따라서 단순히 release/updater 문맥이 존재한다는 이유로 모든 인접 변경을 R3로 올리는 방식은 부적절합니다.

## 6. MV-7 — post-Wave1 verifier-authority reproduction

PR의 핵심 제품은 이미 공개된 `v0.1.3 -> signed v0.1.4` updater path를 실제 설치로 검증하고, 성공 시 다음 acceptance evidence를 산출하는 verifier입니다.

```text
MASTERV_REL_1C_PUBLISHED_UPDATER_SIGNATURE_ACCEPTANCE_PASS
```

이 verifier의 성공만이 남은 updater acceptance gate를 닫을 수 있으므로 Wave 1 band intent상 **R4 verifier authority**입니다.

Observed v1.3:

```text
policy expected = R4
current = R3
result = UNDERCLASSIFIED
```

R4 semantic evidence에서 핵심 verifier:

```text
scripts/desktop-rel-1c-published-updater-windows.mjs
classification = SUPPORTING_REGRESSION_ONLY
is_r4_authority = false
```

동시에 bounded workflow evidence에는 `UNKNOWN` workflow semantics가 존재하여 PR-level floor를 R3까지 올리지만 R4 verifier authority까지는 도달하지 못합니다.

따라서 다음이 재현되었습니다.

```text
R4_SEMANTIC_UNDERDETECTION
= REPRODUCED_ON_POST_WAVE1_INDEPENDENT_AUDIT_EVIDENCE
```

단, source를 본 뒤 사례를 선택했으므로 **blind holdout/generalization claim은 하지 않습니다.**

## 7. MV-12 — latent R3 production-boundary gaps

PR #12 전체는 여러 contract/workflow와 함께 움직이므로 aggregate PR band와 핵심 production boundary file의 discrimination을 분리했습니다.

### `lib/deployment-surface.ts`

production에서 `gateway` 이외 surface를 fail closed하고 production execution surface authority 자체를 변경합니다.

```text
expected = R3
current = R2
result = UNDERCLASSIFIED
```

### `app/api/analyze/route.ts`

production legacy provider route를 request parsing/provider execution 전에 404로 차단하여 provider execution boundary를 변경합니다.

```text
expected = R3
current = R2
result = UNDERCLASSIFIED
```

이는 PR 전체가 companion workflow/verifier 때문에 높은 band를 받을 수 있더라도 direct authority file 자체의 semantic visibility가 부족할 수 있음을 보여줍니다.

## 8. Genericity check

Audit helper는 repository 이름을 risk signal로 받지 않습니다. Tests는 대표 case에 대해 repository metadata만 다음처럼 교체해 재생했습니다.

```text
gycha0109-beep/MasterV
-> neutral/example
```

결과:

```text
risk projection = IDENTICAL
audit outcome = IDENTICAL
```

따라서 이번 reproduction은 `MasterV` 문자열에 의존하지 않습니다.

금지되는 remediation 예:

```text
MasterV path -> R3/R4
masterv token -> high risk
특정 repo whitelist/blacklist
```

## 9. Defect decomposition

현재 evidence는 하나의 거대한 project-specific heuristic보다 최소 세 종류의 generic semantic gap을 가리킵니다.

### A. SIGNING_TRUST_ROOT_AUTHORITY_GAP

예:

- updater public signing key rotation
- signature verification trust-root mutation

목표 band: R3 계열.

### B. EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_GAP

예:

- real published artifact를 실행/검증하고 acceptance closure 결과를 직접 산출하는 verifier
- filename에 `live-verification` 또는 explicit `*_GATE`가 없어도 authority role이 실질적으로 동일한 경우

목표 band: R4 계열.

### C. PRODUCTION_EXECUTION_BOUNDARY_GAP

예:

- production deployment surface fail-closed selection
- provider execution route isolation

목표 band: R3 계열.

이 세 class는 동일 remediation으로 묶어서는 안 됩니다. R3 operational authority와 R4 verifier authority의 acceptance 조건이 다르기 때문입니다.

## 10. Regression / CI

Initial audit head:

```text
9e9479c89e68e139ce5d6fca3f712a24d97e5a19
```

CI:

```text
CI #1235
run 32542757958
Python 3.11 = SUCCESS
Python 3.13 = SUCCESS
Python 3.14 = SUCCESS
full unittest = SUCCESS
asset sync = SUCCESS
profile validation = SUCCESS
findings validation = SUCCESS
wheel build = SUCCESS
```

기존 authoritative code를 수정하지 않았기 때문에 기존 D1/D2/R4/Wave1 regression suite도 같은 full unittest 안에서 그대로 통과했습니다.

## 11. Governance conclusion

```text
PROJECT_SPECIFIC_HIGH_RISK_SEMANTIC_BLIND_SPOT = REPRODUCED
MASTERV_NAME_HEURISTIC_REQUIRED = NO
R4_SEMANTIC_UNDERDETECTION_POST_WAVE1 = REPRODUCED
R3_SIGNING_TRUST_ROOT_GAP = REPRODUCED
R3_PRODUCTION_EXECUTION_BOUNDARY_GAP = REPRODUCED
BLIND_HOLDOUT_CLAIM = NO
AUTHORITATIVE_REMEDIATION = NOT_AUTHORIZED
```

PR #52의 v1.3 bounded promotion을 소급하여 무효화하지 않습니다. 당시 명시된 limitation은 independent R4 holdout 부재였고, 이번 post-Wave1 evidence가 그 미검증 vocabulary에서 추가 miss를 드러낸 것입니다.

후속 단계는 세 gap을 generic evidence contract로 각각 calibration하는 작업이어야 하며, project-name/path-name blanket escalation을 사용해서는 안 됩니다.

## 12. Explicit non-actions

이 shadow audit은 다음을 하지 않습니다.

- `trust.py` 수정
- `packs.py` 수정
- schema/profile/review-pack 수정
- risk model version 변경
- MasterV-specific production rule 추가
- automation/pilot authorization
- Stage10K HUMAN_DECISION
- authoritative remediation
- merge authorization
