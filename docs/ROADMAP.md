# Project Intelligence Engine — Execution Roadmap

> Status: RECOVERY / VERIFICATION REQUIRED  
> Updated: 2026-10-30  
> Baseline verified: `main` at `7368fc01206158b69825eef787b9c6be8381d7ed`.  
> Scope: repository operating roadmap plus separate non-authoritative evidence-retention audit. This document must not overrule implemented contracts or source-code authority.

## Active execution state — 2026-10-30 (supersedes earlier recovery to-dos)

- **Evidence recovery**: All **1,084** original Artifact IDs from the historical Stage12 preservation cohort have been individually recovered as GitHub source ZIPs to the authorized Windows PC and fresh ZIP SHA-256/size/CRC verified. Of these, **997** match recovered historical Stage12 SHA-256 values; **87** lack an available historical SHA-256 comparator. The original 2026-10-27 Stage12 consolidated container bytes remain unavailable, so **historical byte-for-byte container equivalence is NOT proven**.
- **Reconstructed full historical cohort**: `verified/PIE_EVIDENCE_1084_RECONSTRUCTED_2026-10-30.zip`, **21,908,593 bytes**, SHA-256 `492d06b2708356e56aa666e77b26c76d7224f4e1c49308e29d508206827e80b6`, with all 1,084 embedded source ZIP hashes independently validated. Local reports: `inventory/stage30-historical-eight-identification.json`, `stage31-eight-archive-recovery.json`, `stage32-full-source-zip-audit.json`, `stage33-reconstructed-full-bundle-verified.json`.
- **Fresh seven-repository census**: Authenticated GitHub read-only bounded sequential/parallel sweeps on 2026-10-30 captured **24,483** currently listed Artifacts in total, with per-page counts matching API totals, no duplicate IDs, and opening/closing page-1 IDs and total counts stable within each sweep. This is **not a server-atomic snapshot**. Reports: `stage35-live-artifact-census-reconciliation.json`, `stage37-all-seven-current-census-reconciled.json`.
- **Extended preservation**: Recovered a separate **764** additional PIE ZIPs expiring from **2026-11-27 00:00 UTC (inclusive)** to **2026-12-01 00:00 UTC (exclusive)**, excluding historical cohort members already archived. Independently verified their fresh SHA-256/size/ZIP CRC; historical SHA comparator is not available. New separate bundle: `verified/PIE_EVIDENCE_2026-11-27_TO_2026-12-01_2026-10-30.zip`, **19,873,960 bytes**, SHA-256 `91c22e1c096cc5767cf769c8b84a2569999f2896e3d621c975566f7056537175`. Local report `stage40-next-expiry-bundle-validation.json`.
- **Current verified coverage (Stage47)**: **5,398** distinct original Artifact ZIPs exist on the authorized Windows PC: historical reconstructed 1,084 + Nov-27/Dec-1 764 + Dec-1/Dec-8 1,473 + Dec-8/Dec-15 Stage45 **2,077**. In the bounded 2026-10-30 seven-repo API snapshot (24,483 Artifact IDs), **5,386** currently indexed PIE Artifacts expiring before **2026-12-15 00:00 UTC** are accounted for by the local source files; missing **0**, size conflicts **0**, SHA conflicts **0**. Breakdown **1,055** pre-Nov-27, **778** Nov-27/Dec-1, **1,476** Dec-1/Dec-8, **2,077** Dec-8/Dec-15. The 12 extra original ZIPs lie outside the current cutoff; do not conflate snapshot coverage with an atomic/live census or Outcome authority. Report: `inventory/stage47-predec15-retention-coverage-verified.json`.
- **Stage42 / Stage43 live backup COMPLETED**: Windows Desktop Commander access and existing GitHub CLI keyring authentication were restored. Downloaded all **1,473/1,473** previously identified, not-yet-preserved original GitHub Artifact ZIPs expiring **2026-12-01 inclusive to 2026-12-08 exclusive**; read-only downloads only; validated every ZIP against its saved API size, fresh SHA-256, archive member safety and ZIP CRC. Total source ZIP bytes **70,793,828**. Independently re-read all 1,473 local sources and embedded ZIPs in `verified/PIE_EVIDENCE_2026-12-01_TO_2026-12-08_2026-10-30.zip`, **71,674,015 bytes**, outer SHA-256 `185e225a9576913ae99b79b0fb6d913b46c2a211f3fdd8478cb3833c609e7679`, outer ZIP CRC PASS, 1,474 outer members (1,473 sources + manifest), missing/corrupt/partial ZIPs **0**. Per-repo newly preserved: K_beauty **162**, Saju **1,305**, journey-connect-backend **6**. Reports: `inventory/stage42-dec1-dec8-receipts.ndjson`, `stage43-dec1-dec8-bundle-verified.json` and `stage44-predec8-retention-coverage-verified.json`. Source hashes are current-download receipts, **not** newly verified historical SHA-256 equivalence.
- **Other operational gates**: PR #105 remains open/unmerged with latest checked CI SUCCESS; PR #106 is a draft docs-only recovery PR and must stay unmerged without approval. Four official PIE human-review/outcome workflows had zero GitHub runs in the Stage29 check, which does **not** exclude independent human Outcome records elsewhere. Continue `REPORT_ONLY` and `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES`; do not auto-merge/deploy or mutate Trust/Outcome policy.

