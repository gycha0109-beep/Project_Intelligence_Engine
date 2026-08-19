# PIE Stage 10J — GitHub Prospective Capture Hook

## 1. Purpose

Stage 10J connects the existing `pie analyze-pr` application path to the Stage 10I prospective evidence intake boundary without turning ordinary PR analysis into an automatic Trust assessment, human review, Outcome, pilot, or automation decision.

Fixed boundary:

```text
GitHub PR
  -> pie analyze-pr
  -> prospective capture candidate
  -> explicit operator completion of Trust request
  -> explicit materialize-github-prospective-capture
  -> Stage 10A Trust report
  -> Stage 10I prospective case intake
```

The candidate is evidence scaffolding only.

```text
mode=REPORT_ONLY
automation_authorized=false
pilot_authorized=false
human_review_recorded=false
outcome_recorded=false
```

## 2. Analyze-PR integration

Every successful `analyze-pr` run writes a `prospective-capture-<identity>.json` candidate beside the existing PR analysis artifacts.

The candidate binds only evidence already known at analysis time:

- project identity and Project Profile hash,
- GitHub repository identity,
- PR number,
- exact base/head OIDs where available,
- changed-file set,
- GitHub source evidence hash,
- local repository/head/working-tree verification state.

It does not invent:

- Trust task class,
- required/completed scenarios,
- rollback evidence,
- replay evidence,
- readiness policy,
- human review,
- Outcome authority.

Missing operator inputs remain explicit blockers.

## 3. Exact-head fail-closed contract

Materialization requires the candidate to have been produced from an exact, clean, repository-matched PR state.

Before Stage 10A or Stage 10I is called, Stage 10J replays and verifies:

```text
candidate repository
candidate PR number
candidate head OID
candidate base OID
candidate changed-file set
live GitHub repository / PR state
local repository identity
local exact HEAD
clean local worktree
Project Profile identity/hash
Trust request task identity
Trust request canonical source revision
Trust request changed-file set
repository_match=true
head_match=true
```

Any drift fails closed and requires a fresh `pie analyze-pr` run or corrected operator input.

## 4. Source revision boundary

GitHub candidates preserve the exact raw 40-hex commit OID.

Stage 10A canonicalizes Git source revisions as:

```text
git:<40-hex-sha>
```

Stage 10J therefore compares Trust request/report identity against the canonicalized candidate head at the Trust boundary while continuing to require the raw exact GitHub OID at the GitHub/local verification boundary.

No shortened or symbolic revision is accepted for prospective materialization.

## 5. Identity manifest integration

The prospective capture candidate is a PR analysis artifact and is written before the Stage 3 identity manifest snapshot.

Therefore `identity.json` covers the candidate along with the existing analysis artifacts and `validate_identity_manifest()` remains complete. This adds the new artifact without weakening existing source/hash contracts.

## 6. Materialization

`materialize-github-prospective-capture` is an explicit command. It is not invoked automatically by `analyze-pr`.

If no Trust report exists, materialization generates the Stage 10A report from the exact request/profile/evidence sources. If one already exists, Stage 10J requires exact Stage 10A source replay before reuse.

Only after those checks does it call the existing Stage 10I `intake_prospective_case` path.

Stage 10I remains responsible for the prospective R0 evidence campaign contract and its own risk-band/source-replay enforcement.

## 7. CLI

Available through the prospective Trust CLI and delegated `pie-trust` surface:

```text
verify-github-prospective-capture
materialize-github-prospective-capture
```

`pie analyze-pr` only emits the candidate. Materialization remains a separate explicit action.

## 8. Authority boundary

The following are intentionally not inferred from Stage 10J:

```text
candidate generated != REVIEWED
candidate generated != AUDITED
candidate generated != Outcome
materialized case != human approval
CI success != safety ground truth
implementation PASS != pilot authorization
implementation PASS != automation authorization
```

Stage 10J is a governed capture/handoff boundary only.

## 9. Scope boundary

Stage 10J remains project-local PIE functionality. It does not create cross-project storage, Factory Knowledge, blueprint governance, Software Factory orchestration, estimation, client management, or any Factory Intelligence implementation.
