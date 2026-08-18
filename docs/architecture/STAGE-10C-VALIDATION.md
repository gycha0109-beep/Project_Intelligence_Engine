# PIE Stage 10C — Validation

## 목적

Stage 10C Source Replay & Outcome Reconciliation이 기존 PIE 계약을 깨지 않으면서 report-only source verification artifact를 생성하고, self-asserted Outcome metadata를 confirmed source evidence로 잘못 승격하지 않는지 검증한다.

## 변경 파일

검증 범위는 다음을 포함한다.

- reconciliation core / CLI
- root + package reconciliation schemas
- Trust CLI delegation
- focused reconciliation tests
- hardening tests
- implementation-review regression tests
- architecture docs
- package asset sync
- 기존 전체 unittest regression
- 기존 `urs` validation commands
- wheel build

## 구현 내용 검증 기준

### Assessment

- exact Trust report identity + original source replay → `RECONCILED`
- report hash / ID / project / task / revision / projection mismatch → fail closed
- source mutation after report generation → replay mismatch
- semantic tamper + outer rehash → verifier reject

### PRODUCTION_DEFECT

- exact Defect Registry + exact imported Ledger authority
- same project / same source revision historical Finding relation
- Outcome 시점 lifecycle replay
- Outcome 시점 이전 reproducer/diagnostic relation
- SAFE verdict를 Defect authority로 증명하는 경로 차단
- future lifecycle/finding/artifact backfill 차단

### CONTROLLED_EVALUATION

- semantic Evaluation verification
- exact Evaluation ID/hash Outcome reference
- exact Stage 10A Trust-bound Evaluation ID/hash
- matching source revision holdout authority
- repeatability / gate / protected-negative semantics
- broad aggregate FAIL을 task-level UNSAFE로 오인하지 않음

### General safety

- unsupported source authority fail closed
- independent audit provenance-unverified
- unsupported/unproven authority boolean escalation + full rehash reject
- duplicate conclusive authority reuse reject
- orphan manifest mapping reject
- path traversal reject
- symlink input/output reject
- atomic replace failure에서 기존 output 보존
- generated_at이 evidence identity를 변경하지 않음
- fixed `automation_authorized=false`
- fixed `pilot_authorized=false`
- Stage 10D threshold semantics unchanged

## 검증 명령

최종 CI는 기존 authoritative workflow를 그대로 사용한다.

```text
pip install -e .
python scripts/sync_package_assets.py
python -m unittest discover -s tests -v
urs version
urs validate-profile profiles/examples/journey-connect.yml
urs validate-profile profiles/examples/bejewely.yml
urs validate-profile profiles/examples/buildmap.yml
urs validate-profile profiles/examples/generic-webapp.yml
urs validate-findings examples/findings.sample.json
pip wheel . --no-deps --wheel-dir dist-ci
```

Python matrix:

```text
3.11
3.13
3.14
```

## 검증 결과

구현 및 hardening 단계에서 connector가 unittest traceback을 노출하지 않는 제약 때문에 임시 진단 workflow를 사용해 full-discovery failure identity를 단계적으로 분리했다. 임시 진단은 최종 branch에 남기지 않는다.

진단 중 실제 테스트 결함 두 가지를 추가로 발견했다.

1. symlink hardening test가 `Path.resolve()`를 거쳐 symlink target path로 바뀌어 lexical symlink를 실제로 검사하지 못하던 문제
2. temporal-backfill review fixture가 Stage 10B assessment capture보다 이른 Outcome timestamp를 사용해 Trust Comparison event ordering 계약을 위반하던 문제

두 테스트를 각각 lexical symlink path와 독립 Outcome Defect authority timeline으로 교정했다.

교정 후 code/hardening regression authority:

```text
workflow run #734
run ID 32089294671
```

결과:

```text
Python 3.11 SUCCESS
Python 3.13 SUCCESS
Python 3.14 SUCCESS
full unittest result marker CLEAN
asset sync SUCCESS
urs version SUCCESS
all example profile validations SUCCESS
sample findings validation SUCCESS
wheel build SUCCESS
```

이 run은 구현/hardening 회귀가 clean함을 확인하기 위한 진단 workflow다.

그 뒤 최종 diff review에서 replay 가능한 authority가 없는 Outcome 유형의 self-verifier escalation 가능성을 추가 발견했다. `independent_provenance_verified` 또는 `authority_supported` check까지 공격자가 true로 바꾸고 status/summary/hash를 함께 재계산하는 경우를 차단하기 위해 report schema에 type별 상수 불변식을 추가했다.

```text
INDEPENDENT_AUDIT → PROVENANCE_UNVERIFIED / reconciled=false
REGRESSION → UNSUPPORTED_SOURCE / reconciled=false
SECURITY_INCIDENT → UNSUPPORTED_SOURCE / reconciled=false
FALSE_POSITIVE_REVIEW → UNSUPPORTED_SOURCE / reconciled=false
```

root schema와 package asset schema를 동일하게 갱신하고, check boolean + status + summary + evidence snapshot + report ID + report SHA 전체를 재작성하는 공격 regression을 추가했다.

최종 Stage 10C terminal authority는 이 마지막 hardening을 포함한 documentation-inclusive exact-head 원본 workflow run으로 판단한다.

## 구현 리뷰에서 발견한 문제

상세 내용은 `STAGE-10C-IMPLEMENTATION-REVIEW.md`를 따른다.

핵심 발견:

1. current defect lifecycle을 사용한 temporal backfill 가능성
2. Outcome 이후 Finding/Artifact link의 소급 evidence 가능성
3. Evaluation same-revision non-holdout case로 인한 false ambiguity
4. Outcome `base_status` semantic projection 누락
5. orphan source manifest mapping silent ignore
6. symlink hardening regression의 lexical-path 검증 필요
7. temporal-backfill review fixture의 Stage 10B event ordering 위반
8. authority 없는 Outcome의 self-verifier boolean escalation 가능성

모두 최종 documentation-inclusive exact-head regression 전에 코드/schema/회귀 테스트로 보완했다.

## 보완 사항

- historical as-of Outcome replay를 Defect lifecycle/link evidence에 적용
- conclusive Evaluation authority를 unique matching holdout case로 한정
- report semantic verifier에서 Outcome base status 재계산
- source manifest와 registry/event identity를 실행 전에 cross-check
- source replay verifier를 통해 source mutation을 최종적으로 검출
- symlink regression은 lexical path 그대로 manifest에 넣어 실제 resolver rejection을 검증
- temporal-backfill regression은 Trust assessment Ledger와 분리된 Outcome Defect authority를 사용해 source replay mutation 없이 시간축을 검증
- 원본 authority가 없는 Outcome의 allowed status/check는 schema에서 상수로 fail closed

## 잔여 리스크

- standalone signed Independent Audit authority 없음
- Regression / Security Incident / False Positive Review 전용 authority 없음
- Evaluation의 external issuance time provenance는 별도 cryptographic authority가 아님
- Stage 10C는 Stage 10D denominator를 변경하지 않음
- Stage 10C PASS는 pilot authorization이 아님

## 다음 단계

마지막 hardening을 포함한 documentation-inclusive exact-head CI가 3.11/3.13/3.14에서 모두 green이면 PR을 Ready for Review로 전환한다.

그 이후에도:

```text
automation_authorized=false
pilot_authorized=false
```

를 유지하며, merge하지 않는다. 다음 별도 단계는 `R0 Pilot Safety Review`다.
