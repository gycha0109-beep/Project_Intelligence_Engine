# Project Intelligence Engine — Execution Roadmap

> Status: RECOVERY / VERIFICATION REQUIRED  
> Updated: 2026-10-30  
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

## Progress checkpoint — 2026-10-29 (local audited files)

- Confirmed PR #105 advanced to head `d11b216cba02293f1e5c6959683bff7480577255`; GitHub CI run `40819794723` finished `success`. PR is still open/unmerged; previous Python 3.14 failure belongs to an older head.
- Resumed read-only, bounded local GitHub artifact-page captures with `stage17_bounded_acquisition.py`; raw metadata page files and per-page hashes retained only on Windows PC.
- Reconciled local captures using `stage17_reconcile.py` into `inventory/stage17-reconciliation.json`. K_beauty: 7,245 unique observed IDs, 168 observed pre-Nov-27 due candidates, 0 conflicting duplicate metadata, unqueried pages 2–21 (20). Saju: 6,363 unique observed IDs, 270 due candidates, 0 conflicting duplicates, unqueried pages 2–55 (54). These are snapshot-scoped observations, not repository-wide exhaustive coverage.
- Observed differing GitHub artifact total counts across snapshots (especially Saju). Reconcile by Artifact IDs and capture timestamps, not page position alone.
- Archived ZIP file count/integrity and original storage location remain **unverified**. Previous 1,084 ZIP claim must not be promoted to confirmed status.
- Next action: continue rate-limited metadata acquisition from K_beauty page 21 / Saju page 55, then rerun exact ID/expiry reconciliation. Preserve missing/unknown and archival evidence separately.

## Progress checkpoint — 2026-10-30 (verified local audit)

- GitHub PR #105 exact head `d11b216cba02293f1e5c6959683bff7480577255`: CI run `40819794723` SUCCESS; PR remains open/unmerged. PR #106 preceding head `667d005c1c80b49340231a40ca1a351b583b1c50`: CI run `40824803364` SUCCESS.
- Resumed collection at K_beauty page 21 and Saju page 55. Captured 48 further pages (4,800 metadata rows) via bounded read-only GitHub requests with no overwrites; verified all 48 newly captured files against their SHA-256 receipt.
- Saved `inventory/stage18-collection.ndjson` and `inventory/stage18-reconciliation.json` on the authorized Windows PC under `C:\Users\M\Documents\PIE-Evidence-Audit`.
- K_beauty: 9,227 distinct observed Artifact IDs across time-varying snapshots, 0 name/size/expiry metadata conflicts, 168 observed pre-Nov-27 due PIE artifacts. Designated middle pages 2–71 have all been captured; this is *not* an exhaustive point-in-time repository census.
- Saju: 9,033 distinct observed Artifact IDs, 0 name/size/expiry conflicts, 270 observed pre-Nov-27 due PIE artifacts. Still unqueried: pages 2–27 (26 pages).
- No additional PIE Artifact with expiry before 2026-11-27 was found in the newly captured 48 pages. Different GitHub API total counts between collection times demonstrate pagination drift; do not equate page coverage with absolute completeness.
- Stopped when anonymous GitHub core API budget reached 12 remaining. Do not bypass the limit guard; resume Saju page 27 when the limit renews or a properly authorized read-only method is available.
- Original 1,084 ZIP / 1,055 protected Artifact claims still lack verified local ZIP path, file integrity, and ID-to-file reconciliation. Keep archive preservation status UNKNOWN, distinct from verified metadata captures.
- Continue `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES`: GitHub CI, PR, and retention metadata are not verified project-local technical Outcomes.

## Progress checkpoint — 2026-10-30 (Stage19 ledger recovery)

- Found original preservation archive **as a named ChatGPT Library file**: `PIE_EVIDENCE_AUDIT_STAGE12_CONSOLIDATED_2026-10-27.zip` (Library metadata size 21,647,697 bytes). Original Stage13 documentation reports expected archive SHA-256 `a9598f971eec6b0c44941781868cf404217213091b81aff6b892318e183cbe77`; this digest was not recomputed during this recovery.
- The original Stage12 report records 1,084 archived original ZIPs and 1,084/1,084 prior ZIP/CRC/size validation. These are **historical verification claims**, not a new byte-level validation result. ChatGPT Library raw ZIP bytes could not be materialized in this session; the Windows audit folder still has no archive ZIPs.
- Also recovered indexed text of the historical Stage12 `ledger.csv` from ChatGPT Library. For K_beauty (174 ledger IDs) and Saju (273 ledger IDs), all relevant rows are present in that indexed text. The index was truncated after 1,000 rows overall, so this source cannot independently confirm the entire 1,084-ID archive census.
- Cross-checked that indexed ledger against locally collected metadata in `stage19_archive_ledger_id_check.py`; saved `inventory/stage19-archive-ledger-id-reconciliation.json`. All **168 K_beauty** and **270 Saju** previously identified pre-2026-11-27 PIE expiry IDs appear in the ledger: missing ID count **zero**. Six additional K_beauty ledger IDs and three Saju ledger IDs fall outside the current identified expiry set. This is **ID-list reconciliation, not local ZIP existence or integrity verification**.
- Remaining Saju middle-page collection 2–27 (26 pages) is not yet complete; anonymous GitHub REST API core budget was 12 requests remaining, preserving the rate guard. Resume after reset, without unauthorized credential use.
- GitHub REST Artifact listing supports `per_page` up to 100 and repository Actions read access for authenticated access; all current page captures remain read-only, partial and susceptible to page movement between timestamps.
- No Trust assessment, policy, human Review, authoritative Outcome, merge, deployment, or production action was changed. `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES` remains in force.
