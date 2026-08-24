# AUTO-3C — Controlled Outcome Calibration Closeout

## Result

```text
AUTO-3C CONTROLLED OUTCOME CALIBRATION
= PASS
```

The proof used only the dedicated synthetic calibration repository:

```text
pie-peb3-lab/pie-peb3-calibration
```

The calibration PR remained Draft and unmerged. No production repository, production deployment, real Stage10K human review, real R0 campaign evidence, pilot authorization, merge authority, deploy authority, or production-effect authority participated.

## Exact PIE authority

AUTO-3C installed and exercised exact PIE authority:

```text
6fc3be0d2ed29cf3a51929fc4f6f42bcb157cb65
```

This is the landed AUTO-3B authority revision.

## Calibration target

```text
repository = pie-peb3-lab/pie-peb3-calibration
PR         = 10
base       = 5673310fe66d74da5d31f165ffc4314e0d845740
final head = a14a497ad73eff13e7765390507bb3c30ff3fd2d
state      = OPEN / DRAFT / UNMERGED
```

The synthetic actor remained:

```text
synthetic:auto3-calibration-human
```

and all generated output remained explicitly classified as:

```text
calibration_only            = true
synthetic_evidence          = true
eligible_for_pilot_evidence = false
```

## First runtime defect

The first calibration run failed:

```text
run_id = 32692531960
result = FAILURE

GitHubProspectiveCaptureError:
source must be 'github-cli'
```

The defect was isolated to the calibration fixture. The Stage10J GitHub prospective source contract requires:

```text
source = github-cli
```

The fixture had used:

```text
source = synthetic-auto3-calibration
```

The synthetic classification did not need to occupy the source discriminator. It remains preserved separately in dataset provenance, warning metadata, actor identity, calibration flags, and pilot-ineligibility flags.

The fixture-only repair was committed as:

```text
a14a497ad73eff13e7765390507bb3c30ff3fd2d
```

No PIE core contract was relaxed.

## Successful runtime

The corrected runtime completed successfully:

```text
run_id          = 32693408313
artifact_id     = 9508004231
artifact_name   = auto3-controlled-outcome-32693408313
artifact_digest = sha256:8e132883a95b75fd4b2f27954f2fb085215fdffbfd44716b0509f72e45877d92
```

The artifact contained the controlled evidence capsule:

```text
evaluation-report.json
trust-report.json
review-packet.json
outcome-declaration.json
transport-first.json
transport-replay.json
comparison-registry.json
reconciliation-sources.json
summary.json
result.json
README.txt
```

## End-to-end authority chain

The successful runtime exercised:

```text
PASS controlled evaluation
→ Trust assessment with evaluation binding
→ prospective intake
→ governed synthetic REVIEWED event
→ AUTO-3A explicit SAFE declaration
→ AUTO-3B declared Outcome transport
→ RECONCILED
→ identical declaration replay
→ idempotent = true
```

Exact evidence identities included:

```text
assessment_id = assessment-1472ff872a1261c94cfa05eaee1890f0
trust_report_id = trust-4c207d77faec061f8380e1dd039ed2c1
trust_report_sha256 = dc4c1f06204bc74460bcf22168582b90abf1cacbad1acb1f66ed66c496890210

review_event_id = event-da5dbf5f05a26f9303a084565fb7cd6a
review_packet_id = prospective-review-packet-4ef0e675d8376c702e5790861b2630e8
review_packet_sha256 = e0df5e71d716ac4252a1ad18ee64cf6ffce7ddcb9447a2a0298f07592268e108

evaluation_id = evaluation-878c96ea9517c9fb2974f6373823b472
evaluation_report_sha256 = f3f98a79577d98d87a5417d4c0694c28b59cf8af8ec656f306bfdd6455f67140

declaration_id = outcome-declaration-b0c7a54eff2005b153c8e24a6ad19f47
declaration_sha256 = b0c7a54eff2005b153c8e24a6ad19f471298b8ad5b8e34f751600806ef0ea2d1

outcome_event_id = event-ab4e0e03f3348347922667fa49319e06
final_registry_sha256 = 1ca6025b9ff4eae064775c03fbd068eb632f56c6676669f57cebb954df1807aa
summary_sha256 = d7dde303f777973bfa888b5da28fb8ac71c7d73df15844946d7e576718b6f648
```

## Transport and replay assertions

First transport:

```text
status                = DECLARED_OUTCOME_RECORDED_AND_RECONCILED
reconciliation_status = RECONCILED
idempotent             = false
```

Identical declaration replay:

```text
status                = DECLARED_OUTCOME_RECORDED_AND_RECONCILED
reconciliation_status = RECONCILED
idempotent             = true
```

Both transports preserved the same:

```text
Outcome event identity
final registry identity
authority key
```

and the final campaign contained exactly one Outcome event.

This establishes the intended AUTO-3 boundary:

```text
explicit human declaration
→ validated authority binding
→ preflight source reconciliation
→ authoritative mutation
→ identical replay without duplicate Outcome
```

## Observed Trust projection is not pilot evidence

The synthetic case projected:

```text
predicted_risk_band = R2
trust_readiness      = NOT_READY
campaign_status      = COLLECTING_EVIDENCE
```

Those values are calibration observations only. In particular:

```text
synthetic REVIEWED event
!= real Stage10K human review evidence

synthetic SAFE controlled evaluation
!= real R0 production Outcome evidence

successful AUTO-3C calibration
!= pilot eligibility
```

No synthetic event from this calibration may increment real R0 campaign or pilot-eligibility evidence counters.

## Authority ceiling

The successful run preserved:

```text
human_outcome_declared        = true
automatic_outcome_inference   = false
outcome_recorded              = true
automation_authorized         = false
pilot_authorized              = false
merge_authorized              = false
deploy_authorized             = false
production_effect_authorized  = false
```

Therefore AUTO-3C proves only that the already-landed AUTO-3A/AUTO-3B authority chain works under a controlled synthetic calibration. It does not grant any additional operational authority.

## Durable evidence

Canonical closeout evidence is recorded at:

```text
evidence/trust/auto3-controlled-outcome-calibration-20260824.json
```

The external calibration artifact remains provider-hosted evidence and is referenced by exact run, artifact ID, digest, repository, PR, and revision. PIE does not silently reclassify the synthetic calibration repository as production evidence.

## Closeout

```text
AUTO-3A explicit declaration        = LANDED
AUTO-3B declared Outcome transport  = LANDED
AUTO-3C controlled evaluation chain = PASS
AUTO-3C first reconciliation        = PASS
AUTO-3C identical replay            = IDEMPOTENT
AUTO-3C duplicate Outcome count     = 0
AUTO-3C synthetic isolation         = PRESERVED
AUTO-3C pilot evidence eligibility  = FALSE
AUTO-3C authority ceiling           = PRESERVED
```
