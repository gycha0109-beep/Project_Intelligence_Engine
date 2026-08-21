# TRUST Workflow Diff Semantics Contract — D1 Remediation Foundation

## 1. Authority

- PIE authoritative main: `96b053f63a25465a4e75e58d755a62462b20ee68`
- Wave 1A corpus/label freeze: `c599f53f12bb9e8218b472752b3a8039f48413fb`
- Wave 1B seen baseline: `02c44376484c7f471307bf6470de8078d9e62492`
- D1: `WORKFLOW_BLANKET_R3_OVERCLASSIFICATION`
- Frozen holdout replay: **0**
- Trust classifier mutation in this change: **0**

This change does not lower `.github/workflows/**` from R3 and does not modify
`trust.py`, the Trust request schema, review-pack selection, project profiles,
automation authorization, pilot authorization, or Stage10K authority.

## 2. Problem

Wave 1B reproduced one high-confidence unacceptable mismatch:

- RankingWiki PR #54 human prior: `R2`
- current PIE: `R3`
- cause: `.github/workflows/ci.yml` receives the unconditional workflow
  `HIGH_RISK_PATH` R3 floor.
- observed workflow delta: one additional verification command only.

The same path class also contains materially different changes:

- K_beauty PR #269 adds `statuses: write` and performs a mutating commit-status
  API request.
- K_beauty PR #275 creates a workflow containing `statuses: write`.

Therefore changing all workflow paths from R3 to R2 would trade one false
positive for security/control-plane false negatives.

## 3. Contract

`review_system.workflow_semantics.analyze_workflow_patch(path, patch)` reduces a
single GitHub Actions patch into one deterministic class:

### `CI_TEST_WIRING_ONLY`

Emitted only when every changed YAML line is a test/verify/lint/check/build
`name` or `run` line and no authority signal is present.

This class is intentionally narrow. It is the only class that may later justify
removing the blanket workflow R3 path floor.

### `AUTHORITY_MUTATION`

Emitted when changed lines contain at least one explicit authority signal:

- GitHub Actions write permission or `permissions: write-all`
- `${{ secrets.* }}` reference
- mutating `gh api` / `curl` request using POST, PUT, PATCH, or DELETE
- recognized deployment/release/publish command

Both additions and removals are authority mutations because either direction
changes operational authority.

### `UNKNOWN`

Emitted for every workflow delta that is neither proven test-only nor proven
authority mutation.

`UNKNOWN` is fail-safe. Future Trust integration must retain R3 for this class
unless a separately reviewed semantic rule proves a lower band.

## 4. Evidence binding

The reducer emits:

- normalized workflow path
- SHA-256 of the exact supplied patch
- semantic classification
- reason IDs
- matched authority lines and change direction
- changed-line count

PIE already collects the full PR patch and its SHA-256 during `analyze-pr`.
This contract deliberately stops before Trust ingestion. The next bridge must
bind per-workflow semantic evidence to the already captured PR diff authority;
a caller-provided semantic label is not sufficient.

## 5. Seen regression cases

| Case | Observed semantic delta | Contract |
|---|---|---|
| RW-54 | adds `npm run verify:ia-1` only | `CI_TEST_WIRING_ONLY` |
| KB-269 | adds `statuses: write` and status POST | `AUTHORITY_MUTATION` |
| KB-275 | new workflow includes `statuses: write` | `AUTHORITY_MUTATION` |

The fixture is intentionally drawn only from already-seen Wave 1 examples.
No `FROZEN_UNREPLAYED` sample is opened by this change.

## 6. Non-goals

This change does **not**:

- change effective risk bands
- alter `.github/workflows/**` path classification
- modify R4 policy/verifier inference
- fix the generic `policy` token collision
- add project-specific MasterV/AnnoyingRadar semantics
- replay holdout data
- merge PR #40 or PR #41

## 7. Next bounded step

After this contract passes CI, the next implementation candidate is a
hash-bound bridge from collected PR diff evidence to Trust risk projection:

1. derive per-workflow patch semantic evidence from the collected diff;
2. bind it to the source diff SHA-256 and exact PR head;
3. allow only `CI_TEST_WIRING_ONLY` to neutralize the blanket workflow R3
   floor;
4. keep `AUTHORITY_MUTATION` and `UNKNOWN` at R3;
5. replay seen baseline before opening any frozen holdout.

That bridge is a separate policy-sensitive change and is not authorized by this
contract implementation alone.
