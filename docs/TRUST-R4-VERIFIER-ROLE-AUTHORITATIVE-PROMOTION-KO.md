# Trust R4 Verifier-Role Authoritative Promotion

## Status

- defect: `EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_GAP`
- shadow source: PR #54 / `TRUST_R4_EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_SHADOW_V1`
- promotion PR: #55
- stacked base: PR #54 exact head `7630a68ff2b1f434b1b9266a03f8f3557a8f51bd`
- authoritative main at promotion start: `7aa435f1b5afd208a05b222f5bed55da77d4c6e8`
- historical Trust risk model: `1.3`
- promotion candidate Trust risk model: `1.4`
- mode: `REPORT_ONLY`
- `automation_authorized = false`
- `pilot_authorized = false`
- Stage10K HUMAN_DECISION: **NO**
- merge: **not authorized**
- blind R4 generalization claim: **NO**

## 1. Promotion purpose

PR #54 demonstrated that one real post-Wave1 executable acceptance verifier can be separated from ordinary supporting regression scripts without adding repository-name or filename-only heuristics.

The positive source is MasterV PR #7:

```text
scripts/desktop-rel-1c-published-updater-windows.mjs
```

Current v1.3 semantic classification:

```text
SUPPORTING_REGRESSION_ONLY
is_r4_authority = false
```

The file performs real published-release observation, fail-closed assertions, signed updater acceptance verification and durable evidence recording. Under the frozen risk-band intent the verifier authority itself is R4.

The promotion therefore makes the bounded verifier-role discriminator authoritative for the new Trust risk model only.

## 2. Versioning strategy

The v1.3 meaning is not mutated in place.

```text
Trust v1.3
R4 evidence contract = TRUST_R4_SEMANTIC_UNDERDETECTION_SHADOW_V1
verifier-role extension = absent

Trust v1.4
R4 evidence contract = TRUST_R4_EXECUTABLE_ACCEPTANCE_VERIFIER_ROLE_AUTHORITY_V1
verifier-role extension = authoritative candidate
```

Reports carrying `risk_model_version = 1.3` continue to rebuild and normalize R4 evidence under the v1.3 contract. Reports carrying `risk_model_version = 1.4` use the v1.4 contract.

This preserves historical report/source replay rather than reinterpreting old evidence through a newer semantic contract.

## 3. Source-bound authority contract

The verifier-role discriminator is not accepted as caller-provided semantic authority.

R4 evidence continues to be derived from the same bound source pair used by Trust:

- exact GitHub PR head revision
- exact changed-file set
- GitHub source evidence hash
- full supplied PR diff SHA-256
- full supplied PR diff byte length
- exact per-file diff section
- per-file patch SHA-256
- canonical R4 evidence fingerprint

Missing or mismatched source binding fails evidence construction.

No source pair means no verifier-role semantic R4 claim.

## 4. v1.4 discriminator

The frozen v1.3 semantic analyzer runs first.

Only files currently classified as:

```text
SUPPORTING_REGRESSION_ONLY
```

may be reconsidered.

Promotion to the existing authority class:

```text
EXECUTABLE_VERIFICATION_GATE_AUTHORITY
```

requires the combined bounded evidence established in PR #54:

1. explicit acceptance / verification / closure `PASS|SUCCESS` outcome
2. external or operational observation
3. durable evidence output
4. published / production / hosted / release-acceptance context
5. fail-closed behavior
6. executable assertions
7. no explicit evaluation-only ceiling

The implementation persists the candidate signal projection in the v1.4 R4 evidence object as derived evidence. It does not rely on repository identity.

## 5. Positive correction

For the MasterV PR #7 live published updater acceptance verifier:

```text
v1.3 = SUPPORTING_REGRESSION_ONLY / not R4
v1.4 = EXECUTABLE_VERIFICATION_GATE_AUTHORITY / R4
```

Trust v1.4 therefore produces:

```text
reason = SEMANTIC_R4_AUTHORITY
effective_band = R4
```

when the exact source-bound evidence is supplied.

The same semantic source remains below R4 when no source pair is available.

## 6. Negative controls

The promotion preserves the PR #54 negative boundary.

### Same-PR real negative

```text
scripts/desktop-rel-1c-contract.mjs
```

The script references the live verifier acceptance marker but does not perform the external operational acceptance observation or durable acceptance evidence itself.

Result:

```text
v1.4 = SUPPORTING_REGRESSION_ONLY
R4 promotion = NO
```

### Synthetic negatives

The following remain non-R4:

