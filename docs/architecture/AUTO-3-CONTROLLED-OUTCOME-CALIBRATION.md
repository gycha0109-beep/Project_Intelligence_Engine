# AUTO-3 Controlled Outcome — Calibration Closeout

## Result

```text
AUTO-3 CONTROLLED OUTCOME CALIBRATION
= PASS
```

The proof used only the dedicated synthetic calibration repository:

```text
pie-peb3-lab/pie-peb3-calibration
```

No production repository, production deployment, business data, real R0 review evidence, pilot-eligibility evidence, automatic Outcome inference, merge authority, deploy authority, or production-effect authority participated.

## Exact PIE authority

The calibration installed and executed the exact merged AUTO-3B PIE authority revision:

```text
repository = gycha0109-beep/Project_Intelligence_Engine
revision   = 6fc3be0d2ed29cf3a51929fc4f6f42bcb157cb65
```

That authority already contains:

```text
AUTO-3A = explicit human Outcome declaration
AUTO-3B = declaration-bound Outcome transport + source reconciliation
```

AUTO-3C does not add a new Outcome engine or broaden authority. It is the controlled runtime calibration of those landed contracts.

## Calibration target

Synthetic calibration PR:

```text
repository = pie-peb3-lab/pie-peb3-calibration
PR         = #10
state      = OPEN
Draft      = true
merged     = false
base       = 5673310fe66d74da5d31f165ffc4314e0d845740
head       = a14a497ad73eff13e7765390507bb3c30ff3fd2d
source     = git:a14a497ad73eff13e7765390507bb3c30ff3fd2d
```

The first runtime failed because the synthetic source projection used an invalid Stage10J discriminator:

```text
source = synthetic-auto3-calibration
```

The existing GitHub prospective contract requires:

```text
source = github-cli
```

The fixture was corrected without changing the synthetic evidence semantics. Synthetic identity remains explicit through the calibration repository, synthetic actor, labels, warning, and final calibration flags.

Correction commit:

```text
a14a497ad73eff13e7765390507bb3c30ff3fd2d
fix(auto-3c): use accepted GitHub source discriminator
```

## Successful runtime

```text
workflow    = AUTO-3 Controlled Outcome Calibration
run_id      = 32693408313
run_number  = 2
conclusion  = SUCCESS
artifact_id = 9508004231
artifact    = auto3-controlled-outcome-32693408313
artifact SHA-256 = 8e132883a95b75fd4b2f27954f2fb085215fdffbfd44716b0509f72e45877d92
```

The downloaded artifact ZIP was independently hashed after retrieval and matched the GitHub artifact digest exactly.

Machine-readable closeout evidence is frozen at:

```text
evidence/trust/auto3-controlled-outcome-calibration-20260824.json
```

## Controlled evaluation

The synthetic evaluation completed with:

```text
evaluation_id = evaluation-878c96ea9517c9fb2974f6373823b472
report_sha256 = f3f98a79577d98d87a5417d4c0694c28b59cf8af8ec656f306bfdd6455f67140
gate          = PASS
repeatability = baseline true / challenger true / runs 2
holdout       = present
protected negative regressions = 0
```

The Trust report preserved that exact evaluation id and report semantic hash.

## Trust assessment

The calibration intentionally does not claim Trust readiness or an R0 result.

Actual assessment:

```text
assessment_id = assessment-1472ff872a1261c94cfa05eaee1890f0
trust_report  = trust-4c207d77faec061f8380e1dd039ed2c1
risk_band     = R2
readiness     = NOT_READY
```

The effective R2 band is produced by the synthetic changed source path and task-class underdeclaration in the fixture. This does not invalidate AUTO-3C because the calibration objective is declared Outcome transport and reconciliation integrity, not R0 pilot eligibility.

Therefore:

```text
AUTO-3C calibration PASS
!=
Trust READY
!=
R0 evidence
!=
pilot eligibility
```

## Governed synthetic REVIEWED event

The calibration generated a governed review packet and then submitted a deliberately synthetic human-decision fixture:

```text
actor                = synthetic:auto3-calibration-human
review_level         = REVIEWED
decision             = APPROVE
confirmed_risk_band  = R2
review_event_id      = event-da5dbf5f05a26f9303a084565fb7cd6a
review_event_sha256  = 6f31dd78fdb305af1214f907fa4a3d7495b352c87afcd590b38051b1aa72258f
review_packet_id     = prospective-review-packet-4ef0e675d8376c702e5790861b2630e8
review_packet_sha256 = e0df5e71d716ac4252a1ad18ee64cf6ffce7ddcb9447a2a0298f07592268e108
```

The event reason codes preserve the exact governed packet id/hash binding and include:

```text
SYNTHETIC_AUTO3_CALIBRATION_ONLY
```