### Next active actions

1. Re-verify the **four local retention bundles** (historical 1,084; Nov-27/Dec-1 764; Dec-1/Dec-8 1,473; Dec-8/Dec-15 2,077) using Stage48 independently verified source-ID sets, per-entry SHA-256/size, archive CRC and absence of overlap. The **997** historical Stage12 SHA matches remain distinct from the **87** source ZIPs with no available old hash comparator. Do not upload raw evidence ZIPs to GitHub.
2. Next unpreserved observed expiry horizon: **2026-12-15 to 2026-12-31 UTC**, with **6,637** previously observed PIE Artifact IDs (**313,010,785 API-reported source bytes**) in the saved Stage38 census. Split by expiration subwindow, check authenticated rate limit, and preserve only after pinned source-cohort validation. Do not imply global completeness across changing API listings.
3. Periodically compare a refreshed bounded seven-repo census with the local source ZIP manifest and record drift explicitly.
4. Seek only source-reconcilable, authorized project-local human Review/Outcome records for ORL-7. Until then maintain `REPORT_ONLY` and `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES`; no synthetic Outcome, inferred audited correctness or trust promotion.
5. Keep PR #105/#106 exact-head CI status current; no automatic merge, deployment, or policy mutation.

## Current implementation and governance

- PIE is a project-local technical intelligence and evidence control plane. Factory Intelligence and BuildMap-specific runtime coupling are outside current PIE authority.
- Continue `REPORT_ONLY`. Never infer HUMAN REVIEWED/AUDITED, SAFE Outcome, authorization to merge/deploy, or production correctness from CI success, merged PRs, archived Artifacts, or observed metadata.
- Operational/Trust/Calibration implementations already exist. Do not reimplement them based on older draft designs.
- Current `main` has merged PR #104. PR #105 remains open/unmerged at head `085c44efee47f7886678e08abf31f85395d125bc`; its CI run `41002685159` completed SUCCESS across Python 3.11, 3.13 and 3.14. Previous head failures are historical, not current blockers.
- `docs/architecture/README.md` is a historical architecture index with an older snapshot; actual code and schemas remain authoritative.

## Historical track A: Evidence preservation and census (baseline, superseded by active state)

Source location on the authorized Windows device: `C:\Users\M\Documents\PIE-Evidence-Audit`. This directory is external, not an authoritative PIE Outcome Ledger.

### Verified baseline at handoff

