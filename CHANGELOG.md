# Changelog

## 0.3.0 - 2026-07-20

- Added `pie init-project` presets for Bejewely, BuildMap, Journey Connect, and generic web applications.
- Added `pie github-doctor` for GitHub CLI installation, authentication, and repository-context checks.
- Added `pie analyze-pr` accepting a PR number or HTTPS PR URL.
- Added read-only collection of PR metadata, changed files, commits, CI checks, issue comments, reviews, inline review comments, and patch diff.
- Added local/remote repository mismatch blocking and local-HEAD/PR-head warnings.
- Added tamper-evident `github-source.json` and `pie validate-github-source`.
- Added non-destructive project bootstrap behavior and explicit `--force` overwrite control.
- Added GitHub connector, bootstrap, security, failure-path, and end-to-end regression tests; full suite 79/79 PASS.

## 0.2.0 - 2026-07-20

- Added project graph indexing and hash validation.
- Added structural and approved-rule change impact analysis.
- Added parallel change-set comparison.
- Added co-change candidate discovery with explicit human approval.
- Added candidate decision preservation and locked pair writes.
- Added Project State capture and Markdown reporting.
- Preserved Universal Review System v0.1.1 commands and contracts.
- Added Bejewely-oriented component and candidate examples.
- Added intelligence and regression tests; full suite 67/67 PASS.

## 0.1.1 — 2026-07-19

### Fixed

- Implemented stack-profile inheritance that was previously documented but not applied.
- Corrected Gate semantics so accepted risks are not counted as open blockers.
- Added an explicit fixed-but-unverified state instead of equating `FIXED` with `RESOLVED`.
- Corrected relative manifest-path verification.
- Changed merged Finding output to a directly reusable array and separated conflicts.
- Replaced unsafe raw-substring Pack routing with token and extension matching.
- Removed duplicated Finding schema content from the Review Run schema.

### Added

- Project-local stack profiles and inherited Pack exclusion.
- Effective-profile export and Pack version lock files.
- Run synchronization from `findings.json`.
- Protected-path SHA-256 snapshot and verification.
- Run-directory validation, directory Gate calculation, final policy locking, and manifest verification.
- Companion review-input preservation and archive-completeness enforcement.
- Explorer candidate, challenge, and verification artifacts.
- Package-asset drift regression testing.
- Stack, Pack, manifest, and protected-pattern path traversal guards.
- Gate-policy structural validation and protected-symlink rejection.
- Protected-file collection scoped directly to configured glob patterns.

### Policy hardening

- P0 must always be configured as blocking.
- P0 findings cannot be accepted as residual risk.
- Accepted risks require owner, reason, and review date.
- E3+ evidence requires an explicit result.
- P0/P1 findings require a verification plan.

## 0.1.0 — 2026-07-19

Initial reusable review core, schemas, Review Packs, profiles, CLI, Gate engine, and archive support.