- live regression + durable smoke log without acceptance authority outcome
- acceptance marker contract without live observation/evidence
- live synthetic evaluation with explicit evaluation-only ceiling
- live acceptance output without durable evidence

Synthetic false-positive promotions remain zero in the bounded calibration matrix.

## 7. Existing R4 semantic regression

The pre-v1.4 R4 fixture remains unchanged.

Existing real seen R4 positives:

```text
KB-262
KB-272
KB-277
KB-279
AR-30
```

remain R4 in v1.4: **5/5 preserved**.

Existing controls:

```text
RW-54
KB-275
NEG-DOC-VERIFICATION
NEG-DOMAIN-POLICY
```

remain non-R4: **4/4 preserved**.

## 8. Historical compatibility

Historical version support remains explicit:

```text
1.1
1.2
1.3
1.4
```

The D2 generic-policy-token correction remains active from v1.2 onward.

The v1.3 R4 semantic evidence contract can still be:

- rebuilt
- normalized
- embedded in a Trust report
- verified from report contents
- replayed from the exact GitHub source + diff pair

The v1.4 report can independently be built/replayed from the same source pair while producing the new verifier-role R4 outcome.

## 9. Wave 1 regression

Existing authoritative Wave 1 regression tests remain part of the full suite.

The required invariant remains:

```text
Wave1 = 34 / 34 acceptable
underclassification = 0
```

The verifier-role change does not rewrite Wave 1 frozen labels or claim a new blind R4 holdout.

## 10. CI provenance

### CI #1259

Head:

```text
cb0292ccf69a52aa52bbd71b494e349f20516b6c
```

The new authoritative promotion tests all passed, including:

- MV-7 v1.3 vs v1.4 semantic split
- v1.4 R4 correction
- verifier-role negative matrix
- existing R4 positive/negative preservation
- v1.3 historical evidence normalization
- v1.3 and v1.4 report/source replay
- no-source no-R4 behavior

The full suite had exactly one failure:

```text
test_contract_is_shadow_only_on_v13_authority
```

Root cause:

The frozen PR #54 shadow test asserted the mutable current constant:

```text
TRUST_RISK_MODEL_VERSION == "1.3"
```

After the promotion candidate moved current to v1.4, that assertion no longer represented the historical authority it intended to pin.

This was a historical-version test maintenance defect, not a classifier, label, source-binding or negative-control failure.

### Historical pin correction

Commit:

```text
8ac1a70b2fe3a5ac98bf0503a9ee33b0aa90dc38
```

The shadow test now explicitly asserts:

```text
TRUST_RISK_MODEL_V1_3 == "1.3"
TRUST_RISK_MODEL_VERSION == "1.4"
```

No shadow classifier, fixture, candidate threshold or expected semantic classification changed.

### CI #1261

Run:

```text
32546409554
```

Result:

```text
Python 3.11 = SUCCESS
Python 3.13 = SUCCESS
Python 3.14 = SUCCESS
full unittest = SUCCESS
asset sync = SUCCESS
Journey Connect profile = SUCCESS
BEJEWELY profile = SUCCESS
BuildMap profile = SUCCESS
generic-webapp profile = SUCCESS
findings validation = SUCCESS
wheel build = SUCCESS
```

A final exact-head CI is required after this result-freeze document is committed.

## 11. Explicit non-actions

This promotion does not:

- address `SIGNING_TRUST_ROOT_AUTHORITY_GAP`
- address `PRODUCTION_EXECUTION_BOUNDARY_GAP`
- add MasterV/repository-name heuristics
- add PASS-only or filename-only R4 heuristics
- change workflow semantics authority
- authorize automation
- authorize pilot operation
- create a Stage10K HUMAN_DECISION
- claim blind R4 generalization
- authorize merge

## 12. Promotion acceptance condition

The promotion may be marked `PASS` only if the final exact-head CI after this documentation freeze confirms all of:

```text
Trust current candidate = v1.4
v1.3 historical replay = preserved
MV-7 live verifier = authoritative R4 in v1.4
same-PR supporting contract = non-R4
synthetic verifier-role false positives = 0
existing R4 positives = 5/5 preserved
existing R4 negatives = 4/4 preserved
Wave1 = 34/34 acceptable
Wave1 underclassification = 0
all CI matrices = SUCCESS
```

Until that final exact-head CI succeeds:

```text
R4_VERIFIER_ROLE_AUTHORITATIVE_PROMOTION = VALIDATION_PENDING
PR55_MERGE = NOT_AUTHORIZED
```