- Existing Stage14 inventory: K_beauty 4,445 distinct observed Artifact IDs; Saju 3,943. Relevant observed pre-2026-11-27 PIE expiry candidates: 168 and 270 respectively.
- Stage14 remaining unqueried page ranges: K_beauty 2–49 (48 pages); Saju 2–83 (82 pages). This is not exhaustive repository coverage.
- Stage15 on 2026-10-27 separately saved page 49 (K_beauty) and page 83 (Saju), 100 rows each, zero newly observed expiry candidates. On-disk hashes: K_beauty `c9232c74c2ff774267347b45ad0cb81a4c3aaeda3e57676db124b3063a6b1586`; Saju `3e6a38898ebfda26ff6f6d15240133008d5e8cca3a8730501016acfc93fff867`. Reconcile all old+new snapshots before updating total unique counts.
- Original handoff reports 1,084 valid ZIPs and complete preservation of 1,055 identified expiry candidates. This has **not** been independently verified against local ZIP files/hashes during this recovery. Treat those totals as claims pending on-disk verification.
- Due to time-dependent GitHub pagination and deletions, a page-number sweep is a snapshot of observations, not proof of complete cross-time capture.

### Original recovery actions (historical; superseded by active state)

1. Run read-only on-disk ZIP count, archive integrity, ID-to-file mapping, and SHA-256 verification; publish a redacted manifest of found/missing IDs. Do not export raw ZIP content to GitHub.
2. Merge Stage15 page captures into the local inventory; verify duplicate ID metadata consistency, source timestamps, and revised unqueried range (provisionally K_beauty 2–48 = 47; Saju 2–82 = 81), then write a current reconciliation.
3. Continue bounded, rate-limit-aware GitHub API metadata collection from K_beauty 48 and Saju 82, never overwrite a captured page, and record GitHub `total_count` drift.
4. For any newly found unexpired PIE Artifact before the cutoff, download and hash only if not already archived and permitted. Mark unverified/missing as such.
5. Never declare seven-repository full backup unless the chosen time/window coverage and on-disk ZIP verification are actually exhaustive.

## Historical track B: Repository PR health (baseline, superseded by active state)

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

## Progress checkpoint — 2026-10-30 (Stage20 local archive preflight)

- Created `C:\Users\M\Documents\PIE-Evidence-Audit\stage20_verify_archive.py`, a syntax-checked, read-only verifier for the historical Stage12 consolidated ZIP once its actual bytes are made available on the authorized Windows PC.
- It checks exact expected filename, 21,647,697 byte size, historical SHA-256 `a9598f971eec6b0c44941781868cf404217213091b81aff6b892318e183cbe77`, archive member path safety, outer ZIP CRC, count of 1,084 nested Artifact ZIPs, and nested ZIP CRC. This lightweight verifier does not independently recreate PIE internal evidence manifest/authority validation; use original Stage12 verifier for that.
- Ran syntax compilation and the preflight, producing `inventory/stage20-archive-zip-reverification.json` with `status=ARCHIVE_UNAVAILABLE`. The archive is indexed in ChatGPT Library but its raw bytes could not be materialized in this execution and no local Windows copy has been found.
- Therefore **current fresh ZIP byte-level verification remains incomplete**, although the historically generated package, Stage12 report and ID reconciliation support an earlier preservation claim. No expired-vs-preserved inference or authority promotion is permitted.

## Progress checkpoint — 2026-10-30 (Stage21 rate-limited continuation)

- At 2026-10-30 01:32 UTC, GitHub anonymous REST core budget remained 12/60, reset scheduled for 02:01:39 UTC (11:01:39 KST). Kept a minimum reserve of 10, captured Saju middle page 27, and stopped at 10 remaining rather than bypassing the prior rate guard.
- Saved its source metadata and exact SHA-256 receipt in `inventory/middle-page-acquisition/Saju/page-0027.json` and `inventory/stage21-saju-capture.ndjson`, on the authorized Windows device. Page contained 100 Artifact metadata records and zero additional pre-2026-11-27 PIE expiry candidates.
- Reconciled 100 K_beauty page-snapshot files and 100 Saju page-snapshot files with `stage21_reconcile.py`, saved `inventory/stage21-evidence-census-reconciled.json`. K_beauty 9,227 unique observed IDs (9,945 rows; 718 repeat occurrences), Saju 9,131 unique IDs (9,959 rows; 828 repeats). No malformed records or conflicts in name, size, expiry for duplicate IDs.
- K_beauty designated middle pages 2–71 captured; Saju remaining designated middle pages **2–26 (25 pages)**. Snapshots span multiple collection dates and total-count drift; completeness is not guaranteed by historical page-number coverage.
- Re-checked the 2026-11-27 pre-expiry set: K_beauty 168 IDs, earliest 2026-11-22 01:27:06 UTC; Saju 270 IDs, earliest 2026-11-22 01:33:56 UTC. All 438 IDs match the *historical indexed Stage12 ledger*; fresh archive ZIP byte verification remains unavailable.
- Stage18 and Stage21 capture-receipt hashes match their stored local files; this attests only to local metadata capture integrity, not original GitHub archive authenticity, ZIP integrity, independent technical Outcome or reviewed authority.
- Continue read-only page capture from Saju page 26 on the next safe API budget window, reconcile drift and Stage12 ledger IDs after each batch, and stop on conflicting metadata. Do not merge/deploy/alter policy or change ORL-7 from `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES`.

