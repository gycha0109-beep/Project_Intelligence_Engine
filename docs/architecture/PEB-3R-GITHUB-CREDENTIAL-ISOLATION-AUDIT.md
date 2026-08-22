# PEB-3R-A — GitHub Target-Scoped Credential Feasibility & Isolation Boundary Audit

> Status: **AUDIT COMPLETE — PR-OBJECT CREDENTIAL SCOPING NOT AVAILABLE; REPOSITORY ISOLATION REQUIRED**
>
> Authority baseline: `3c26a3f4265fea55ccf95e28ed58188a4654fc2c`
>
> Existing controlled target: PR #61 / `39ba94c0b847017f1f9f8e315fdbb198c15b65b9` / `OPEN / DRAFT / UNMERGED`
>
> This stage is side-effect-free with respect to the PEB-3 formal target. It does not mark PR #61 ready, merge it, create production authority, enable automation, enable a pilot, or change Trust v1.5 / existing R4 authority.

## 1. Audit question

PEB-3 stopped before formal `GITHUB_PR_MUTATION` dispatch because the connected GitHub credential could not be proven to be scoped to the designated target.

The PEB-3R-A question is:

> Can GitHub issue a credential whose effective write authority is natively restricted to one specific pull request object, such as PIE PR #61, while permitting `MARK_READY_FOR_REVIEW` / `CONVERT_TO_DRAFT` only for that object?

If not, what is the smallest native GitHub resource boundary that can carry independently provable write scoping?

## 2. Starting authority

```text
main = 3c26a3f4265fea55ccf95e28ed58188a4654fc2c
Trust = v1.5 / REPORT_ONLY
PEB-1 = PASS / LANDED
PEB-2 = PASS / LANDED
PEB-3 = BLOCKED / LANDED BLOCKER EVIDENCE
PEB-3 blocker = TARGET_SCOPED_CREDENTIAL_NOT_PROVEN
```

Formal PEB-3 target remains:

```text
repository = gycha0109-beep/Project_Intelligence_Engine
PR = #61
state = OPEN / DRAFT
head = 39ba94c0b847017f1f9f8e315fdbb198c15b65b9
merge intent = NONE
```

## 3. GitHub native credential boundaries

### 3.1 Fine-grained personal access tokens

GitHub's fine-grained personal access token model selects:

1. one resource owner,
2. repository access,
3. repository/account permissions.

Repository access can be restricted to selected repositories, and GitHub recommends selecting the minimum repositories and permissions necessary.

The native selection surface is repository-level. GitHub does not expose a pull-request-number selector when creating a fine-grained personal access token.

Relevant GitHub documentation:

- `https://docs.github.com/en/enterprise-cloud@latest/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens`
- `https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens`

Therefore:

```text
FINE_GRAINED_PAT_REPOSITORY_SCOPE = AVAILABLE
FINE_GRAINED_PAT_SINGLE_PR_SCOPE = NOT AVAILABLE IN DOCUMENTED NATIVE MODEL
```

A token with Pull Requests write permission for the PIE repository cannot be treated as credential-level proof that PR #61 is the only writable PR in that repository.

### 3.2 GitHub App installation access

A GitHub App installation can be installed for all repositories or only selected repositories.

GitHub App installation access tokens can additionally be narrowed when minted by specifying:

```text
repositories / repository_ids
permissions
```

The resulting token cannot gain repositories or permissions that the installation/app itself was not granted, and installation access tokens expire after one hour.

Relevant GitHub documentation:

- `https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party`
- `https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app`
- `https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app`

Again, the documented repository selector is repository-level. The installation-token API accepts repository names/IDs and permission names, not a pull-request-number allowlist.

Therefore:

```text
GITHUB_APP_SELECTED_REPOSITORY_SCOPE = AVAILABLE
GITHUB_APP_PERMISSION_DOWNSCOPING = AVAILABLE
GITHUB_APP_SINGLE_PR_CREDENTIAL_SCOPE = NOT AVAILABLE IN DOCUMENTED NATIVE MODEL
```

## 4. PEB-3R-A feasibility result

The PEB-3 requirement cannot be satisfied by claiming that a repository-scoped credential is itself PR #61-scoped.

That would collapse two different controls:

```text
CREDENTIAL_RESOURCE_SCOPE
!=
ADAPTER_REQUEST_TARGET_BINDING
```

An adapter can reject every PR number except `61`, but if the credential itself carries write authority over other pull requests in the same repository, the credential has not been proven target-scoped at PR-object granularity.

PEB-3 explicitly requires credential or provider authority bounded to the designated target **or an equivalently isolated non-production resource boundary**.

The supported solution is therefore to move the credential isolation boundary outward to a dedicated repository.

## 5. Required isolation boundary

The minimum acceptable GitHub-native external boundary for the next stage is:

```text
DEDICATED_NON_PRODUCTION_REPOSITORY
```

Required properties:

```text
purpose = PEB execution calibration only
production deployment = none
production secrets = none
production branch = none
business source authority = none
merge into PIE main = none
```

The credential must have write authority only to this dedicated calibration repository among private/write-relevant targets.

