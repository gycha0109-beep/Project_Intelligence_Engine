# PIE Stage 10J — Implementation Review

## 1. Review result

Stage 10J implementation is structurally consistent with the existing Stage 10A/10I authority model after two integration regressions were identified and corrected during exact-head CI validation.

No threshold, review, Outcome, pilot, or automation boundary was relaxed to obtain PASS.

## 2. Implemented surfaces

Stage 10J adds:

- `github-prospective-capture-candidate.schema.json` and packaged schema copy,
- `review_system.github_prospective_capture`,
- `AnalyzePullRequestResult.prospective_candidate_path`,
- candidate emission from `analyze_pull_request`,
- `verify-github-prospective-capture`,
- `materialize-github-prospective-capture`,
- delegation through the existing Trust CLI,
- focused candidate/materialization/CLI tests.

## 3. Candidate safety review

Candidate generation is deterministic from known PR/project evidence plus generation time.

Semantic verification recomputes:

- candidate identity,
- local verification projection,
- blocker set,
- status/next-step projection,
- Trust request scaffold,
- evidence snapshot SHA,
- report SHA.

A candidate cannot be made materializable by merely deleting a blocker and rehashing it.

Candidate read/write paths reject symlink traversal and use atomic replacement for writes.

## 4. Materialization safety review

Materialization rechecks live GitHub and local authority instead of trusting stale candidate bytes.

Fail-closed cases include:

- live PR head movement,
- live PR base movement,
- changed-file drift,
- repository mismatch,
- local HEAD drift,
- dirty worktree,
- Project Profile drift,
- Trust request identity mismatch,
- Trust source replay mismatch.

Stage 10A report generation and Stage 10I intake occur only after those checks.

## 5. Regression 1 — source revision representation mismatch

Initial CI failed because GitHub candidates carry raw 40-hex OIDs while Stage 10A canonicalizes Trust request revisions to `git:<sha>`.

The materializer compared the canonical Trust request value directly to the raw candidate OID and rejected a valid exact revision.

Correction:

```text
raw GitHub/local boundary: <40-hex-sha>
Trust boundary:           git:<40-hex-sha>
```

The materializer now canonicalizes the already exact candidate head with the existing `normalize_source_revision()` contract before comparing Trust request or existing Trust report identity.

This preserves exact GitHub verification and existing Trust canonicalization simultaneously.

## 6. Regression 2 — identity manifest artifact ordering

After the source-revision fix, full regression exposed one remaining failure:

```text
unexpected artifact: prospective-capture-<id>.json
```

The candidate had been written after the Stage 3 identity manifest was generated, so the new analysis artifact was absent from the manifest.

Correction:

```text
write standard PR artifacts
-> write prospective capture candidate
-> snapshot identity manifest
```

The identity mechanism itself was not weakened or special-cased. The new artifact is now covered by the normal manifest contract.

## 7. Diagnostic workflow handling

Temporary GitHub Actions diagnostics were used only because the connected Actions job-log endpoint did not expose the failing traceback directly.

The diagnostics:

- isolated the failing Stage 10J success path,
- captured the exact traceback as an Actions artifact,
- captured the full 456-test unittest output,
- were removed before final validation.

The canonical `.github/workflows/ci.yml` was restored byte-for-byte to its original blob before source validation, and the temporary diagnostic workflow does not belong to the final Stage 10J diff.

## 8. Authority interpretation

Implementation PASS means only that the Stage 10J capture/materialization contract is implemented and regression-tested.

It does not create:

- `REVIEWED`,
- `AUDITED`,
- an authoritative Outcome,
- pilot eligibility,
- pilot authorization,
- automation authorization.

Those remain governed by the existing later-stage contracts and explicit human authority.