## Progress checkpoint — 2026-10-30 (Stage22 GitHub CLI authentication)

- Confirmed `gh auth status` on the authorized Windows PC `DESKTOP-6C3L8O4` reports active GitHub account `gycha0109-beep`; did not read, print, export, or persist credential contents. `gh api rate_limit` returned authenticated core budget **5,000 requests/hour**; previous direct Python `urllib` calls used the anonymous 60/hour budget.
- Created and executed `stage22_gh_authenticated_capture.py` using read-only `gh api --method GET` and existing CLI keyring authentication, with no new credential material and no overwrites. Saved Saju middle pages **2–26**, exactly **25 new page JSON files / 2,500 rows**, 100 distinct IDs each, no newly observed pre-2026-11-27 PIE expiry candidates.
- Ran `stage21_reconcile.py` against all local page snapshots: K_beauty **9,227** distinct observed IDs and Saju **11,604**, combined **20,831** across both repositories. Metadata conflicts (name/size/expiry) **zero**. Oldest and middle page snapshots remain time-distributed, and GitHub listing total_count drift is observed; this is not a complete single-time snapshot or a verification of all historical artifacts.
- Ran `stage22_reconcile_authenticated.py`, independently verifying SHA-256 for all **25/25** new JSON files against persisted capture receipts; verified no gaps in the previously designated middle-page ranges for either repository.
- Observed pre-Nov-27 expiry candidates remain **168** K_beauty and **270** Saju. All 438 IDs appear in the historical indexed Stage12 ledger; **zero missing ID matches**, but archive ZIP byte existence/integrity on this Windows PC remains unverified. No permission, policy, Outcome authority or artifact archive integrity was inferred from metadata.
- Next: reconcile a fresh bounded live snapshot if a point-in-time census is required (API results can change while paging); recover original Stage12 consolidated archive bytes for independent ZIP hash/CRC rerun. Do not merge/deploy or change `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES`.

## Progress checkpoint — 2026-10-30 (Stage23–28 ZIP recovery and independently verified backup)

