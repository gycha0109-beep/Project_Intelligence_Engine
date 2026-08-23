# PEB-3R-D — Live Isolated Target Binding

> Status: **PARTIAL PASS / TOKEN INSTANCE SCOPE READBACK BLOCKED**
>
> Starting PIE main: `3b741c4f8e766f220caf069aa5129112f02b3807`

## 1. Purpose

This stage records the first real dedicated non-production GitHub resource boundary and live Draft pull-request target for PEB-3E without performing the governed Draft → Ready mutation.

## 2. Dedicated repository boundary

A new GitHub organization and repository were established:

```text
organization = pie-peb3-lab
repository = pie-peb3-lab/pie-peb3-calibration
repository_id = 1343419049
visibility = public
purpose = calibration only
```

The repository carries no production deployment, production secret, business-source authority, or merge path into PIE main.

## 3. GitHub App installation isolation

A separate ChatGPT Codex Connector GitHub App installation exists for the organization:

```text
installation_id = 155854672
installation_account = pie-peb3-lab
repository_set = [pie-peb3-lab/pie-peb3-calibration]
```

Provider readback returned exactly one accessible repository for this installation. The separate personal-account installation remains independent and is not accepted as the PEB-3 execution credential.

Therefore the repository-level credential isolation requirement is now satisfied.

## 4. Live calibration target

The dedicated repository contains one inert calibration branch and Draft pull request:

```text
branch = calibration/peb3e-target-20260823
PR = #1
state = OPEN / DRAFT / UNMERGED
base_sha = 7813fd57037419ed9565016c70585d55cbd99438
head_sha = 295d73c9b263280705fe0ad66cd96d0edc5ee47c
changed_files = 1
```

The single changed file is calibration-only metadata. The PR explicitly has no merge intent.

## 5. Adapter live binding

The governed GitHub PR adapter implementation is already landed in PIE. The real target now supplies the exact constructor binding tuple:

```text
repository = pie-peb3-lab/pie-peb3-calibration
pr_number = 1
expected_head_sha = 295d73c9b263280705fe0ad66cd96d0edc5ee47c
expected_precondition = OPEN / DRAFT
```

Accordingly:

```text
ADAPTER_IMPLEMENTATION = READY
LIVE_TARGET_BINDING = PROVEN
```

No real Ready/Draft mutation has yet been attempted.

## 6. Remaining blockers

The frozen PEB-3R verifier still requires authoritative evidence for the actual short-lived GitHub App installation token instance used for formal dispatch:

```text
token repository set = proven
token permission set = proven
bounded validity / expiry = proven
```

The current connected GitHub surface exposes installation identity and installation repository-set readback, but does not expose the underlying installation access-token payload or expiry metadata.

Therefore the remaining blockers are narrowed to:

```text
SHORT_LIVED_TOKEN_SCOPE_NOT_PROVEN
AUTHORITATIVE_PROVIDER_SCOPE_EVIDENCE_INCOMPLETE
```

and:

```text
formal_dispatch_permitted = false
```

## 7. Authority ceiling

```text
production_execution_authorized = false
formal_nonproduction_dispatch = false
automation_authorized = false
pilot_authorized = false
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 / existing R4 authority = UNCHANGED
```

The next stage must resolve token-instance scope/readback without weakening the frozen PEB-3R contract. Only then may PEB-3E perform:

```text
DRAFT → READY → independent readback → DRAFT rollback → independent readback
```
