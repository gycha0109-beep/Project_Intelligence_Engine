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

Implementation-review hardening 전용 진단에서 Python 3.13 / 3.14 기준 다음 focused suites는 이미 성공했다.

```text
test_trust_reconciliation.py
test_trust_reconciliation_hardening.py
test_trust_reconciliation_review.py
```

Python 3.11 및 documentation-inclusive exact-head 전체 workflow 결과는 최종 authoritative run 확정 후 이 문서에 기록한다.

## 구현 리뷰에서 발견한 문제

상세 내용은 `STAGE-10C-IMPLEMENTATION-REVIEW.md`를 따른다.

핵심 발견:

1. current defect lifecycle을 사용한 temporal backfill 가능성
2. Outcome 이후 Finding/Artifact link의 소급 evidence 가능성
3. Evaluation same-revision non-holdout case로 인한 false ambiguity
4. Outcome `base_status` semantic projection 누락
5. orphan source manifest mapping silent ignore
6. symlink hardening regression의 lexical-path 검증 필요

모두 최종 full regression 전에 코드/회귀 테스트로 보완했다.

## 보완 사항

- historical as-of Outcome replay를 Defect lifecycle/link evidence에 적용
- conclusive Evaluation authority를 unique matching holdout case로 한정
- report semantic verifier에서 Outcome base status 재계산
- source manifest와 registry/event identity를 실행 전에 cross-check
- source replay verifier를 통해 source mutation을 최종적으로 검출

## 잔여 리스크

- standalone signed Independent Audit authority 없음
- Regression / Security Incident / False Positive Review 전용 authority 없음
- Evaluation의 external issuance time provenance는 별도 cryptographic authority가 아님
- Stage 10C는 Stage 10D denominator를 변경하지 않음
- Stage 10C PASS는 pilot authorization이 아님

## 다음 단계

최종 documentation-inclusive exact-head CI가 3.11/3.13/3.14에서 모두 green이면 PR을 Ready for Review로 전환한다.

그 이후에도:

```text
automation_authorized=false
pilot_authorized=false
```

를 유지하며, merge하지 않는다. 다음 별도 단계는 `R0 Pilot Safety Review`다.
