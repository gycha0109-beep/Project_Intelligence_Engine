# PIE Stage 10J — Validation

## 1. Validation scope

Stage 10J validation covers:

- prospective candidate generation from `analyze-pr`,
- schema and semantic rehash verification,
- degraded/exact-head blocker projection,
- atomic candidate write/load and symlink rejection,
- live GitHub head/base/changed-file drift rejection,
- local repository/head/clean-worktree enforcement,
- Project Profile binding,
- Trust request identity binding,
- Stage 10A Trust report generation/replay,
- Stage 10I intake handoff,
- no automatic review/Outcome/pilot/automation authority,
- existing PR identity manifest compatibility,
- delegated and standalone CLI behavior,
- full repository regression suite.

## 2. Failure discovery and correction

The original PR head failed full unittest discovery on Python 3.11/3.13 and canceled 3.14.

Exact diagnostic evidence identified:

1. valid raw GitHub SHA rejected after Stage 10A canonicalized it to `git:<sha>`,
2. new prospective candidate written after the PR identity manifest snapshot.

Both were corrected without changing Trust thresholds, Stage 10I campaign thresholds, review authority, or fail-closed drift checks.

## 3. Focused diagnostic evidence

A temporary Actions diagnostic captured the exact failing traceback and later the complete unittest output.

After both fixes, diagnostic run:

```text
Stage 10J Diagnostic run #5
Run ID: 32204498107
Python: 3.13
full unittest discovery: SUCCESS
Tests: 456
Failures: 0
Errors: 0
```

The temporary diagnostic workflow was removed after diagnosis.

## 4. Canonical source-validation CI

Canonical CI at source-fix head `3e2ebb5ddcad641299bdaf310b59d326225a6958`:

```text
CI #968
Run ID: 32204498101
Python 3.11: SUCCESS
Python 3.13: SUCCESS
Python 3.14: SUCCESS
```

Each matrix job passed:

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

## 5. Final-head requirement

The source-validation run above proves the implementation fixes. The final PR gate additionally requires the docs-inclusive exact PR head to pass the same canonical 3.11/3.13/3.14 matrix.

No Stage 10J PASS determination should be made from an older green head if later commits change the PR head.

## 6. Safety interpretation

A green Stage 10J validation means:

```text
prospective capture implementation = validated
exact-head materialization checks = validated
Stage 10A -> Stage 10I handoff = validated
```

It does not mean:

```text
human review = performed
independent audit = performed
Outcome = established
pilot = authorized
automation = authorized
R0 evidence thresholds = satisfied
```

Stage 10J remains a report-only governed capture boundary.
