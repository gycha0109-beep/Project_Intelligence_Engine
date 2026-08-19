# Stage 9 Implementation Review

상태: `PASS`

권위 기준선: PR #16 HEAD `7d4de5a37295d6154158f715a383fd4e7f44d0a9`

최종 검증 HEAD: `783f6de0ca0d97709ae5b5bdfaac460b19f23514`

## 구현 결과

- JSON Schema 2020-12 기반 `buildmap-export.schema.json`을 source와 packaged asset에 추가했다.
- 검증된 Evidence Ledger에서 명시적으로 선택한 Run 하나만 export한다.
- Artifact body를 복사하지 않고 ID, type, relative path, SHA-256, media type과 byte size만 projection한다.
- Claim statement, Evidence summary·result 원문·locator, Finding title·impact·action, Defect signature·title·root cause·resolution을 export하지 않는다.
- raw GitHub discussion, patch, diff, log, credential·token·key 계열 artifact는 기본 제외한다.
- Finding→Defect와 Defect→Artifact 관계는 opaque ID, relation과 redacted 상태만 보존한다.
- Decision reason은 message와 expression 대신 group·reason ID만 보존한다.
- 전체 Ledger source row를 source fingerprint로 묶고, metadata projection hash, deterministic export ID와 outer export hash를 추가했다.
- self-contained schema·semantic verifier와 선택적 Ledger source replay verifier를 추가했다.
- atomic output과 symlink·traversal 방어를 추가했다.
- 기존 `pie`/`urs`에 `export-buildmap`, `validate-buildmap-export`를 additive하게 추가하고 동일 adapter의 `pie-buildmap` entrypoint를 제공한다.
- 기존 Ledger schema, artifact schema, dependency와 제품 버전은 변경하지 않았다.

## 구현 리뷰 중 발견·보완

### IR-1 — Finding과 Defect 관계 유실

초기 projection은 Finding과 Defect를 각각 export했지만 둘 사이의 연결을 보존하지 않았다.

**조치:** Finding에 정렬된 `defect_ids`를 추가하고 source replay에서 관계를 재계산한다.

### IR-2 — malformed reason reference에서 verifier 예외 가능

JSON Schema 오류가 있는 `reason_refs`에 list·object가 들어오면 semantic verifier의 set 연산이 예외를 발생시킬 수 있었다.

**조치:** 각 reference의 type과 필수 문자열을 먼저 검사한 뒤 canonical ordering과 중복을 판정한다. 악성 입력도 예외 대신 명시적 validation error가 된다.

### IR-3 — Defect의 Evidence Artifact 관계 유실

Defect current state는 export됐지만 reproducer, diagnostic 등 Artifact 관계가 누락돼 BuildMap이 근거 연결을 유지할 수 없었다.

**조치:** Defect에 `artifact_refs`를 추가했다. 각 reference는 `artifact_id`, relation, `artifact_redacted`만 포함하며 note와 actor 자유문은 제외한다.

### IR-4 — 적용 script 재실행으로 CLI·TOML 중복

검증용 적용 script가 이미 추가된 import와 entrypoint를 다시 삽입해 pyproject TOML 중복을 만들었다.

**조치:** 적용기를 exact-line deduplication 방식으로 고쳤고 최종 제품 diff에서 모든 적용·진단 자산을 제거했다. 이는 제품 런타임 결함이 아니라 작업 자동화 결함이었다.

### IR-5 — Defect Artifact reference 테스트의 순서 가정

제품은 reference를 artifact ID·relation으로 정렬하는데 초기 테스트는 redaction boolean 순서를 가정했다.

**조치:** relation key별로 `diagnostic=false`, `reproducer=true`를 검증하도록 테스트를 수정했다. 제품 동작은 변경하지 않았다.

## 안전성 검토

- Ledger 전체 integrity, FK, migration, Run artifact와 Defect registry projection을 검증한 뒤 읽는다.
- artifact body와 local `artifact_root`는 export하지 않는다.
- raw GitHub discussion 포함 여부는 schema에서 항상 `false`다.
- source identifier가 query, fragment, userinfo 또는 미지원 scheme을 포함하면 `pie://runs/<run-id>`로 대체한다.
- custom redaction glob 원문은 export하지 않고 canonical pattern set hash만 기록한다.
- redacted Artifact를 참조하는 Evidence, Finding, Decision, Policy와 Defect Artifact reference는 `artifact_redacted=true`를 명시한다.
- arrays, relationship IDs, reason references와 redaction flags는 canonical projection으로 재계산한다.
- outer hash를 다시 계산한 의미 변조도 source replay에서 차단한다.
- output은 temporary file, fsync, atomic replace를 사용한다.

## 남은 제한

- 첫 계약은 Run 하나만 export하며 history pagination과 incremental cursor는 제공하지 않는다.
- custom redaction pattern 원문을 공개하지 않으므로 source replay는 custom omission count까지 검증하지만 어떤 pattern이 사용됐는지는 복원하지 않는다.
- self-contained 검증은 source fingerprint의 원본 진실성을 증명하지 않으며 Ledger source replay가 필요하다.
- export는 signer identity, encryption과 transport authentication을 제공하지 않는다.
- BuildMap 측 실제 저장 adapter와 network 전달은 이번 Stage 범위가 아니다.
- local file과 SQLite cross-process locking은 제공하지 않는다.

## 판정

구현 리뷰: `PASS`

GitHub Actions run `30101785712`에서 문서와 Architecture index를 포함한 HEAD `783f6de0ca0d97709ae5b5bdfaac460b19f23514`의 Python 3.11·3.13·3.14 전체 regression과 wheel build가 통과했다.
