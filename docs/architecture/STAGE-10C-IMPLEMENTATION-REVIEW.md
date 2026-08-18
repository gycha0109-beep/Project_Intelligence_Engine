# PIE Stage 10C — Implementation Review

## 목적

Stage 10C 구현 diff를 source-evidence 승격 공격 관점에서 별도로 리뷰하고, 단순 문자열 참조나 사후 변경이 confirmed Outcome으로 승격되는 경로를 제거한다.

## 변경 파일

핵심 리뷰 대상:

- `src/review_system/trust_reconciliation.py`
- `src/review_system/trust_reconciliation_cli.py`
- `src/review_system/trust_cli.py`
- `schemas/trust-reconciliation-sources.schema.json`
- `schemas/trust-reconciliation-report.schema.json`
- package asset schema copies
- `tests/test_trust_reconciliation*.py`
- `pyproject.toml`

Stage 10D evaluator와 observation policy 구현은 변경하지 않는다.

## 구현 내용

구현은 다음 책임을 분리한다.

1. Stage 10B assessment가 참조하는 Stage 10A Trust report를 semantic verify한다.
2. 동일 Trust report를 원래 request/profile/ledger/policy/evaluation/reground source로 replay한다.
3. `PRODUCTION_DEFECT` Outcome을 Defect Registry + Evidence Ledger의 실제 relation으로 다시 연결한다.
4. `CONTROLLED_EVALUATION` Outcome을 Trust report가 캡처한 exact Evaluation ID/hash와 source-revision holdout case로 다시 연결한다.
5. 독립 authority가 없는 Outcome 유형은 강한 provenance를 발명하지 않고 fail closed한다.
6. conclusive Outcome이 동일 authority를 중복 사용해 future evidence count를 부풀리지 못하게 authority key 중복을 차단한다.
7. 결과는 report-only reconciliation artifact로 기록한다.