- **Original source recovery no longer blocked for the identified expiry cohort.** GitHub CLI `gh api` with the existing keyring credentials successfully re-downloaded original Artifact ZIP bytes to the authorized Windows computer, without reading/exporting the token. Recovery is local-only, read-only against GitHub.
- Recovered all 7-repository previously identified PIE Artifacts expiring before **2026-11-27 00:00 UTC**: **1,055/1,055 local ZIPs**, per repo K_beauty 168, Saju 270, BuildMap 20, AnnoyingRadar 258, ranking 204, thought-drawer 6, journey-connect-backend 129. This is the *historically observed cutoff cohort*, not every GitHub Artifact ever created.
- **Stage26 independent fresh audit:** `inventory/stage26-seven-repo-zip-validation.json`. Verified **1,055/1,055** files by re-reading actual local ZIP bytes, checking source inventory ID, size, receipt SHA-256, ZIP member safety/uniqueness, and CRC; missing files **0**, conflicts **0**, zero-byte incomplete files **0**. Raw ZIP bytes total **20,972,385**.
- **Evidence-strength split:** **976** recovered ZIPs match their historical Stage12 SHA-256 and size in indexed ledger. Remaining **79** (ranking 73, thought-drawer 6) pass live GitHub download, inventory size, fresh capture SHA-256 and ZIP CRC but **cannot be compared against historical SHA-256** because the indexed Stage12 CSV exposed only the first 997 of 1,084 rows. Do **not** promote those 79 to historical-byte-equivalence.
- **Stage27 reconstructed due-only bundle:** `C:\Users\M\Documents\PIE-Evidence-Audit\verified\PIE_EVIDENCE_DUE_RECOVERY_2026-10-30.zip`, size **21,456,439 bytes**, SHA-256 `44f7c086c66ddbd8c7e76282e8ffe23830f5909aa3e456dce9ae6f945ad6d193`. It contains all **1,055 nested original Artifact ZIPs** plus manifest and Stage26 verification result. Independently re-read bundled file, checked outer CRC, exactly 1,055 source ZIP paths and **1,055/1,055** embedded SHA-256s. Result at `inventory/stage27-bundle-verification.json`. This newly created package is **not claimed byte-for-byte identical** to the historical 1,084-entry Stage12 consolidated archive.
- **Stage28 supplementary restoration:** 21 non-cutoff original ZIPs identified in the indexed Stage12 ledger (K_beauty 6, Saju 3, BuildMap 4, AnnoyingRadar 4, journey-connect-backend 4) independently recovered with **21/21 historical SHA-256, size, ZIP CRC matches**; record: `inventory/stage28-historical-extras-recovery.json`. Total known local source ZIPs now **1,076** (1,055 cutoff cohort + 21 supplementary), but the remaining **8 non-cutoff historical Stage12 ZIP identities** (likely from ranking/thought-drawer, not proven) and the original Stage12 container byte hash remain **unrecovered/unverified**.
- Correction: an earlier Stage23 single-BuildMap probe had a manually miscopied expected SHA-256 and falsely reported a historical mismatch; **the actual file matches the source Stage12 ledger exactly**, rehashed and CRC verified. Immutable correction at `inventory/stage28-buildmap-probe-erratum.json`; do not use the uncorrected single probe as a failure finding.
- No raw evidence ZIP was uploaded to GitHub. The PR is documentation only. Continue `REPORT_ONLY`, no human Review or Outcome synthesis, no merge/deploy/trust policy mutation. `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES` stays in force.
- **Next execution priorities:** locate original historical Stage12 package bytes or a complete independent 1,084-ID manifest (to resolve remaining 8 and revalidate original container); assess fresh API snapshot drift if exhaustive current-time census is required; then seek only source-reconcilable project-local human Review/Outcome evidence for ORL-7 eligibility. PR #105 stays open and needs no new failing-Python-3.14 diagnosis on its latest green CI head.

## Progress checkpoint — 2026-10-30 (Stage29 independent ORL workflow readback)

- Ran read-only authenticated GitHub Actions workflow queries for the four official PIE review/outcome workflows: `operational-review-action.yml`, `operational-outcome-context.yml`, `operational-outcome-action.yml`, `prospective-human-review-bridge.yml`. All four workflows are **active** and currently each lists **zero GitHub runs** as of the local audit `2026-10-30T02:29:08Z`; source metadata saved at `inventory/stage29-orl-workflow-probe.json`.
- Zero listed runs are **not proof that independent human review/Outcome records do not exist elsewhere**, and cannot establish a TP/FP/FN/TN denominator, audited correctness, or release authority. Keep `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES`.
- PR #105 remains open/unmerged with CI SUCCESS at its latest inspected head `d11b216cba02293f1e5c6959683bff7480577255`. PR #106 remains a draft documentation PR, unmerged; its previous checkpoint CI at `7a549dc4ccc350e7b95a89dc95658efc261e0fc7` was SUCCESS (run `40991828863`). Do not merge automatically.

## Progress checkpoint — 2026-10-30 (Stage42 preparation; authorized PC unavailable)

