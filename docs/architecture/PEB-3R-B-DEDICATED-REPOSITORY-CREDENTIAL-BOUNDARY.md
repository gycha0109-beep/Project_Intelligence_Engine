# PEB-3R-B — Dedicated Non-Production Repository & Credential Boundary Establishment

> Status: **IMPLEMENTATION PREPARED / EXTERNAL ADMIN RESOURCE CREATION BLOCKED**
>
> Authority baseline: `63121861d70b6df82801e85c7963775526826aa5`
>
> PEB-3R-A result: repository is the minimum GitHub-native credential isolation boundary.

## 1. Purpose

PEB-3R-A established that GitHub does not expose native write-credential scoping to one pull-request number. Therefore the formal PEB-3 calibration target must move outside the authoritative PIE repository into a dedicated non-production repository.

PEB-3R-B prepares the verifier and evidence contract required to prove that boundary before any governed external mutation can be dispatched.

This stage does **not** create production execution authority, automation authority, pilot authority, or a Stage10K human decision.

## 2. Required external boundary

The required target architecture is:

```text
DEDICATED NON-PRODUCTION REPOSITORY
        ↓
SELECTED-REPOSITORY GITHUB APP INSTALLATION
        ↓
DOWNSCOPED SHORT-LIVED INSTALLATION TOKEN
        ↓
EXACT-PR GOVERNED ADAPTER
        ↓
PEB-3E CONTROLLED DRAFT → READY → DRAFT CALIBRATION
```

Planned repository identity:

```text
gycha0109-beep/pie-peb3-calibration
```

The repository must be calibration-only and must carry no production deployment, production secret, business-source authority, or merge path into PIE main.

## 3. Current provider observation

The currently connected GitHub App installation is:

```text
installation_id = 81654749
```

Its accessible repository set includes multiple independent repositories, including PIE, K_beauty, BuildMap, MasterV, and Saju.

Therefore the currently connected credential is not accepted as the PEB-3R-B execution credential.

The current connector surface exposes repository/read-write operations within already accessible repositories, but does not expose actions to:

```text
create a new repository
change GitHub App installation repository selection
mint a repository-downscoped installation access token
```

That limitation is an execution-surface limitation, not evidence that GitHub itself lacks those administrative capabilities.

## 4. Implemented verifier

Implementation:

```text
src/review_system/trust_execution_isolation_boundary.py
```

Contract:

```text
TRUST_PEB3R_ISOLATION_BOUNDARY_V1
```

The verifier is report-only and side-effect-free. It accepts external/provider evidence and determines whether the PEB-3R boundary is sufficiently proven to permit later controlled non-production execution review.

It cannot create repositories, credentials, installations, tokens, pull requests, or mutations.

## 5. Repository requirements

The dedicated repository is accepted only if all of the following are proven:

```text
exists = true
calibration_only = true
production_deployment = false
production_secrets = false
business_source_authority = false
full_name = exact expected repository
```

Failure produces:

```text
DEDICATED_NONPRODUCTION_REPOSITORY_NOT_ESTABLISHED
```

## 6. Credential requirements

The formal credential must be:

```text
mechanism = GITHUB_APP_INSTALLATION_TOKEN
```

and provider evidence must prove:

```text
installation identity = exact
selected repository scope = proven
repository set = [dedicated calibration repository] exactly
token repository set = proven
token permission set = proven
bounded validity = proven
PIE repository write authority = false
production repository write authority = false
```

A broad connected-account credential is rejected.

Credential blockers are:

```text
SELECTED_REPOSITORY_GITHUB_APP_SCOPE_NOT_PROVEN
SHORT_LIVED_TOKEN_SCOPE_NOT_PROVEN
```

## 7. Adapter requirements

Credential scoping alone does not prove exact PR binding. The future adapter must independently constrain the request to:

```text
provider = GITHUB
repository = exact dedicated repository
resource_type = PULL_REQUEST
exact PR binding = true
exact head binding = true
exact precondition binding = true
allowed operations = {
  MARK_READY_FOR_REVIEW,
  CONVERT_TO_DRAFT
}
```

The following surfaces must all be absent:

```text
arbitrary command
arbitrary API/URL
merge
close
file write
branch write
workflow write
secret write
repository-settings write
```

Any violation produces:

```text
GOVERNED_ADAPTER_BINDING_NOT_READY
```

## 8. Provider evidence requirements

The verifier requires authoritative readback for:

```text
repository metadata
installation repository set
token permission set
```

Missing readback produces:

```text
AUTHORITATIVE_PROVIDER_SCOPE_EVIDENCE_INCOMPLETE
```

A local configuration claim cannot substitute for provider-issued scope evidence.

## 9. Current frozen evidence

Evidence:

```text
evidence/trust/peb3r-b-isolation-boundary-20260822.json
```

Current expected result:

```text
PEB-3R-B = BLOCKED

blockers =
  DEDICATED_NONPRODUCTION_REPOSITORY_NOT_ESTABLISHED
  SELECTED_REPOSITORY_GITHUB_APP_SCOPE_NOT_PROVEN
  SHORT_LIVED_TOKEN_SCOPE_NOT_PROVEN
  GOVERNED_ADAPTER_BINDING_NOT_READY
  AUTHORITATIVE_PROVIDER_SCOPE_EVIDENCE_INCOMPLETE

formal_dispatch_permitted = false
next_step = ESTABLISH_EXTERNAL_ADMIN_RESOURCE_AND_CREDENTIAL_BOUNDARY
```

## 10. Why adapter-only restriction is insufficient

The following is explicitly rejected:

```text
broad credential
+ adapter checks exact PR number
= target-scoped credential
```

That equation is false.

The required two-layer invariant remains:

```text
CREDENTIAL RESOURCE SCOPE
AND
ADAPTER REQUEST/TARGET SCOPE
```

Both must independently pass.

## 11. External administrator action boundary

The next uncompleted action requires a GitHub administrative surface that is not available through the current connected toolset.

It must establish:

1. a dedicated non-production repository,
2. a GitHub App installation whose selected repository set is that repository only for this calibration identity,
3. a short-lived installation token downscoped to that repository and the minimum PR/read permissions required,
4. provider readback proving the resulting repository and permission sets.

No formal PEB-3 mutation may occur before those facts are replayably available to the verifier.

## 12. Current authority ceiling

```text
PEB-3R-A = PASS / LANDED
PEB-3R-B = BLOCKED AT EXTERNAL ADMIN RESOURCE CREATION
PEB-3E = NOT STARTED

production_execution_authorized = false
formal_nonproduction_dispatch = false
automation_authorized = false
pilot_authorized = false
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 / existing R4 authority = UNCHANGED
```

The blocked result is intentional fail-closed behavior. PEB-3R-B becomes ready only after real provider-issued repository and credential-scope evidence exists.
