# PIE Stage42 — December 1–8 evidence-retention runbook

**Status: PREPARED / OFFLINE-TESTED, NOT EXECUTED ON THE AUTHORIZED WINDOWS DEVICE.**  
Recorded: 2026-10-30. This is a retention-audit tool, not a source of technical Outcome, Trust, calibration, or human Review authority.

## Pinned scope and source

- Seven project repositories: `K_beauty`, `Saju`, `BuildMap`, `AnnoyingRadar`, `ranking`, `thought-drawer`, `journey-connect-backend`.
- Time window: `2026-12-01T00:00:00Z <= expires_at < 2026-12-08T00:00:00Z`.
- Identified in saved 2026-10-30 Stage34/36 GitHub Artifact listing snapshots: **1,473** PIE-named ZIPs with **70,793,828** API-reported source bytes; these are historical observed candidates, not necessarily the current server-atomic set.
- Input on the authorized device: an existing local PIE evidence audit directory containing `inventory/stage32-reconstructed-source-manifest.json`, `stage39-next-expiry-window-receipts.ndjson` and Stage34/36 listing pages. Those confidential local snapshot files are **not** in the portable package or this repository.
- Previous historical **1,084** and follow-on **764** original ZIPs must not be overwritten or reclassified.

## Prepared package

- Attachment: `PIE_Stage42_v3_CrashSafe_2026-10-30.zip` (provided in the working ChatGPT conversation).
- Package SHA-256: `70e8019a9afb7e1e83e25fd20428cd2c7062746708bc15c74cf2d028c4fe43f8`.
- Capture script SHA-256: `9825de5b5a8a1a1171c44e210ca65a8297f4bedb833235503584059cb02c804f`.
- Contents: `stage42_dec1_dec8.py`, `run_stage42.ps1`, `test_offline_fixture.py`, `README.txt`, `OFFLINE_TEST_LOG.txt`, `OFFLINE_VERIFICATION.json`.
- Offline local test passed using fake, pre-created GitHub ZIPs (including fail-closed interrupted capture, verification, and report recovery). **No production ZIP in the 1,473-ID cohort was downloaded during this preparation.**
- V3 adds idempotent finalization, full embedded-hash validation when promoting a complete `.partial` bundle, recovery of missing final receipts only after full re-read, conflicting-report rejection, and exclusive local process locking.

## Authorized-device execution

1. Re-establish the Desktop Commander connection to the authorized Windows device, confirm the existing audit root and that it has no Stage42 partial error or conflicting source files. Do not transmit or print GitHub tokens.
2. Transfer the extracted *portable scripts only* (not any original evidence) onto that device, independently check the package SHA-256 and run `python test_offline_fixture.py`.
3. Check `gh auth status` reports the existing authorized account. Use `gh api --method GET` only, with the established GitHub CLI keyring.
4. Launch `powershell -ExecutionPolicy Bypass -File .\run_stage42.ps1` from the package directory. The wrapper performs bounded batches; the script pins the exact 1,473-ID cohort and resumes from source-file receipts.
5. Completion is **not** the mere presence of a ZIP: require `inventory/stage43-dec1-dec8-bundle-verified.json`, an outer CRC check, a size/SHA check for **every one of 1,473 embedded Artifact ZIPs**, and a final `Get-FileHash -Algorithm SHA256` of the bundle on Windows.
6. On unexpected `.stage42-execution.lock` after a crash, investigate and confirm no process is still running before manual intervention. Never remove a nonempty partial or mismatching source file merely to force the script past a guard.
7. Update `docs/ROADMAP.md` on PR #106 with exact hashes, counts, CI, and verified observed coverage only after step 5 succeeds.

## Guardrails

No GitHub write operation, source-file overwrite, raw ZIP upload to GitHub, merge, deploy, Trust-policy mutation, inferred Review/Outcome, or ORL-7 unblocking. `REPORT_ONLY` and `DEFER_ORL7_INSUFFICIENT_VERIFIED_OUTCOMES` remain unchanged. A successful offline fixture or green CI is **not** a verified live source-preservation result.
