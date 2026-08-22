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

## 4. Real positive anchor

MasterV PR #3 changed the updater public signing authority consistently across native updater code and updater-aware release configuration.

The PR explicitly establishes a recoverable production updater signing authority while keeping the private key/password outside source control.

Frozen policy intent:

```text
signature verification trust-root mutation
= security / release authority
= R3
```

The shadow test first confirms current v1.4 still projects the representative runtime/config paths as R2, then checks the bounded candidate projection moves them to R3.

## 5. Negative controls

The calibration includes:

- same-PR supporting contract that validates the key ID but does not own the runtime/config trust root
- documentation containing signing/trust-root language
- test-only signature verification public key
- ordinary application crypto public key with no release/signature-verification authority
- example/development updater configuration

These must not trigger the candidate.

A synthetic generic positive using `trustRootPublicKey` in an artifact-signature production configuration demonstrates that the rule does not depend on MasterV, Tauri, or repository identity. This is only a genericity control, not independent real-world evidence.

## 6. Forbidden remediation

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

## 7. Acceptance gate

The shadow calibration may be marked PASS only if exact-head CI confirms:

```text
current Trust = v1.4
MV-3 runtime updater trust root: current R2 -> candidate R3
MV-3 release updater config trust root: current R2 -> candidate R3
same-PR supporting contract: no promotion
docs/test/example/ordinary-crypto negatives: no promotion
generic synthetic trust-root mutation: candidate R3
candidate never upgrades to R4
candidate never downgrades existing R3
all CI matrices = SUCCESS
```

Until exact-head CI succeeds:

```text
SIGNING_TRUST_ROOT_SHADOW_CALIBRATION = VALIDATION_PENDING
AUTHORITATIVE_REMEDIATION = NOT_AUTHORIZED
MERGE = NOT_AUTHORIZED
```

## 8. Non-actions

This stage does not:

- modify `trust.py`
- modify the authoritative R4 semantic evidence contract
- modify schemas or profiles
- address `PRODUCTION_EXECUTION_BOUNDARY_GAP`
- authorize automation or pilot operation
- create a Stage10K HUMAN_DECISION
- claim a blind holdout
- authorize merge