Within that repository, the governed adapter must independently hard-bind the allowed PR identity and allowed operations.

Therefore the complete boundary is two-layered:

```text
LAYER 1 — CREDENTIAL BOUNDARY
GitHub App installation/access token
→ dedicated calibration repository only
→ minimum repository permissions only

LAYER 2 — ADAPTER BOUNDARY
exact repository
+ exact PR number
+ exact head SHA
+ exact precondition
+ allowlisted operation
+ allowlisted rollback operation
+ no arbitrary request / shell surface
```

Credential isolation and adapter target binding are complementary; neither substitutes for the other.

## 6. Preferred credential mechanism

For PEB calibration, a dedicated GitHub App installation is preferred over a long-lived personal token because GitHub documents the following useful controls:

- installation on selected repositories,
- installation-token repository downscoping,
- installation-token permission downscoping,
- token expiry after one hour.

The target design is:

```text
GitHub App
  installation repository selection
    = dedicated non-production calibration repository only

installation access token
  repositories
    = [dedicated calibration repository]
  permissions
    = minimum required for governed PR mutation/readback
  lifetime
    = provider-defined short-lived installation token
```

This audit does not create the GitHub App, installation, repository, private key, or token.

A fine-grained PAT restricted to a dedicated repository is technically a repository-isolation candidate, but it is not preferred for the governed adapter because the GitHub App installation-token model gives a more explicit application identity and short-lived token lifecycle.

## 7. Adapter requirements after repository isolation

The future governed adapter must not expose generic GitHub or shell capability.

Allowed conceptual surface:

```text
read_target()
mark_ready()
convert_to_draft()
verify_state()
```

Forbidden surface:

```text
run(args)
shell(command)
request(method, arbitrary_url)
merge_pr()
close_pr()
write_file()
update_branch()
mutate_workflow()
mutate_secret()
mutate_repository_settings()
```

The adapter must freeze:

```text
provider = GITHUB
repository = dedicated calibration repository
resource_type = PULL_REQUEST
resource_id = exact calibration PR
operation = MARK_READY_FOR_REVIEW
rollback_operation = CONVERT_TO_DRAFT
```

Any mismatch must terminate before dispatch.

## 8. Required proof matrix

PEB-3R-B must produce replayable evidence for both positive scope and negative reachability.

### 8.1 Credential evidence

Must prove from provider-issued metadata or equivalent authoritative evidence:

```text
installation/application identity = exact
repository selection = dedicated calibration repository only
issued token repository set = exact expected repository
issued token permission set = exact minimum set
credential validity window = bounded
production repository write authority = absent
PIE repository write authority = absent for the calibration credential
```

### 8.2 Adapter evidence

Must prove:

```text
exact repository binding = enforced
exact PR binding = enforced
exact head binding = enforced
allowed operation = mark ready only
allowed rollback = convert to draft only
arbitrary command surface = absent
arbitrary URL/API surface = absent
```

### 8.3 Negative capability proof

The boundary must fail closed for attempts to:

```text
mutate PIE repository
mutate another repository
mutate a different PR in the calibration repository
merge the calibration PR
close the calibration PR
write repository files
update branches
change workflows
change secrets
change repository settings
```

Negative proof should prefer provider rejection for credential-boundary cases and local pre-dispatch rejection for adapter-boundary cases. A successful destructive probe is not required merely to demonstrate denial.

## 9. Existing PR #61 disposition

PR #61 is no longer an acceptable **formal** PEB-3 effect target because it resides in the authoritative PIE repository, while GitHub's native write credential scoping stops at repository granularity.

It remains useful only as historical evidence of the pre-dispatch blocker:

```text
PR #61 = KEEP OPEN / DRAFT / UNMERGED
FORMAL PEB-3 DISPATCH AGAINST PR #61 = RETIRED
```

This audit does not mutate or close PR #61.

## 10. Stage decision

```text
PEB-3R-A
= PASS

GITHUB_SINGLE_PR_CREDENTIAL_SCOPE
= NOT AVAILABLE IN DOCUMENTED NATIVE AUTHORIZATION MODEL

MINIMUM_NATIVE_WRITE_ISOLATION_BOUNDARY
= REPOSITORY

PEB-3R_DESIGN
= DEDICATED_NON_PRODUCTION_REPOSITORY
  + SELECTED-REPOSITORY GITHUB APP INSTALLATION
  + DOWNSCOPED SHORT-LIVED INSTALLATION TOKEN
  + EXACT-PR GOVERNED ADAPTER

CURRENT_PEB-3
= STILL BLOCKED
```

## 11. Next boundary

The next stage is:

```text
PEB-3R-B
Dedicated Non-Production Repository
& GitHub App Credential Boundary Establishment
```

PEB-3R-B requires real external resource/credential creation. It must establish the dedicated calibration repository and a GitHub App/installation credential boundary before PEB-3E can perform any governed state mutation.

Until that boundary exists:

```text
production_execution_authorized = false
formal_nonproduction_dispatch = blocked
automation_authorized = false
pilot_authorized = false
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 / existing R4 authority = UNCHANGED
```