고정 안전 플래그:

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
```

## 구현 리뷰에서 실제 발견한 문제

### 1. Defect lifecycle temporal backfill

초기 구현은 현재 Defect Registry의 `lifecycle_status`를 사용했다.

위험:

```text
Outcome 시점: OBSERVED
후속 시점: REPRODUCED
→ 과거 UNSAFE Outcome이 나중에 소급 confirmed 되는 경로
```

보완:

- registry event history에서 `Outcome.occurred_at` 이하 event만 replay한다.
- 그 시점의 `status_to` projection으로 lifecycle을 계산한다.
- `UNSAFE`는 Outcome 시점에 이미 `REPRODUCED` 이상이어야 한다.

### 2. Defect relation temporal backfill

초기 구현은 현재 Ledger의 finding relation을 확인했으므로, Outcome 이후 연결된 Finding이 과거 source revision 관계를 소급 증명할 수 있었다.

보완:

- Defect Registry `finding_links[].linked_at <= Outcome.occurred_at`만 후보로 사용한다.
- 그 후보 Finding의 Ledger run이 assessment와 동일 project/source_revision인지 확인한다.
- Outcome 이후 link는 relation ground truth에 포함하지 않는다.

### 3. Defect artifact temporal backfill

reproducer/diagnostic artifact 역시 현재 relation 존재만 확인하면 후속 evidence가 과거 Outcome을 소급 강화할 수 있었다.

보완:

- `artifact_links[].linked_at <= Outcome.occurred_at`만 인정한다.
- 해당 Artifact가 assessment와 동일 project/source_revision의 run에 속해야 한다.

### 4. Evaluation 동일 revision 다중 case ambiguity

초기 구현은 같은 `source_revision` case가 전체 dataset에서 하나여야 한다고 가정했다.

문제:

같은 revision이 development/validation/holdout에 합법적으로 반복되면 안전한 holdout evidence도 `AMBIGUOUS_AUTHORITY`가 될 수 있었다.

보완:

- conclusive Outcome은 `source_revision + split=holdout`으로 authority case를 좁힌다.
- 정확히 하나의 matching holdout case만 요구한다.
- non-holdout revision 중복은 holdout authority ambiguity를 만들지 않는다.

### 5. Outcome `base_status` semantic projection 누락

초기 self-verifier는 assessment status와 final duplicate status는 재계산했지만 Outcome `base_status` 자체를 `checks + outcome_type + verdict`에서 독립 재계산하지 않았다.

위험:

semantic field를 바꾸고 외부 hash를 다시 만든 report가 source replay 없이 구조 검증을 우회할 여지가 있었다.

보완:

- `_expected_outcome_base_status(...)`를 추가한다.
- report verifier가 Outcome type별 상태 우선순위를 재계산한다.
- `base_status`, duplicate-adjusted `status`, `reconciled`, summary, overall status, evidence snapshot, report ID, outer hash를 모두 다시 projection한다.
- source truth 자체의 재검증은 별도 `verify_reconciliation_report_sources(...)`가 담당한다.

### 6. Orphan source-manifest mapping

초기 구현은 registry에 없는 assessment/event source mapping을 manifest hash에는 포함하지만 reconciliation에는 사용하지 않았다.

문제:

오타 또는 의도적 orphan authority가 조용히 무시될 수 있었다.

보완:

- unknown assessment mapping reject
- unknown Outcome event mapping reject
- mapped `authority_type`과 실제 Outcome type 불일치 reject

### 7. Symlink 회귀 테스트의 lexical-path 문제

초기 hardening test 일부가 helper의 `resolve()`를 거치며 symlink path 자체가 target path로 정규화될 가능성이 있었다.

보완:

- 별도 regression에서 symlink를 `relative_to(root)` lexical path 그대로 manifest에 기록한다.
- reconciliation resolver가 symlink component를 직접 탐지해 reject하는지 검증한다.

## 검증 결과

구현 리뷰 회귀는 다음을 직접 고정한다.

- future lifecycle transition cannot backfill old Outcome
- future Finding link cannot backfill old revision relation
- same-revision non-holdout duplicates do not invalidate a unique holdout authority
- Outcome base-status semantic tamper + rehash reject
- orphan manifest assessment/event reject
- lexical symlink source reject

최종 Python matrix와 documentation-inclusive exact-head run은 `STAGE-10C-VALIDATION.md`에 기록한다.

## 보완 사항

- Defect UNSAFE는 문자열 `defect_id`가 아니라 exact registry + ledger import + same-revision historical relation + as-of lifecycle + as-of reproducer/diagnostic를 요구한다.
- Evaluation SAFE/UNSAFE는 exact Trust-bound Evaluation authority와 matching holdout case를 요구한다.
- unsupported provenance는 confirmed로 승격하지 않는다.
- report semantic verifier와 source replay verifier를 분리해 각각 self-consistency와 external authority mutation을 담당한다.

## 잔여 리스크

1. Evaluation report 자체에는 독립적인 external issuance timestamp authority가 없다. Stage 10C는 Evaluation ID/hash, semantic validity, Trust binding, source revision을 증명하지만 해당 Evaluation이 Outcome 이전에 외부 시스템에서 발행됐다는 별도 cryptographic time provenance까지 증명하지 않는다.
2. `INDEPENDENT_AUDIT`의 standalone signed provenance authority가 아직 없다.
3. `REGRESSION`, `SECURITY_INCIDENT`, `FALSE_POSITIVE_REVIEW` 전용 authority contract가 아직 없다.
4. Stage 10C는 Stage 10D denominator를 변경하지 않는다. reconciliation artifact를 threshold denominator에 적용하는 결정은 R0 Pilot Safety Review의 책임이다.

## 다음 단계

Stage 10C가 green이어도 자동화 권한은 생기지 않는다.

다음 별도 단계는 `R0 Pilot Safety Review`이며, 그 단계에서 처음으로 Stage 10A classifier + Stage 10B confirmed Outcomes + Stage 10C reconciliation + Stage 10D observation threshold evidence를 함께 평가한다.
