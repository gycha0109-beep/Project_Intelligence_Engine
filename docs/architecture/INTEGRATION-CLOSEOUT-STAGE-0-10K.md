# PIE Integration Closeout — Stage 0 through Stage 10K

## 1. Purpose

This document records the final integration audit for promoting the accumulated PIE Stage 0–10K stacked development baseline to `main`.

This is not a new infrastructure Stage and does not expand PIE's product authority. It is a repository-baseline closeout.

## 2. Integration authority

Pre-closeout authority:

```text
main baseline:
c8578aa2c8096b3f0fa7652248c078702a94d023

validated stacked source branch:
agent/stage-10d-operating-observation-threshold-policy

stacked source exact HEAD after Stage 10K closeout:
600a8d30b26c25f15219314ae1c98c2213703497

integration branch:
integration/stage-0-10k-main-baseline

integration PR:
#31
```

The integration branch was created as an exact copy of `600a8d30b26c25f15219314ae1c98c2213703497` before this documentation-only closeout delta.

The final docs-inclusive integration HEAD and final CI run must be taken from GitHub PR/Actions metadata because a document cannot contain the SHA of the commit that contains itself without changing that SHA.

## 3. Main-to-integration scope audit

Initial PR #31 comparison against `main`:

```text
commits: 626
changed files: 229
additions: 45,969
deletions: 817
```

The changed-file inventory is constrained to the accumulated PIE implementation surfaces:

- root/architecture documentation,
- example Trust observation policy,
- `pyproject.toml` CLI entry points,
- root JSON Schemas and synchronized packaged schema assets,
- `review_system` application/GitHub/intelligence/Ledger/Defect/Evaluation/Policy/Reground/BuildMap/Trust modules,
- focused and regression tests.

No `.github/workflows` file is part of the main-to-integration diff. No temporary diagnostic workflow, self-patch workflow, test log, patch script, generated runtime evidence package, or deployment configuration survives in the integration diff.

## 4. Package and dependency audit

The product package remains:

```text
name = project-intelligence-engine
version = 0.3.0
requires-python = >=3.11
```

Runtime dependencies remain limited to:

```text
PyYAML>=6.0.3
jsonschema>=4.26.0
```

The accumulated stages add dedicated CLI entry points for the Ledger, Defect Registry, Evaluation Lab, Policy Registry, Reground, BuildMap export, and Trust subsystems without adding a new runtime dependency.

No version bump is performed by this integration closeout.

## 5. Data and migration audit

Stage 4/5 add a local SQLite Evidence Ledger projection with schema versions `001` and `002`.

The migration contract is additive and checksum-verified:

- `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`,
- migration checksum mismatch fails closed,
- existing applied migrations are not silently rewritten,
- no `DROP TABLE` migration is present.

Import/rebuild code can delete stale rows from the SQLite projection, but the Ledger is explicitly rebuildable and the source artifact directories / file-authoritative registries remain the authority. This is projection maintenance, not destructive mutation of the source evidence artifacts.

No destructive source-data migration is introduced by the integration closeout itself.

## 6. Governance and safety audit

The integration diff was searched for authority escalation.

No implementation path sets:

```text
pilot_authorized = True
automation_authorized = True
```

The Trust safety-review path explicitly constructs reports with:

```text
mode = REPORT_ONLY
automation_authorized = False
pilot_authorized = False
target_band = R0
```

Even a fully satisfied Stage 10E safety review reaches only:

```text
ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

with next step:

```text
REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION
```

It does not activate a pilot.

The following remain prohibited by this baseline:

- CI success becoming `REVIEWED` or `AUDITED`,
- PR merge becoming a safety Outcome,
- `WORKFLOW_ACCEPTED` becoming reviewed evidence,
- packet preparation creating human review authority,
- `AUDITED` HUMAN_DECISION becoming Stage 10F `INDEPENDENT_AUDIT` Outcome authority,
- threshold relaxation through semantic rehashing,
- synthetic/unit-test/retrospective evidence becoming real runtime campaign evidence,
- automatic GitHub approval/merge/comment/label/deployment from Trust results.

## 7. Stage 10K review boundary

The final prospective review path is:

```text
Stage 10J exact GitHub capture
-> Stage 10I prospective assessment
-> Stage 10K deterministic review packet
-> explicit human REVIEWED / AUDITED action
-> later authoritative Outcome
-> Stage 10C reconciliation
-> Stage 10D observation
-> Stage 10G / 10H replay
```

Review authority requires the exact assessment identity, exact packet identity/hash, canonical packet bytes, current Stage 10I source replay, current Stage 10J GitHub replay, explicit human decision, and explicit actor.

Packet formatting/key-order byte mutation and semantic rehash forgery are independently rejected.

## 8. PIE / BuildMap / Factory boundary

The accumulated baseline preserves the long-term authority boundary:

```text
PIE = project-local technical intelligence / evidence authority
BuildMap = separate product/strategic reasoning authority
Factory Intelligence = future cross-project generalized production knowledge authority
```

Stage 9 exports metadata-only BuildMap references. It does not make BuildMap a PIE runtime dependency.

Stage 10J/10K documentation explicitly excludes Factory Intelligence, cross-project databases, blueprint/client-overlay governance, ERP/SI orchestration, Factory ingestion, and BuildMap-specific runtime schema expansion.

No Factory Intelligence implementation is introduced by this integration.

## 9. Integration validation

Before the documentation closeout delta, the exact integration source HEAD was validated directly by PR #31 CI:

```text
source HEAD:
600a8d30b26c25f15219314ae1c98c2213703497

CI #1028
Run ID: 32216529751

Python 3.11: SUCCESS
Python 3.13: SUCCESS
Python 3.14: SUCCESS
```

Each matrix job completed:

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

Python 3.11 executed:

```text
Ran 474 tests
OK
```

The PR CI validates GitHub's synthetic merge ref between the integration head and the current `main`, so this is an integration check rather than only a branch-local check.

A docs-inclusive exact-head matrix must pass again after this closeout documentation is added.

## 10. Non-blocking observation

The current GitHub-hosted runner emits a deprecation warning because `actions/checkout@v4` and `actions/setup-python@v5` target the older Node action runtime and GitHub currently forces them onto Node 24.

The actions complete successfully and this does not affect the Stage 0–10K integration result. Updating CI action majors is a separate maintenance task and is intentionally not mixed into the main-baseline promotion.

## 11. Runtime evidence state

Integration success does not populate the real R0 evidence campaign.

Current direction after baseline promotion remains:

```text
real change
-> Stage 10J capture
-> Stage 10I assessment
-> Stage 10K explicit human review
-> later real Outcome
-> reconciliation / observation / replay
```

Synthetic tests and historical workflow activity must not be backfilled as real prospective evidence.

## 12. Merge and cleanup boundary

PR #31 may be marked Ready only after the final docs-inclusive exact-head matrix is green and the final diff is re-audited.

Merging PR #31 into `main` is a special governance action and requires explicit user approval. It must not be auto-merged by the normal stacked-branch rule.

After an approved main merge and post-merge CI success, obsolete stacked PRs/branches can be closed or cleaned up as historical development scaffolding. That cleanup must not delete the new `main` baseline or runtime evidence.