- **Stage42 2026-12-01 to 2026-12-08 expiring cohort is NOT yet downloaded.** Prior Stage38/Stage34/Stage36 source snapshots identify 1,473 PIE Artifact IDs, 70,793,828 API-reported ZIP bytes. These must not be counted as preserved or CRC-verified in production.
- Desktop Commander on the previously authorized Windows PC did not respond to connectivity checks in this session; the alternative remote device path likewise reported the Windows PC offline. No local Windows ZIP or inventory was modified in this checkpoint.
- Prepared and offline-tested an improved standalone read-only Windows Stage42 execution package, `PIE_Stage42_v2_SafeResume_2026-10-30.zip` (available as an attachment in the working conversation; **not** committed to this repo or installed on the authorized PC). It verifies the pinned 1,473-ID target cohort, uses the already authenticated `gh api` CLI without exporting credentials, captures bounded batches, checks ZIP size/SHA-256/CRC, and writes a final Stage43 bundle only when all source ZIPs have independently passed revalidation.
- New crash/restart protection: if a completed ZIP or nonempty completed partial survived a process interruption before its receipt was persisted, the script re-downloads the source artifact, compares exact SHA-256/size/ZIP CRC, and only then promotes the orphan to verified. A corrupted, mismatched, missing or unexpectedly changed file is fail-closed, not silently accepted. Individual receipts are flushed/synced as downloads finish.
- Verified Python syntax, ZIP package member CRC, and offline fixture exercising bounded resume, orphan re-download matching, completed-partial recovery, corrupt orphan rejection, post-capture tamper detection, incomplete-set finalization refusal, and final bundle/embedded SHA checks. **This is an isolated simulated fixture, not live validation of 1,473 production artifacts.**
- Separately, the connected GitHub App successfully downloaded one previously known BuildMap source Artifact ZIP `9793602686` into the conversation environment; direct SHA-256 `03c8c81a0c2742ca4f30b49d6f149faf9397996f4bf643d0fadbfb1f010a4feb` matched the recorded historical ledger and ZIP CRC passed. This validates individual read-only download transport but **does not substitute for the 1,473-ID Stage42 cohort on the PC**.
- Next: restore authorized Windows PC access, copy the validated Stage42 v2 package (script + PowerShell runner) to the PC without changing prior evidence, execute the bounded batches, independently check the resulting `inventory/stage43-dec1-dec8-bundle-verified.json`, refresh the seven-repo retention coverage, then update this roadmap with actual SHA-256/CI evidence.
- No merge, deploy, deletion, policy mutation, or automatic ORL-7 authority promotion. Keep `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES`.

## Progress checkpoint — 2026-10-30 (Stage42 v3 crash-safe preparation)

- Windows device remains unreachable from the Desktop Commander connection in this chat. **No live Stage42 production source ZIPs have been collected or authenticated on that Windows PC in this checkpoint**; the 1,473 ZIPs (70,793,828 API-reported bytes) for `2026-12-01 <= expires_at < 2026-12-08` remain the *next unarchived observed cohort*.
- Completed independent v3 safety hardening of the portable local-only tool with preserved read-only `gh api` source flow, strict 1,473-ID cohort checks, bounded retries, and local SHA-256/ZIP CRC receipts.
- Specifically repaired a crash gap in v2: a finished final ZIP without its audit JSON, or a complete post-write `.partial` file awaiting atomic rename, is now re-read member-by-member and promoted only after exact receipt/hash/size/CRC/manifest checks. Already-finalized packages are verified idempotently; corrupted partials, mismatched existing final reports, and concurrent processes fail closed.
- An offline test fixture using fake GitHub source ZIPs passed all prior bounded capture/orphan-resume/tamper checks plus idempotent finalize, final-report restoration, complete-partial promotion, corrupt-partial refusal, final-report conflict refusal, and exclusive process lock. This is **not** an execution or evidence verification of 1,473 live GitHub source ZIPs.
- Portable package in the conversation: `PIE_Stage42_v3_CrashSafe_2026-10-30.zip`, SHA-256 `70e8019a9afb7e1e83e25fd20428cd2c7062746708bc15c74cf2d028c4fe43f8`. Script SHA-256 `9825de5b5a8a1a1171c44e210ca65a8297f4bedb833235503584059cb02c804f`. Persistent instructions: [Stage42 crash-safe runbook](EVIDENCE_RETENTION_STAGE42_RUNBOOK.md).
- **Remaining external dependency:** Reconnect the authorized Windows PC; validate portable package bytes and existing inventory locally; execute source ZIP collection and independent Stage43 bundle/hash verification. Do not upload source archives to GitHub, auto-merge PRs, or convert GitHub CI into authoritative Outcome evidence.

