# PIE Stage 10K — Validation

## 1. Validation scope

Stage 10K validation covers the complete prospective human-review handoff boundary:

- deterministic governed review packet construction,
- Stage 10I assessment identity/source replay,
- Stage 10A Trust report/evidence binding,
- Stage 10J GitHub candidate binding,
- live GitHub repository/PR/base/head/changed-files replay,
- packet schema and semantic hash verification,
- semantic rehash forgery rejection through authoritative reconstruction,
- stale packet rejection,
- explicit `REVIEWED` / `AUDITED` submission only,
- packet identity/hash binding into Stage 10B-compatible HUMAN_DECISION events,
- duplicate packet submission rejection,
- no `WORKFLOW_ACCEPTED` escalation,
- no automatic review/Outcome/pilot/automation authority,
- archive/path/symlink hardening,
- Stage 10I/10J/Trust full regression,
- package schema asset synchronization,
- example profile/Finding validation,
- wheel build.

## 2. Required attack cases

The Stage 10K suite exercises the required attack/regression classes:

```text
packet SHA mutation                         -> fail closed
semantic packet content mutation           -> fail closed
assessment_id substitution                 -> STALE_REVIEW_PACKET / fail closed
source_revision substitution               -> fail closed
Trust report substitution                  -> STALE_REVIEW_PACKET / fail closed
changed_files mutation                     -> STALE_REVIEW_PACKET / fail closed
PR HEAD drift                              -> STALE_REVIEW_PACKET / no registry mutation
different-project packet reuse             -> fail closed / no registry mutation
stale packet review submission             -> fail closed
exact packet duplicate submission          -> fail closed
packetless REVIEWED mutation attempt       -> fail closed
WORKFLOW_ACCEPTED escalation               -> rejected
AUDITED authority misuse                   -> no Independent Audit Outcome authority
semantic rehash forgery                    -> source replay mismatch / fail closed
symlink/path traversal                     -> fail closed
invalid/partial packet                     -> fail closed
Stage 10I source replay mismatch           -> fail closed / no registry mutation
packet preparation                         -> no registry mutation
reserved packet reason-code spoofing       -> fail closed
```

The packet hash is canonical semantic JSON. The deterministic writer fixes the normal on-disk representation; validation treats whitespace/key-order-only reserialization as the same semantic packet rather than as a new evidence snapshot. Changed governed meaning is protected both by `packet_sha256` and by source reconstruction.

## 3. Failure history

Earlier Stage 10K heads were not treated as PASS:

```text
ab0af9e3605c549c013dd4aa5ad8ce16fca66cb4
CI #992 / Run 32208175851
FAILED

6efb049b06dfc2f5bf101f69d7911f946207223d
CI #994 / Run 32208237569
FAILED
```

Because the connected Actions interface initially did not expose the traceback reliably, a temporary diagnostic workflow captured unittest logs as artifacts.

Diagnostic head:

```text
3103683fe5df905e4aad158ba588da8b775c5409
CI #996 / Run 32210311883
FAILED
Python 3.11 diagnostic: 470 tests, 468 pass, 2 errors
```

The two errors were hardening-test exception-type expectations. Both underlying operations had already failed closed.

After correcting those expectations and adding further hardening, head `8bab7b0d791b7d327cdfa4eeb633ac5c4bd9c73d` produced:

```text
CI #998 / Run 32210613781
Python 3.11: SUCCESS
Python 3.14: SUCCESS
Python 3.13: FAILED
```

The Python 3.13 diagnostic artifact showed one remaining test-fixture error:

```text
GovernedProspectiveReviewHardeningTests.test_different_project_packet_reuse_fails_before_registry_mutation
FileNotFoundError: .../other-project/campaign
```

The cross-project fixture was corrected to create the distinct project root explicitly.

## 4. Diagnostic green run

Corrected hardening head:

```text
37bc430dd929105de195881db7e15b56b1b4ad6e
CI #1000
Run ID: 32210936964
Python 3.11: SUCCESS
Python 3.13: SUCCESS
Python 3.14: SUCCESS
```

Every diagnostic matrix job also passed profile validation, Finding validation, and wheel build.

The diagnostic log-upload steps were then removed.

## 5. Canonical source-validation CI

Canonical workflow was restored to its original blob:

```text
.github/workflows/ci.yml
blob: f72c5ae53134fe3f1d3c9c098064a37d35915b79
```

Validated implementation source head:

```text
e0f162a510700bf66fc5c6159b410ea12f275c7b
CI #1002
Run ID: 32211117393
Python 3.11: SUCCESS
Python 3.13: SUCCESS
Python 3.14: SUCCESS
```

Each matrix job passed the canonical pipeline:

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

## 6. Docs-inclusive final gate

The source-validation result above proves the implementation head before Stage 10K closeout documentation.

The final PR gate is stricter:

1. all required Stage 10K documents and architecture index update are present,
2. temporary diagnostics are absent from the diff,
3. the exact docs-inclusive PR HEAD passes the same canonical Python 3.11/3.13/3.14 matrix,
4. PR #28 remains OPEN and MERGEABLE with Stage 10K-only scope,
5. no governance/safety authority expansion is present.

The exact docs-inclusive commit SHA and Actions run are authoritative in GitHub PR/CI metadata because a file cannot contain the SHA of the commit that contains that same file without changing the commit. Stage closeout reporting must cite that final external metadata explicitly.

## 7. Safety interpretation

A green Stage 10K gate means:

```text
review packet construction = validated
assessment/Trust/GitHub replay binding = validated
stale packet rejection = validated
explicit human decision persistence binding = validated
```

It does not mean:

```text
REVIEWED = performed on a real R0 case
AUDITED = performed on a real R0 case
Independent Audit Outcome = established
SAFE Outcome = established
pilot = eligible or authorized
automation = authorized
real runtime evidence campaign = populated
```

No synthetic/unit-test/CI result is promoted into real prospective runtime evidence.
