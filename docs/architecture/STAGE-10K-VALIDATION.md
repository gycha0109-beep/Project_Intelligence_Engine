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
formatting/key-order packet byte mutation  -> fail closed / no registry mutation
```

The packet hash is canonical semantic JSON, and the on-disk packet has an independent canonical byte contract: UTF-8, recursively sorted object keys, two-space indentation, and one terminal newline. Whitespace/key-order-only reserialization therefore fails before review authority creation. Changed governed meaning is separately protected by `packet_sha256` and authoritative source reconstruction, including semantic rehash forgery attempts.

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

## 6. Docs-inclusive and byte-hardening final evidence

The initial Stage 10K implementation completed its docs-inclusive gate on PR #28:

```text
PR #28 final head: 7549aa293bdf2cdd727d405c90c322387a249a90
CI #1010 / Run 32211362162
Python 3.11: SUCCESS
Python 3.13: SUCCESS
Python 3.14: SUCCESS
merge commit into stacked parent: 8bd401209f6837fb9ecddde6772ff79f3c8a80fc
post-merge CI #1012 / Run 32211480125: SUCCESS on 3.11 / 3.13 / 3.14
```

Final review identified one remaining distinction required by the Stage 10K attack contract: canonical semantic hashing did not by itself reject formatting/key-order-only packet byte reserialization. PR #29 added an independent canonical on-disk byte contract without changing `packet_sha256` semantics or any review authority.

```text
PR #29 final hardening head: 9d20dab0429d0d4542c4465e70fa990287dcb7e5
CI #1015 / Run 32211722146
Python 3.11: SUCCESS
Python 3.13: SUCCESS
Python 3.14: SUCCESS
merge commit into stacked parent: bbccd692feb3f7e3dea3293d3cdb3ab3be9bbdd3
post-merge CI #1017 / Run 32211832639
Python 3.11: SUCCESS
Python 3.13: SUCCESS
Python 3.14: SUCCESS
```

Therefore the final Stage 10K code authority before docs-only closeout is:

```text
stacked parent: agent/stage-10d-operating-observation-threshold-policy
exact code HEAD: bbccd692feb3f7e3dea3293d3cdb3ab3be9bbdd3
CI #1017 / Run 32211832639: SUCCESS
```

The docs-only closeout commit necessarily has a later SHA than the code authority it documents. Its exact CI is external GitHub metadata and must also be reported at Stage closeout. No temporary diagnostic or self-patch workflow may remain in the final diff.

## 7. Safety interpretation

A green Stage 10K gate means:

```text
review packet construction = validated
assessment/Trust/GitHub replay binding = validated
stale packet rejection = validated
literal packet-byte binding = validated
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
