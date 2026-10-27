# Project Intelligence Engine — Execution Roadmap

> Status: RECOVERY / VERIFICATION REQUIRED  
> Updated: 2026-10-27  
> Baseline verified: `main` at `7368fc01206158b69825eef787b9c6be8381d7ed`.  
> Scope: repository operating roadmap plus separate non-authoritative evidence-retention audit. This document must not overrule implemented contracts or source-code authority.

## Current implementation and governance

- PIE is a project-local technical intelligence and evidence control plane. Factory Intelligence and BuildMap-specific runtime coupling are outside current PIE authority.
- Continue `REPORT_ONLY`. Never infer HUMAN REVIEWED/AUDITED, SAFE Outcome, authorization to merge/deploy, or production correctness from CI success, merged PRs, archived Artifacts, or observed metadata.
- Operational/Trust/Calibration implementations already exist. Do not reimplement them based on older draft designs.
- Current `main` has merged PR #104. PR #105 is open at recorded head `55116f7bc1df7f959916c4d2dd101c0f963d9717`; its observed CI run 33504417761 failed on Python 3.14; Python 3.11/3.13 jobs were cancelled. Recheck current PR head/CI before any PR action.
- `docs/architecture/README.md` is a historical architecture index with an older snapshot; actual code and schemas remain authoritative.

## Immediate track A: Evidence preservation and census (external audit)

Source location on the authorized Windows device: `C:\Users\M\Documents\PIE-Evidence-Audit`. This directory is external, not an authoritative PIE Outcome Ledger.

### Verified baseline at handoff

- Existing Stage14 inventory: K_beauty 4,445 distinct observed Artifact IDs; Saju 3,943. Relevant observed pre-2026-11-27 PIE expiry candidates: 168 and 270 respectively.
- Stage14 remaining unqueried page ranges: K_beauty 2–49 (48 pages); Saju 2–83 (82 pages). This is not exhaustive repository coverage.
- Stage15 on 2026-10-27 separately saved page 49 (K_beauty) and page 83 (Saju), 100 rows each, zero newly observed expiry candidates. On-disk hashes: K_beauty `c9232c74c2ff774267347b45ad0cb81a4c3aaeda3e57676db124b3063a6b1586`; Saju `3e6a38898ebfda26ff6f6d15240133008d5e8cca3a8730501016acfc93fff867`. Reconcile all old+new snapshots before updating total unique counts.
- Original handoff reports 1,084 valid ZIPs and complete preservation of 1,055 identified expiry candidates. This has **not** been independently verified against local ZIP files/hashes during this recovery. Treat those totals as claims pending on-disk verification.
- Due to time-dependent GitHub pagination and deletions, a page-number sweep is a snapshot of observations, not proof of complete cross-time capture.

### Next actions

1. Run read-only on-disk ZIP count, archive integrity, ID-to-file mapping, and SHA-256 verification; publish a redacted manifest of found/missing IDs. Do not export raw ZIP content to GitHub.
2. Merge Stage15 page captures into the local inventory; verify duplicate ID metadata consistency, source timestamps, and revised unqueried range (provisionally K_beauty 2–48 = 47; Saju 2–82 = 81), then write a current reconciliation.
3. Continue bounded, rate-limit-aware GitHub API metadata collection from K_beauty 48 and Saju 82, never overwrite a captured page, and record GitHub `total_count` drift.
4. For any newly found unexpired PIE Artifact before the cutoff, download and hash only if not already archived and permitted. Mark unverified/missing as such.
5. Never declare seven-repository full backup unless the chosen time/window coverage and on-disk ZIP verification are actually exhaustive.

## Immediate track B: Repository PR health

1. Inspect PR #105 at its live head, collect Python 3.14 failing test diagnostics, and classify whether failure is attributable to the proposed diff or baseline.
2. Propose focused fix and tests on a feature branch only after evidence supports a specific change; open PR and let CI verify.
3. Do not merge, deploy, delete evidence, or enable auto-merge without explicit authorization.

## Outcome-learning blocker

- Keep `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES` until source-reconcilable authoritative project-local Outcomes exist.
- CI metadata, prospective capture, and Artifact retention do not constitute authoritative Outcome evidence. No speculative calibration/risk-engine change.

## Completion criteria

- Inventory coverage report reconciled and explicit about remaining gaps.
- All files claimed as preserved have recorded on-disk ZIP integrity and hash/ID evidence.
- PR #105 status and exact CI diagnosis documented.
- No change to Trust/Outcome authority or cross-project evidence promotion.
