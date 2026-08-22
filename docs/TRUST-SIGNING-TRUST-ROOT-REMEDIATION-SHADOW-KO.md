# Trust Signing Trust-Root Authority Gap — Shadow Calibration

## Status

- defect: `SIGNING_TRUST_ROOT_AUTHORITY_GAP`
- contract: `TRUST_SIGNING_TRUST_ROOT_AUTHORITY_SHADOW_V1`
- authoritative main at calibration start: `6b853758991dc5169cc9d3a754fca70f7a17e17f`
- authoritative Trust risk model: `1.4`
- target band: `R3`
- mode: `REPORT_ONLY`
- authority: `SHADOW_ONLY`
- `automation_authorized = false`
- `pilot_authorized = false`
- authoritative remediation: **NOT AUTHORIZED**
- Stage10K HUMAN_DECISION: **NO**
- blind holdout/generalization claim: **NO**
- shadow calibration result: **PASS**

## 1. Purpose

The MasterV evidence audit reproduced a generic R3 underclassification where a production updater signature-verification public trust root was rotated but current Trust remained R2.

This stage calibrates only that defect. It does not address production execution boundaries and does not reopen the now-landed R4 verifier-role track.

## 2. Evidence boundary

The real positive anchor is MasterV PR #3 (`MV-3`). It is already a Wave 1 external-seen sample with a human-frozen R3 expectation for `release_security / signing_authority`.

Therefore:

```text
MV-3 = KNOWN SEEN POSITIVE
new blind evidence = NO
blind generalization = NO
```

Two runtime/config paths from the same signing-key rotation event are used to test surface discrimination:

- `src-tauri/src/updater.rs`
- `src-tauri/tauri.windows-independent-updater-release.conf.json`

They are not counted as two independent real-world positives; they are two surfaces of one known authority mutation.

## 3. Candidate semantic boundary

The candidate does **not** elevate changes because they contain `release`, `updater`, `public key`, `signature`, or `production` individually.

A candidate R3 trust-root mutation requires all of:

1. signature-verification trust material is present
2. signing / signature-verification / updater trust context is present
3. operational production/release/updater context is present
4. the changed text performs a concrete trust-root/public-verification-key assignment
5. the path is a runtime or configuration surface, not docs/tests/supporting scripts/examples

Candidate reason:

```text
SEMANTIC_R3_SIGNING_TRUST_ROOT_CANDIDATE
```

Candidate band:

```text
R3
```

The candidate cannot lower an already-R3/R4 result and does not create an R4 claim.

## 4. Real positive anchor result

MasterV PR #3 changed the updater public signing authority consistently across native updater code and updater-aware release configuration.

The PR explicitly establishes a recoverable production updater signing authority while keeping the private key/password outside source control.

Frozen policy intent:

```text
signature verification trust-root mutation
= security / release authority
= R3
```

Exact calibration result:

```text
src-tauri/src/updater.rs
current v1.4 = R2
candidate    = R3

src-tauri/tauri.windows-independent-updater-release.conf.json
current v1.4 = R2
candidate    = R3
```

This confirms the original R3 underclassification still exists on current v1.4 and the bounded candidate corrects it without producing R4.

## 5. Negative and genericity controls

The calibration includes:

- same-PR supporting contract that validates the key ID but does not own the runtime/config trust root
- documentation containing signing/trust-root language
- test-only signature verification public key
- ordinary application crypto public key with no release/signature-verification authority
- example/development updater configuration

All remained non-promoted.

A synthetic generic positive using `trustRootPublicKey` in an artifact-signature production configuration triggers R3, demonstrating that the rule does not depend on MasterV, Tauri, or repository identity. This is only a genericity control, not independent real-world evidence.

Observed result:

```text
same-PR supporting contract = NO PROMOTION
documentation control       = NO PROMOTION
test-only key control       = NO PROMOTION
ordinary crypto control     = NO PROMOTION
example/dev updater control = NO PROMOTION
generic synthetic positive  = R3 CANDIDATE
existing R3 control         = remains R3
R4 promotion                = NONE
```

## 6. Initial CI failure and correction

Initial shadow head:

```text
02b907551557296fdecba659c552018146979079
```

CI:

```text
#1268
run = 32548435530
result = FAILED at full unittest
```

Source diagnosis found a parser asymmetry in the shadow-only trust-root assignment matcher: JSON-style quoting was explicitly accepted for `"pubkey"`, but the generic `"trustRootPublicKey"` form used by the repository-neutral synthetic positive did not accept surrounding quotes.

This was not a policy-band relaxation and did not change the positive/negative evidence boundary. The assignment matcher was normalized so all recognized trust-root key names allow optional JSON/YAML-style quoting.

Correction commit:

```text
3d6f542a2ce6159e21c50e3619da41dd72378f82
```

No fixture expectation, policy target, real positive label, negative-control label, or authoritative Trust behavior was changed.

## 7. Successful calibration CI

CI after the parser normalization:

```text
CI #1275
run = 32548803887
head = 3d6f542a2ce6159e21c50e3619da41dd72378f82

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

A final exact-head CI is required after this result-freeze document commit.

## 8. Forbidden remediation

This calibration explicitly rejects:

```text
MasterV -> R3
updater filename -> R3
release filename -> R3
public key mention -> R3
signature mention -> R3
all crypto changes -> R3
all config changes -> R3
```

## 9. Acceptance result

The calibrated invariant is:

```text
current Trust = v1.4
MV-3 runtime updater trust root: current R2 -> candidate R3
MV-3 release updater config trust root: current R2 -> candidate R3
same-PR supporting contract: no promotion
docs/test/example/ordinary-crypto negatives: no promotion
generic synthetic trust-root mutation: candidate R3
candidate never upgrades to R4
candidate never downgrades existing R3
```

Subject to final exact-head CI after this documentation freeze:

```text
SIGNING_TRUST_ROOT_SHADOW_CALIBRATION = PASS
AUTHORITATIVE_REMEDIATION = NOT_AUTHORIZED
MERGE = NOT_AUTHORIZED
```

## 10. Non-actions

This stage does not:

- modify `trust.py`
- modify the authoritative R4 semantic evidence contract
- modify schemas or profiles
- address `PRODUCTION_EXECUTION_BOUNDARY_GAP`
- authorize automation or pilot operation
- create a Stage10K HUMAN_DECISION
- claim a blind holdout
- authorize merge
