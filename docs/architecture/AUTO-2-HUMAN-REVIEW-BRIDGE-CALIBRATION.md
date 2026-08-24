# AUTO-2 Human Review Bridge — Calibration Closeout

## Result

```text
AUTO-2 HUMAN REVIEW BRIDGE CALIBRATION
= PASS
```

The proof used only the dedicated synthetic calibration repository:

```text
pie-peb3-lab/pie-peb3-calibration
```

No production repository, production deployment, business data, secret, human-review decision, outcome, merge authority, pilot authority, or production-effect authority participated in the proof.

## Exact authority and target

PIE authority revision:

```text
5043c7caea2893d86183d8f76ae7c9b1c7aa0101
```

Trust request:

```text
evidence/trust/requests/auto2-synthetic-calibration-pr8-20260824.json
SHA-256 = f59d36876dc3ef1ddb609584ea9b18998d45bdc39f162edb309e731350539dd3
```

Synthetic target PR #8 remained open, Draft, and unmerged for both observations:

```text
repository = pie-peb3-lab/pie-peb3-calibration
base       = 5673310fe66d74da5d31f165ffc4314e0d845740
head       = bee68c0635fb5001d42168ddac23de04b1e526df
changed    = .pie-auto2/synthetic-target.md
```

Synthetic replay harness PR #9 also remained open, Draft, and unmerged:

```text
head = 0c26c0920983c539b602216552f98a2e9a8fdfa3
```

## Replay A

```text
run_id       = 32689759680
artifact_id  = 9506850092
artifact SHA = sha256:7ea69187f43390402167e8afb49fa98400e27c56d78e83e6d633276957db2cbc

assessment_id = assessment-14f66912abbff347151c07ebdbc2be94
execution_id  = pie-pr-auto-b4266d81d47c3d95a9f0a07670b24b72

raw packet_id = prospective-review-packet-98ea4b35d723dfe95e24b16230e812ff
raw packet snapshot = 5d3dce5079081d83c8764734205e12a3f3e6cd35458c517dbc17ba0a49883620
raw observation manifest = 66ce561f335b98e7a26143a67d431fd54771b4c18854986491716222aeea8884

semantic_packet_sha256 = c87ed7aeafb9bbafda7b82ded448421171a90bb78bf24721236f2ec62934ebe3
deterministic_result_sha256 = ad6a05956ca29ad84924d5136a86734017c0802d104a440ad036e99e5a1b690b
```

## Replay B

```text
run_id       = 32689866835
artifact_id  = 9506886022
artifact SHA = sha256:dbc0c217420e1bb2dd75be9a8208f3ce0966975512021ebd373ed72f1d58ffcf

assessment_id = assessment-14f66912abbff347151c07ebdbc2be94
execution_id  = pie-pr-auto-b4266d81d47c3d95a9f0a07670b24b72

raw packet_id = prospective-review-packet-0980dd54252837011b5ffffea5320abc
raw packet snapshot = f00f0193a917b60efe0305c4993460ba8efb6e8f7be0edf65a21bf06f5e89336
raw observation manifest = 9c5d52ca56eb7b17ab2ee85cfcf6b0903d602c26a2908decbff318e4c82eab31

semantic_packet_sha256 = c87ed7aeafb9bbafda7b82ded448421171a90bb78bf24721236f2ec62934ebe3
deterministic_result_sha256 = ad6a05956ca29ad84924d5136a86734017c0802d104a440ad036e99e5a1b690b
```

## What the proof establishes

The two independent GitHub Actions observations deliberately collected the same exact target and authority at different times. Raw provider evidence changed, and that difference propagated into raw Stage 10K packet provenance.

The following therefore **differed as expected**:

```text
raw packet_id
raw packet evidence snapshot
raw observation manifest
```

The following remained **exactly equal**:

```text
assessment_id
execution_id
semantic_packet_sha256
deterministic_result_sha256
```

This proves the intended boundary:

```text
RAW PROVIDER / PACKET PROVENANCE
!=
AUTO-2 SEMANTIC REPLAY IDENTITY
```

Raw provenance is not discarded or rewritten. It remains available for Stage 10K source replay, packet verification, archive, and human-review binding. AUTO-2 only adds a separate deterministic semantic identity for repeated observations of the same governed inputs.

## Runtime defects discovered during calibration

The calibration found and resolved two real defects before closeout:

1. prospective analysis originally wrote its generated graph into the target worktree, causing governed materialization to reject its own dirty checkout; the graph now stays under per-execution evidence output;
2. the initial AUTO-2 deterministic hash included raw Stage 10K packet identity, which legitimately changes when provider transport metadata changes; AUTO-2 now derives a separate semantic packet projection without changing Stage 10K packet semantics.

## Authority ceiling

Both successful replays terminated at:

```text
READY_FOR_HUMAN_REVIEW
risk_band = R1
```

and preserved:

```text
human_review_recorded        = false
outcome_recorded             = false
automation_authorized        = false
pilot_authorized             = false
merge_authorized             = false
deploy_authorized            = false
production_effect_authorized = false
```

Therefore this calibration authorizes **evidence preparation only**. It does not authorize a human decision, outcome, automatic approval, merge, deployment, pilot, or production effect.

## Closeout

```text
AUTO-2 implementation           = LANDED
AUTO-2 exact target binding     = PASS
AUTO-2 Trust-source binding     = PASS
AUTO-2 clean-worktree invariant = PASS
AUTO-2 semantic same-head replay = PASS
AUTO-2 authority ceiling        = PRESERVED
```
