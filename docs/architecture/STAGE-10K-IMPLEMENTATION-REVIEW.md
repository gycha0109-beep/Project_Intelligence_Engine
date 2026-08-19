# PIE Stage 10K — Implementation Review

## 1. Review result

Stage 10K implements a governed evidence handoff between the existing Stage 10I prospective assessment and the existing Stage 10B human decision authority.

The implementation adds no new safety judgment level and does not relax any Trust, pilot, automation, eligibility, or Independent Audit authority boundary.

Canonical implementation source-validation head before documentation:

```text
e0f162a510700bf66fc5c6159b410ea12f275c7b
```

Canonical CI at that head:

```text
CI #1002
Run ID: 32211117393
Python 3.11: SUCCESS
Python 3.13: SUCCESS
Python 3.14: SUCCESS
```

A later docs-inclusive exact-head CI remains the final PR gate; a document cannot self-identify the SHA of the commit that contains itself, so the authoritative docs-inclusive HEAD/run is recorded in PR/Actions metadata and Stage closeout reporting.

## 2. Implemented surfaces

Added:

- `schemas/prospective-review-packet.schema.json`
- packaged schema asset copy
- `review_system.trust_prospective_review`
- `review_system.trust_prospective_review_cli`
- focused packet, CLI, and hardening tests

Modified:

- Stage 10I prospective evidence public surface
- Stage 10I prospective CLI delegation
- Stage 10I prospective review mutation contract
- existing Stage 10I tests to require governed packet binding

No Stage 10F Trust Root/issuer authority or production policy surface was changed.

## 3. Packet construction review

`prepare_review_packet()` composes only existing authoritative concepts:

- Stage 10I assessment identity and source manifest,
- Stage 10A Trust report identity/evidence projection,
- Stage 10J GitHub capture candidate and live PR identity,
- existing risk band/hard-gate/review-requirement values.

It does not create a parallel assessment, PR, review, or Outcome ontology.

Preparation is read-only with respect to the Stage 10I comparison registry. Focused tests compare registry bytes before/after preparation.

## 4. Deterministic identity review

The packet contains two related hashes:

- `evidence_snapshot_sha256`: canonical hash over the governed snapshot projection excluding generation/packet identity fields.
- `packet_sha256`: canonical JSON hash over the complete finalized packet excluding only `packet_sha256` itself.

`packet_id` derives deterministically from packet contract, project, assessment, GitHub candidate/head, and evidence snapshot identity.

Changed packet meaning without a valid rehash is rejected by packet verification. Recomputing a syntactically valid packet hash after changing governed meaning is insufficient because `verify_review_packet_sources()` rebuilds the expected packet from the current authoritative Stage 10I/10J sources at the original `generated_at` and compares the governed projection.

The hash contract remains canonical semantic JSON, while the file contract adds an independent canonical byte representation: UTF-8, recursively sorted object keys, two-space indentation, and one terminal newline. `load_review_packet()` and the archived-packet mutation guard both reject any non-canonical byte representation before review authority can be created. This separates literal packet-byte tamper protection from semantic-rehash protection.

## 5. Source and drift review

Verification replays:

1. Stage 10I workspace/assessment/source manifest,
2. Stage 10A Trust report and exact source references,
3. Stage 10I reconciliation state,
4. Stage 10J capture candidate,
5. current live GitHub PR repository/PR/base/head/changed-files.

The reconstructed governed packet must match the submitted packet. Failures are reported as `STALE_REVIEW_PACKET` where the packet no longer describes the current authoritative snapshot.

This closes stale packet reuse for assessment, Trust report, source revision, evidence projection, project identity, PR head/base, and changed-files drift.

## 6. Human decision persistence review

The prospective review mutation now accepts only `REVIEWED` or `AUDITED` and requires a governed packet ID/hash.

The governed submit path archives the exact packet and GitHub candidate, then delegates human decision persistence to the existing Stage 10B-compatible `record_decision()` path rather than reimplementing Stage 10B event identity/hash-chain/projection semantics.

Packet identity/hash are preserved in reserved `reason_codes`, which are themselves inside the Stage 10B `HUMAN_DECISION` event hash.

Duplicate exact packet submissions are rejected. Reserved packet provenance reason codes cannot be supplied by the caller.

The prior raw `record-prospective-review` CLI mutation route was converted into an alias for packet-required governed submission. The low-level mutation function is no longer re-exported from the Stage 10I public prospective evidence surface.

## 7. AUDITED / Independent Audit review

Stage 10K does not reinterpret `AUDITED`.

Stage 10B defines:

```text
WORKFLOW_ACCEPTED = workflow progress only
REVIEWED          = actual human review
AUDITED           = deeper/separate human review
```

Stage 10F separately defines authoritative `INDEPENDENT_AUDIT` Outcome provenance through a Trust Root, Issuer Grant, audit artifact, source replay, and actor constraints.

Therefore:

```text
Stage 10K AUDITED HUMAN_DECISION
!= Stage 10F INDEPENDENT_AUDIT Outcome
```

No Stage 10K command creates a Stage 10F audit artifact or Outcome.

## 8. Attack/hardening coverage

Focused hardening covers:

- packet hash mutation,
- semantic packet mutation without rehash,
- semantic rehash forgery,
- `assessment_id` substitution,
- `source_revision` substitution,
- Trust report substitution,
- changed-files mutation,
- evidence snapshot mutation,
- live PR head drift,
- different-project packet reuse,
- Stage 10I source replay mismatch,
- stale submission with registry immutability,
- packetless review mutation attempt,
- duplicate exact packet submission,
- reserved packet provenance spoofing,
- `WORKFLOW_ACCEPTED` escalation attempt,
- invalid/partial packet,
- symlink/path traversal,
- packet preparation without registry mutation,
- AUDITED decision remaining distinct from Independent Audit Outcome authority.

## 9. Validation defects found and corrected

### Finding A — specialized exception expectation was incorrect

The first diagnostic full-suite run reached two hardening cases where the implementation correctly failed closed using the common prospective evidence exception type, while the newly added tests expected the narrower Stage 10K verification subclass.

Affected attacks:

- symlinked packet input,
- caller spoofing of reserved packet binding reason codes.

No unsafe operation succeeded. The tests were corrected to assert the actual common fail-closed boundary rather than weakening or wrapping the underlying protection solely to satisfy the test.

### Finding B — cross-project attack fixture had an implicit parent-directory assumption

Python 3.13 exposed a new test fixture bug:

```text
FileNotFoundError: .../other-project/campaign
```

The helper intentionally creates only the campaign workspace below an already-existing project root. The hardening test now explicitly creates `other-project/` before initializing its campaign.

This was a test construction defect, not a product authority bypass. The corrected test then validates that a packet from one project cannot be reused to mutate another project's registry.

### Diagnostic handling

A temporary CI modification captured unittest output as per-version artifacts because the connected Actions surface did not initially expose the needed traceback.

After diagnosis:

- all three Python versions passed diagnostic CI #1000 / Run `32210936964`,
- the temporary log-upload steps were removed,
- `.github/workflows/ci.yml` was restored to original blob `f72c5ae53134fe3f1d3c9c098064a37d35915b79`,
- canonical CI #1002 / Run `32211117393` passed all matrix jobs.

The diagnostic workflow is not part of the Stage 10K final diff.

## 10. Authority interpretation

Implementation/CI PASS means only that the governed packet and explicit review-binding mechanism satisfy the tested code contract.

It does not mean that any real prospective case has been human-reviewed, audited, proven safe, made pilot-eligible, or authorized for automation.

No Stage 10K implementation action is itself a human governance decision.
