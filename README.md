# Project Intelligence Engine v0.3.0

Project-aware technical intelligence and evidence-governance tooling built on the Universal Review System control plane.

The package version remains `0.3.0`. The current Stage 0–10K development baseline extends the original GitHub PR intake with deterministic identity, evidence projection, defect/evaluation/policy tracking, reground analysis, metadata-only BuildMap export, and a report-only Trust evidence pipeline.

## Current authority boundary

PIE is a **project-local technical intelligence / evidence authority**.

The current baseline is intentionally conservative:

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
```

CI success, PR merge, workflow acceptance, packet generation, or implementation completion do **not** become `REVIEWED`, `AUDITED`, a safety Outcome, pilot authorization, or automation authorization.

BuildMap remains a separate product/strategic reasoning authority. PIE exports metadata-only references for BuildMap but does not depend on the BuildMap runtime. Factory Intelligence and cross-project production knowledge are outside the current implementation.

## What PIE currently provides

### Change intelligence

- project/profile and Review Pack resolution
- protected-path snapshots and verification
- Project Graph indexing
- change-impact and parallel-change analysis
- rule-candidate discovery and explicit approval
- read-only GitHub PR collection and reproducible PR evidence

### Evidence and learning foundation

- deterministic Run and Artifact identities
- rebuildable SQLite Evidence Ledger projection
- project-level Defect Registry
- deterministic baseline/challenger Evaluation Lab
- versioned Policy Registry
- Reground freshness and impacted-recheck analysis
- metadata-only BuildMap reference export

### Trust and prospective evidence

- Stage 10A report-only R0–R4 Trust assessment
- explicit Stage 10B `WORKFLOW_ACCEPTED` / `REVIEWED` / `AUDITED` decision separation
- authoritative Outcome and reconciliation contracts
- R0 observation threshold reporting
- independent-audit authority verification
- report-only R0 pilot safety/eligibility evidence
- prospective R0 evidence campaign intake
- GitHub prospective capture candidate/materialization
- deterministic Stage 10K review packets bound to exact assessment, Trust, GitHub, and evidence snapshots

The prospective path is:

```text
real GitHub change
-> Stage 10J capture
-> Stage 10I assessment
-> Stage 10K deterministic review packet
-> explicit human REVIEWED / AUDITED
-> later authoritative Outcome
-> reconciliation / observation / replay
```

Synthetic tests and retrospective workflow history are not real prospective runtime evidence.

## Architecture and integration evidence

Detailed contracts, implementation reviews, validation records, and the Stage 0–10K integration closeout are under [`docs/architecture/`](docs/architecture/README.md).

Main integration audit:

- [`INTEGRATION-CLOSEOUT-STAGE-0-10K.md`](docs/architecture/INTEGRATION-CLOSEOUT-STAGE-0-10K.md)

Actual code and schemas remain authoritative when historical stage documents describe an earlier snapshot.

## Requirements

- Python 3.11 or newer
- Git
- GitHub CLI (`gh`) for `github-doctor`, `analyze-pr`, and live GitHub prospective replay
- authenticated GitHub CLI session (`gh auth login`)

PIE does not require a GitHub token in project configuration. GitHub collection reuses the credential managed by `gh` and executes argument vectors without a shell.

## Install

### From a wheel

```powershell
py -m pip install .\project_intelligence_engine-0.3.0-py3-none-any.whl
pie version
```

### From source

```powershell
cd D:\Tools\project-intelligence-engine-v0.3.0
py -m pip install .
pie version
```

The legacy `urs` command remains available as a compatibility alias.

## CLI surfaces

Core command:

```text
pie
urs
```

Dedicated subsystem entry points:

```text
pie-ledger
pie-defect
pie-eval
pie-policy
pie-reground
pie-buildmap
pie-trust
pie-trust-comparison
pie-trust-audit
pie-trust-observation
pie-trust-reconciliation
pie-trust-pilot-review
pie-trust-pilot-evidence
pie-trust-evidence-acquisition
pie-trust-prospective
```

These entry points expose existing deterministic/report-only contracts; their existence does not authorize a pilot or automation.

## First project setup

Example with the Bejewely preset:

```powershell
# GitHub CLI login, once per PC/account
gh auth login