## Progress checkpoint — 2026-10-30 (PR #105 fail-closed input validation hardening)

- Moved forward on existing, unmerged calibration sidecar PR #105 `feat/calibration-policy-match-sidecar`, without merging or altering the Outcome / Trust authority boundary.
- Fixed `verify_calibration_policy_match_explanation_binding()` to return its structured validation errors for non-object sidecars rather than raising `AttributeError` at a subsequent `.get()`. Added a regression test covering `None`, list, string, and integer inputs.
- Fixed `_normalized_path()` to reject Windows drive-absolute and drive-relative path prefixes (`C:/...`, `D:...`) that `PurePosixPath.is_absolute()` alone incorrectly treated as relative on Linux. Added tamper-input regression tests for both path forms.
- Code commits: `3a804e1` (malformed sidecar guard), `95cebd9` (Windows drive guard); test commits `b474542`, `085c44e`. PR #105 latest head `085c44efee47f7886678e08abf31f85395d125bc`; GitHub CI run **`41002685159` completed SUCCESS**, including Python **3.11, 3.13, and 3.14** jobs.
- Revalidated the existing independent Stage42 v3 portable package locally in the conversation runtime with **Python 3.13.5**: ZIP member CRC PASS and exact package SHA-256 `70e8019a9afb7e1e83e25fd20428cd2c7062746708bc15c74cf2d028c4fe43f8`; `test_offline_fixture.py` passed simulated capture, interruption, hash-matched recovery, and finalization scenarios.
- **No change** to actual Stage42 production retention coverage: 1,473 identified Dec-1–Dec-8 source Artifacts remain to be downloaded and independently verified on the authorized Windows device. Desktop Commander connection failed. No fabricated source hashes, no source ZIP upload to GitHub, no ORL-7 Outcome inference, no merge or deploy.


## Progress checkpoint — 2026-10-30 (Stage42 live retrieval + Stage43/44 verification)

- The authorized Windows PC (DESKTOP-6C3L8O4) connection recovered. Existing GitHub CLI login `gycha0109-beep` verified without viewing/printing/exporting any token. Previous locally preserved 1,848 original ZIPs remained present before capture; no source archive was overwritten.
- Created `stage42_dec1_dec8_capture_live.py` as a separate, controlled local derivative of previously validated `stage39_next_expiry_preservation.py`; pinned the exact Stage38 1,473-ID / 70,793,828-byte window, excluded both historical 1,084 and the previously recovered 764 IDs, and persisted one SHA-256/size/CRC receipt per successful capture. **This was actual live local execution, not the portable Stage42 v3 simulation**.
- GitHub API GET-only source artifact downloads completed **1,473/1,473**, no download failures or size/CRC mismatches. `inventory/stage42-dec1-dec8-receipts.ndjson` contains **1,473** unique receipts. Audit copied no raw ZIP bytes to the PIE GitHub repository and changed no policy/authority source.
- Independent `stage43_dec1_dec8_independent_bundle.py` re-read and checked all source ZIPs by ID, SHA-256, inventory size, safe unique member paths and ZIP CRC; produced `verified/PIE_EVIDENCE_2026-12-01_TO_2026-12-08_2026-10-30.zip` (**71,674,015** bytes; SHA-256 **`185e225a9576913ae99b79b0fb6d913b46c2a211f3fdd8478cb3833c609e7679`**). Verified outer member set **1,474**, CRC PASS and all **1,473/1,473** embedded SHA-256 matches.
- Independent repeated post-write Windows readback: local bundle exists, exact SHA-256 matches Stage43 report, outer CRC PASS, receipt count **1,473**, all original local ZIPs **3,321**, outstanding `.partial` files **0**. `inventory/stage43-dec1-dec8-bundle-verified.json`.
- Stage44 seven-repo snapshot-to-local recheck found **3,309** currently indexed PIE ZIP IDs expiring before Dec-8; **3,309/3,309** local source bytes matched size/hash, **zero missing/size/hash conflicts**. Breakdown **1,055** pre-Nov-27, **778** Nov-27/Dec-1, **1,476** Dec-1/Dec-8. The 1,476 includes three source ZIPs already present in reconstructed historical cohort; newly recovered Stage42 members number **1,473**. Total local **3,321** includes 12 historical records expiring beyond cutoff. Report `inventory/stage44-predec8-retention-coverage-verified.json`.
- Remaining: Stage38's next unpreserved December 8–15 expiry cohort (previous snapshot: 2,077), 87 historic ZIPs without recoverable original ledger hash comparators and original Stage12 1,084-entry consolidated container byte-equivalence, plus project-local human Review/Outcome evidence for ORL-7. Continue `REPORT_ONLY`; `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES`; no PR merge, deploy or permission escalation.