This event exists solely to exercise the already-governed AUTO-3A/AUTO-3B path. It must not be counted as real Stage10K REVIEWED evidence, real R0 evidence, or pilot eligibility evidence.

## AUTO-3A declaration

The synthetic actor explicitly declared:

```text
authority_type = CONTROLLED_EVALUATION
verdict        = SAFE
```

Declaration identity:

```text
declaration_id     = outcome-declaration-b0c7a54eff2005b153c8e24a6ad19f47
declaration_sha256 = b0c7a54eff2005b153c8e24a6ad19f471298b8ad5b8e34f751600806ef0ea2d1
```

The declaration binds the exact:

```text
assessment
Trust report id/hash
REVIEWED event id/hash
review packet id/hash
evaluation id/hash
SAFE verdict
human actor
```

and preserves:

```text
human_outcome_declared      = true
automatic_outcome_inference = false
outcome_recorded            = false
```

at declaration time.

## AUTO-3B first transport

The first declared Outcome transport completed as:

```text
status                = DECLARED_OUTCOME_RECORDED_AND_RECONCILED
reconciliation_status = RECONCILED
idempotent             = false
Outcome event          = event-ab4e0e03f3348347922667fa49319e06
registry_sha256        = 1ca6025b9ff4eae064775c03fbd068eb632f56c6676669f57cebb954df1807aa
authority_key          = evaluation:f3f98a79577d98d87a5417d4c0694c28b59cf8af8ec656f306bfdd6455f67140:auto3-holdout
transport_sha256       = 669e30927297c75f26efb1a84aa96edbe47801021661cd7b2df8b8650aeeecf7
```

The authoritative campaign contained exactly one Outcome event after transport.

## Identical replay

The exact same AUTO-3A declaration was transported again against the already-mutated campaign.

Replay result:

```text
status                = DECLARED_OUTCOME_RECORDED_AND_RECONCILED
reconciliation_status = RECONCILED
idempotent             = true
Outcome event          = event-ab4e0e03f3348347922667fa49319e06
registry_sha256        = 1ca6025b9ff4eae064775c03fbd068eb632f56c6676669f57cebb954df1807aa
authority_key          = evaluation:f3f98a79577d98d87a5417d4c0694c28b59cf8af8ec656f306bfdd6455f67140:auto3-holdout
transport_sha256       = 56a6c8172488c77513cf8f5eea38173e448bc5b71c50dad381c81dd44e5a467f
```

The transport record hash itself differs because first execution and replay have different transport-state semantics, including the idempotent flag and base manifest identity.

The authoritative semantic identities remain equal:

```text
Outcome event identity = equal
final registry identity = equal
authority key           = equal
Outcome event count     = 1
```

Therefore the replay proves idempotent Outcome mutation rather than duplicate Outcome creation.

## Authority ceiling

The successful terminal artifact explicitly preserves:

```text
automatic_outcome_inference  = false
automation_authorized        = false
pilot_authorized             = false
merge_authorized             = false
deploy_authorized            = false
production_effect_authorized = false
eligible_for_pilot_evidence  = false
```

The synthetic REVIEWED event and SAFE declaration do not elevate runtime authority.

The calibration campaign remains:

```text
campaign_status = COLLECTING_EVIDENCE
```

## What AUTO-3C establishes

AUTO-3C proves this exact synthetic path on the merged PIE authority:

```text
PASS controlled evaluation
→ Trust assessment with exact evaluation binding
→ prospective intake
→ governed synthetic REVIEWED event
→ explicit AUTO-3A SAFE declaration
→ AUTO-3B declared Outcome transport
→ exact source RECONCILED
→ identical declaration replay
→ idempotent = true
```

It also establishes that the calibration fixture can exercise this path without converting synthetic evidence into real campaign authority.

## What AUTO-3C does not establish

AUTO-3C does not prove or authorize:

```text
real R0 evidence
Trust READY status
real human Stage10K review evidence
pilot eligibility
automatic SAFE inference
automatic approval
automatic merge
automatic deployment
production effects
```

Those remain separate evidence and authority boundaries.

## Closeout

```text
AUTO-3A explicit declaration binding       = LANDED
AUTO-3B declared Outcome transport         = LANDED
AUTO-3C controlled evaluation path         = PASS
AUTO-3C evaluation binding                 = PASS
AUTO-3C governed review/declaration binding = PASS
AUTO-3C source reconciliation              = PASS
AUTO-3C identical replay idempotency       = PASS
AUTO-3C synthetic evidence isolation       = PASS
AUTO-3C authority ceiling                  = PRESERVED
```

AUTO-3 controlled Outcome calibration is closed at the synthetic calibration boundary. Real evidence acquisition remains governed by the existing prospective campaign and is not satisfied by this closeout.