# Move to the repository to analyze
cd D:\Ji_hwan\K_beauty

# Create PIE project files once
pie init-project --preset bejewely

# Verify GitHub CLI and repository binding
pie github-doctor

# Analyze one PR
pie analyze-pr https://github.com/gycha0109-beep/K_beauty/pull/71
```

The default PR analysis directory is:

```text
.pie/pr-71/
├─ github-source.json
├─ pull-request.diff
├─ impact.json
├─ identity.json
├─ prospective-capture-candidate.json
└─ REPORT.md
```

Candidate generation is read-only with respect to prospective review authority. Explicit materialization and explicit human review are separate operations.

Validate GitHub evidence with:

```powershell
pie validate-github-source .pie\pr-71\github-source.json
```

## Supported presets

```text
bejewely
buildmap
journey-connect
generic-webapp
```

`init-project` creates project-local review/intelligence configuration without overwriting existing files unless `--force` is explicitly supplied.

## GitHub safeguards

- repository mismatch blocks analysis by default
- local HEAD / PR exact-head mismatch blocks by default
- scoped dirty worktree changes block by default
- changed-file and discussion collection is paginated and source-hashed
- diff failure is explicit degraded evidence rather than silently complete evidence
- prospective materialization revalidates live repository, PR, head, base, changed files, local repository state, Project Profile identity, Trust request identity, and source replay
- GitHub capture/materialization does not create `REVIEWED`, `AUDITED`, Outcome, pilot, or automation authority
- PIE's GitHub intake does not perform automatic merge, approval, label, comment, or deployment actions

Explicit degraded-analysis overrides such as `--allow-head-mismatch` and `--allow-dirty-worktree` remain analysis-only overrides; they do not grant Trust authority.

## Evidence and Trust safeguards

- source revisions and identities are deterministic and exact where authority requires them
- schema/hash verification is supplemented by authoritative source replay for governed decisions
- path traversal and symlink inputs are rejected on authority-sensitive file surfaces
- writes use atomic-replace patterns where the contract requires preservation
- zero-denominator metrics remain undefined rather than appearing perfect
- R0 false negatives remain zero-tolerance in the observation policy contract
- `WORKFLOW_ACCEPTED` is not reviewed evidence
- Stage 10K packet preparation is not human review
- Stage 10K `AUDITED` is not Stage 10F `INDEPENDENT_AUDIT` Outcome authority
- pilot eligibility can only request a later explicit human authorization; `pilot_authorized` remains false

## Storage model

PIE remains primarily local and project-scoped.

- source artifacts and registries are file-authoritative
- the Evidence Ledger SQLite database is a rebuildable projection
- runtime prospective evidence workspaces are local/gitignored evidence unless explicitly managed elsewhere
- no central cross-project Trust/Factory database is introduced by the Stage 0–10K baseline

## Further documentation

Start with:

- [`docs/architecture/README.md`](docs/architecture/README.md)
- [`docs/architecture/STAGE-10K-GOVERNED-PROSPECTIVE-REVIEW-HANDOFF.md`](docs/architecture/STAGE-10K-GOVERNED-PROSPECTIVE-REVIEW-HANDOFF.md)
- [`docs/architecture/STAGE-10K-VALIDATION.md`](docs/architecture/STAGE-10K-VALIDATION.md)
- [`docs/architecture/INTEGRATION-CLOSEOUT-STAGE-0-10K.md`](docs/architecture/INTEGRATION-CLOSEOUT-STAGE-0-10K.md)

Historical GitHub intake documents remain available under `docs/` for the original v0.3.0 usage and implementation context.
