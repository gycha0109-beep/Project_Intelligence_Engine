# PEB-4A — Real R0 Pilot Eligibility Blocker

Status: `BLOCKED / REAL_R0_PILOT_ELIGIBILITY_EVIDENCE_NOT_ESTABLISHED`

## 1. Authority alignment

The original Production Execution Boundary assessment defines PEB-4 as:

```text
Explicit Human Pilot Authorization Boundary
```

The landed PEB-4A Production Execution Authorization Review remains valid as a generic pre-effect request contract, but it is subordinate to that original authority sequence.

Therefore PIE must not nominate an arbitrary production resource merely because PEB-4A boundary entry was authorized.

The first production-side request may proceed only from an authoritative R0 pilot evidence chain that has reached:

```text
ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

and must then receive a separate exact one-shot authorization for the resulting hashed request.

Current fixed flags remain:

```text
production_boundary_authorized = true
production_execution_authorized = false
effect_authorization.authorized = false
automation_authorized = false
pilot_authorized = false
Stage10K HUMAN_DECISION = NO NEW DECISION
```

## 2. Required authority chain

The relevant repository authority is:

```text
real change
  -> Stage 10J GitHub prospective capture
  -> Stage 10A Trust assessment
  -> Stage 10I prospective assessment
  -> Stage 10K governed review packet
  -> explicit REVIEWED | AUDITED HUMAN_DECISION
  -> later authoritative Outcome
  -> optional Stage 10F Independent Audit
  -> Stage 10C exact source reconciliation
  -> Stage 10D observation projection
  -> Stage 10H canonical runtime package
  -> Stage 10G exact replay
  -> Stage 10E R0 pilot safety review
```

Only the final eligible evidence state can request explicit human pilot authorization. Eligibility itself is not pilot authorization.

## 3. Current repository evidence result

Stage 10G records that the committed repository did not contain a canonical R0 pilot evidence package and therefore concluded:

```text
COMMITTED_R0_EVIDENCE_PACKAGE_PRESENT = NO
COMMITTED_REPOSITORY_ELIGIBILITY = NOT_ELIGIBLE
NEXT_STEP = PROVIDE_COMPLETE_R0_EVIDENCE_PACKAGE
```

Stage 10H subsequently searched the connected repository/GitHub/Actions surfaces and recorded:

```text
BLOCKED_EXTERNAL_EVIDENCE_REQUIRED
```

with no canonical runtime R0 acquisition workspace available.

This remains an evidence-input blocker, not an implementation failure.

## 4. Subsequent real prospective evidence search

The later prospective validation PRs were audited rather than inferred from implementation tests or samples.

The strongest real prospective case found is PIE validation PR #35 against real external Saju PR #1.

Its authoritative recorded result is:

```text
assessment = assessment-69c9afead15517a2d60b06245f946249
effective risk = R4
readiness = NOT_READY
campaign status = COLLECTING_EVIDENCE
human_review_recorded = false
outcome_recorded = false
pilot_authorized = false
```

That run successfully exercised Stage 10J capture, Stage 10I intake, and Stage 10K packet preparation/replay, but it explicitly did **not** submit a Stage 10K human review and did not create an Outcome.

It is therefore useful real prospective validation evidence, but it is not R0 campaign evidence and cannot satisfy pilot eligibility.

Repository PR searches for the terminal eligibility strings resolve to the Stage 10E/10G implementation and inventory work, not to a later authoritative runtime package that actually reached eligibility.

No issue-carried Stage 10K `REVIEWED` campaign evidence was found in the connected PIE repository surface during this audit.

## 5. Gate still required

The approved V1 operational gate remains unchanged:

```text
R0 assessments              >= 20
R0 reviewed                 >= 20
R0 conclusive outcomes      >= 12
R0 confirmed SAFE           >= 12
unsafe challenge evidence   >= 8
R0 independent audits       >= 5
R0 outcome coverage         >= 60%
evidence span               >= 14 days
R0 false negatives          = 0
R0 false-negative rate      = 0.0
```

Synthetic evidence, fixtures, historical CI success, PR merge approval, prior chat instructions, or retrospective validations must not be promoted to satisfy this gate.

## 6. Current hard blocker

The current production/pilot boundary is therefore:

```text
PEB-4A REVIEW CONTRACT = LANDED
PEB-4 TARGET NOMINATION = BLOCKED
PEB-4 PILOT ELIGIBILITY = BLOCKED
PRODUCTION EFFECT AUTHORIZATION REQUEST = NOT READY

HARD BLOCKER
= REAL_R0_PILOT_ELIGIBILITY_EVIDENCE_NOT_ESTABLISHED
```

No production target is nominated and no production mutation is permitted.

## 7. Required next work

The next work is operational evidence collection, not another authority shortcut:

1. capture genuine future R0 changes prospectively;
2. prepare exact Stage 10K review packets;
3. obtain genuine explicit human `REVIEWED` / `AUDITED` decisions where appropriate;
4. observe later authoritative SAFE/UNSAFE Outcomes;
5. obtain Stage 10F Independent Audit evidence under its separate issuer authority where required;
6. reconcile and observe the campaign through Stage 10C/10D;
7. publish/replay a Stage 10H/10G package;
8. require an exact Stage 10E result of `ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW`.

Only after that may PIE construct the exact PEB-4A hashed production/pilot effect request and ask for a separate PEB-4B one-shot human authorization.

## 8. Frozen ceiling

```text
production_execution_authorized = false
effect_authorization.authorized = false
automation_authorized = false
pilot_authorized = false
Stage10K HUMAN_DECISION = NO NEW DECISION
Trust v1.5 = UNCHANGED
existing R4 authority = UNCHANGED
```
