# Universal Review Orchestrator Skill v0.1.1

## Mission

Operate an evidence-driven review using the configured repository scope, effective project profile, selected Review Packs, and deterministic gate policy. Do not treat prior AI conclusions, documentation, tests, or code as independently authoritative.

## Required inputs

- Valid `.review/project.yml`.
- Repository contents at an identified baseline.
- Review mode: full, change, risk, release, or incident.
- Available execution environment and explicit constraints.

## Mandatory lifecycle

1. Resolve and validate the effective project profile.
2. Record branch, commit, tool versions, constraints, and unavailable environments.
3. Initialize a run and snapshot protected paths when configured.
4. Execute baseline commands before modification and record exact results.
5. Map entrypoints, trust boundaries, data flows, transaction boundaries, and persistence boundaries.
6. Select and lock Review Packs; for change reviews, record Pack-selection reasons.
7. Run Explorer passes independently and write only candidate findings.
8. Run Challenger passes against every candidate and retain rejection reasons.
9. Run Verifier passes against surviving findings using the strongest available evidence.
10. Apply only approved remediations; mark them `FIXED`, not `RESOLVED`.
11. Execute targeted and required regression verification.
12. Promote a fix to `RESOLVED` only with E5 evidence.
13. Synchronize `findings.json` into `run.json`.
14. Verify protected baselines and calculate the deterministic Gate.
15. Validate the complete run directory and archive it with a final SHA-256 manifest.

## Non-negotiable rules

- Never claim completeness or proof of correctness from a clean review.
- Never classify a hypothesis as P0/P1.
- Never accept a P0 finding as residual risk.
- Never equate `FIXED` with `RESOLVED`.
- Never use test count as a substitute for test-oracle quality.
- Never use mocks as proof of actual database or runtime behavior.
- Never alter protected paths unless explicitly authorized; any mutation must be surfaced by baseline verification.
- Never hide skipped commands, inaccessible environments, or unsupported assumptions.
- Every P0/P1 finding must include scope, impact, reachable path, evidence, reproduction, remediation, and verification.
- Every E3+ evidence item must include an explicit observed result.
- Rejected findings and merge conflicts must remain visible to prevent repeated false positives.
- Gate metrics derived from Findings take precedence over manually declared Finding counts.

## Role boundaries

### Explorer

Search broadly. Produce `candidate-findings.json`. Do not approve remediation or Gate decisions.

### Challenger

Attempt to reject or downgrade each candidate through existing controls, reachability analysis, intended behavior, framework guarantees, scope exclusions, and contradictory evidence. Record decisions in `challenge-log.md` and rejected items in `rejected-findings.json`.

### Verifier

Reproduce surviving findings or downgrade them. Record commands, environment, results, evidence level, and artifacts in `verification-log.md` and `evidence-ledger.md`.

### Gate

Use synchronized structured findings and operational metrics only. Do not override policy based on narrative confidence.

## Required run outputs

- `run.json`
- `inputs/` copies of available invariants, entrypoints, and accepted-risk records
- `project-profile.source.yml`
- `project-profile.resolved.yml`
- `packs.lock.json`
- `repository-map.md`
- `traceability-matrix.md`
- `candidate-findings.json`
- `findings.json`
- `rejected-findings.json`
- `challenge-log.md`
- `verification-log.md`
- `evidence-ledger.md`
- `residual-risks.md`
- `gate-result.json`
- `final-gate.md`
- `manifest.sha256`

## Completion condition

A review is complete only when the run directory validates, Finding state is synchronized, protected-baseline status is known where required, Gate output is reproducible, and the archive manifest verifies.
