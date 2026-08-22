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
- verification: **PENDING EXACT-HEAD CI**

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

## 3. Audit cases

### MV-3 — known seen signing trust-root anchor

Production updater public signing authority를 새로운 key ID로 회전하고 native updater 및 Tauri release/bootstrap/RC config의 public trust root를 함께 변경합니다.

Frozen policy expectation:

```text
R3 — release security / signing authority
```

현재 path vocabulary에는 `signing`, `updater`, `public key`, `trust root` 자체를 high-risk R3로 올리는 일반 규칙이 없습니다.

### MV-5 — post-Wave1 negative control

`desktop-rel-1-contract.mjs`가 Windows CRLF를 LF로 정규화하도록 한 줄 변경합니다.

```text
release context != release authority mutation
expected = R2
```

이 사례는 surrounding release vocabulary 때문에 일반 compatibility fix가 과승격되는 것을 방지하는 control입니다.

### MV-7 — post-Wave1 published updater acceptance verifier

PR의 핵심 제품은 이미 공개된 `v0.1.3 -> signed v0.1.4` updater path를 실제 설치로 검증하고, 성공 시 다음 acceptance evidence를 산출하는 verifier입니다.

```text
MASTERV_REL_1C_PUBLISHED_UPDATER_SIGNATURE_ACCEPTANCE_PASS
```

이 verifier의 성공만이 남은 updater acceptance gate를 닫을 수 있으므로 Wave 1 band intent상 **R4 verifier authority**입니다.

그러나 현재 v1.3 R4 semantic contract는 일반 supporting script의 `assert`/`throw`만으로 R4를 주지 않고, explicit gate outcome 또는 `live-verification` role 같은 추가 증명을 요구합니다. MV-7의 verifier filename은 그 기존 seen vocabulary와 다릅니다.

### MV-12 path probes — production boundary semantics

PR #12 전체는 여러 contract/workflow와 함께 움직이므로 aggregate PR band와 핵심 production boundary file의 discrimination을 분리해야 합니다.

Audit은 두 direct path를 별도 probe합니다.

1. `lib/deployment-surface.ts`
   - production에서 `gateway` 이외 surface를 fail closed
   - production execution surface authority 자체를 변경
   - expected R3

2. `app/api/analyze/route.ts`
   - production legacy provider route를 request parsing/provider execution 전에 404 차단
   - authorization-like provider execution boundary 변경
   - expected R3

이 path-level probe는 PR #12 전체 band가 안전하더라도 companion workflow/verifier에 의해 핵심 authority file의 blind spot이 가려지는지 확인하기 위한 것입니다.

## 4. Genericity requirement

이번 audit helper는 repository 이름을 risk signal로 받지 않습니다. 동일 source evidence에서 repository metadata만 `neutral/example`로 바꿔도 risk projection과 audit outcome이 같아야 합니다.

금지되는 remediation 예:

```text
MasterV path -> R3
masterv token -> high risk
특정 repo whitelist/blacklist
```

허용 가능한 후속 연구 방향은 source semantics가 일반화되는 경우뿐입니다.

예:

- signing trust-root mutation
- executable release/update acceptance authority
- production deployment-surface authority
- fail-closed provider execution boundary

## 5. Expected diagnostic outcomes — pending CI confirmation

현재 source inspection에 기반한 test hypothesis는 다음입니다.

| Case | Policy expected | v1.3 hypothesis | Audit hypothesis |
|---|---:|---:|---|
| MV-3 seen signing anchor | R3 | R2 | UNDERCLASSIFIED |
| MV-5 negative control | R2 | R2 | MATCH |
| MV-7 updater acceptance verifier | R4 | R3 | UNDERCLASSIFIED |
| MV-12 deployment-surface path | R3 | R2 | UNDERCLASSIFIED |
| MV-12 legacy provider route guard | R3 | R2 | UNDERCLASSIFIED |

이 표는 exact-head CI가 통과하기 전까지 final result가 아닙니다. 실제 classifier output이 다르면 expectation을 약화시키지 않고 원인을 재분석합니다.

## 6. Governance consequence if reproduced

MV-3의 miss는 이미 알려진 external-seen evidence의 재현이므로 새 blind claim이 아닙니다.

MV-7이 실제로 R3 이하이면:

```text
R4_SEMANTIC_UNDERDETECTION
= post-Wave1 independent evidence에서 재현
```

이 경우 PR #52의 bounded v1.3 promotion 자체가 잘못되었다는 뜻은 아닙니다. 당시 명시한 대로 independent R4 holdout이 없었기 때문에, 새로운 vocabulary에서 추가 miss가 발견된 것입니다. 후속 authoritative remediation은 별도 승인 대상입니다.

MV-12 path probes가 R2이면 별도의 R3 semantic gap도 존재합니다. 이 경우 signing/release/security/deployment/access boundary를 하나의 거대한 heuristic으로 합치지 않고 각각 genericizable evidence class인지 검토해야 합니다.

## 7. Explicit non-actions

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