## Progress checkpoint — 2026-10-30 (Stage45–48 real original ZIP preservation)

- Authorized Windows Desktop Commander access is available again. Before this checkpoint, the same audit root already held the completed Stage42 receipts (**1,473**) and Stage43 source-bundle report. Verified actual Stage43 bundle SHA `185e225a9576913ae99b79b0fb6d913b46c2a211f3fdd8478cb3833c609e7679`; Stage44 pre-Dec-8 snapshot coverage **3,309/3,309**, no missing/size/hash conflicts.
- Stage45 mid-execution had **1,361/2,077** individual ZIP receipts already recorded; completed the remaining **716** on the same authorized Windows PC with read-only authenticated `gh api`, bounded `--limit 80 --workers 4` batches and fail-closed per ZIP source-size/SHA/CRC receipts. Final receipts **2,077/2,077**, unique Artifact IDs **2,077**, raw original ZIP bytes **26,858,555**, by repo K_beauty **903**, Saju **1,174**, zero capture errors. Local file `inventory/stage45-dec8-dec15-receipts.ndjson`.
- Stage46 independently re-read all 2,077 local original ZIP bytes, validated against saved API inventory size and Stage45 SHA-256 receipts, checked nested ZIP member safety/uniqueness and CRC, built a separate due-only bundle `verified/PIE_EVIDENCE_2026-12-08_TO_2026-12-15_2026-10-30.zip`. Exact **28,121,460 bytes**, outer SHA-256 **`632c285338ff2ad0e847ec599e292403c9cb877f2c576912d8a8be567e0a0872`**, outer CRC PASS, all **2,077** embedded hashes verified; report `inventory/stage46-dec8-dec15-bundle-verified.json`. Historical SHA comparators were not available for this new cohort.
- Stage47 seven-repo bounded-snapshot reconciliation: observed pre-2026-12-15 PIE expiry IDs **5,386**, all **5,386/5,386** found in the local source ZIP collection, **zero** missing/size/SHA conflicts; local source ZIP count **5,398**. Note counts of current expiry cohorts differ from newly downloaded ZIP counts due to 12 historical records outside the cutoff and archive overlap with older date windows. Report `inventory/stage47-predec15-retention-coverage-verified.json`.
- Stage48 separately opened **all four** recovered source bundles, revalidated outer SHA-256 and CRC, checked **5,398/5,398** embedded member SHA/size against both manifest and individual local ZIP, and asserted zero source-ID overlap across archive cohorts or stray/missing local sources. **All checks PASS**; `inventory/stage48-four-bundle-cross-validation.json`. The 2026-10-27 original Stage12 consolidated container bytes remain unavailable and byte-for-byte identity with a newly reconstructed container is not claimed.
- No GitHub write to source repositories, ZIP evidence upload, human Outcome inference, ORL-7 unlock, Trust mutation, PR merge or deployment.
