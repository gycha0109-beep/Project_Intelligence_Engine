# Stage 10G Implementation Review

## 1. Review target

Stage 10G adds an R0 pilot eligibility evidence-package inventory and dispatch layer on top of the already implemented Stage 10E authority-aware pilot safety review.

Review goals:

- do not manufacture evidence to satisfy thresholds
- distinguish implementation PASS from evidence eligibility
- preserve all prior source-replay authority
- make missing evidence a valid fail-closed result
- prevent a self-contained eligible report from being treated as authority without exact replay
- preserve non-authorization invariants

## 2. Review findings and fixes

### Finding 1 — committed evidence absence was initially easy to overstate

The Stage 10G start tree contains no committed R0 Trust evidence package, but `.pie/` and `.review-runs/` are gitignored.

Risk:

- incorrectly claiming that no runtime evidence exists anywhere
- conflating Git repository contents with local/operator-retained runtime evidence

Fix:

The contract and documentation distinguish:

```text
COMMITTED_R0_EVIDENCE_PACKAGE_PRESENT = NO
```

from the stronger and unsupported claim:

```text
NO_RUNTIME_EVIDENCE_EXISTS_ANYWHERE
```

Only the former is asserted.

### Finding 2 — sample/test evidence must never be auto-promoted

The repository contains a sample observation policy and extensive fixtures capable of constructing synthetic Trust evidence.

Risk:

- using those inputs to make the production/pilot evidence gate appear satisfied

Fix:

Stage 10G never scans tests/examples for replacement evidence and never synthesizes missing files. It only inventories the explicitly supplied evidence root.

The canonical operational convention is:

```text
.pie/r0-pilot-evidence/
```

### Finding 3 — missing evidence must not become an execution error

A pilot-readiness evidence gap is an expected governance result, not malformed software execution.

Fix:

An incomplete package returns a valid report:

```text
status=NOT_ELIGIBLE
source_replay.attempted=false
pilot_review.attempted=false
next_step=PROVIDE_COMPLETE_R0_EVIDENCE_PACKAGE
```

CLI exit remains success for this valid report.

### Finding 4 — path safety cannot be inferred later from a self-contained report

A report can store hashes and presence, but it cannot later prove whether an original local path was a symlink.

Fix:

- symlinked evidence root: reject as unsafe input
- required file that is missing, symlinked, broken, or non-regular: do not accept as usable evidence
- report projection normalizes unusable required input as missing evidence
- exact replay rechecks current filesystem sources

This avoids storing false path-safety claims in a portable report.

### Finding 5 — self-contained eligible verification was too weak as an authority boundary

A report's hashes/projections can prove internal consistency, but a self-contained report alone cannot prove that the recorded source-replay booleans correspond to the current evidence bytes.

Risk:

- treating a semantically reconstructed eligible report as current authority without replay

Fix:

`verify-r0-pilot-evidence-run` requires `--evidence-root` whenever the report status is:

```text
ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

The CLI then reruns the exact package.

Self-contained verification remains useful for `NOT_ELIGIBLE` report integrity but is not an eligible authorization-review authority.

### Finding 6 — Stage 10G must not duplicate Stage 10E safety logic

Duplicating the Stage 10E checks would create two independently drifting pilot eligibility implementations.

Fix:

A complete package is passed to the existing Stage 10E authority-aware `review_r0_pilot` boundary.

Stage 10G only projects:

- Stage 10E review ID/hash/status
- Stage 10E blockers/next step
- source-replay verification state

### Finding 7 — top-level and nested source mutation need separate coverage

Top-level package files are directly hashed by Stage 10G. Nested evidence is referenced from the Stage 10C manifest.

Fix:

- top-level mutation changes Stage 10G inventory SHA and breaks exact report replay
- nested Trust/Audit/Defect/Evaluation/source mutation is detected by Stage 10C/Stage 10E source replay

Stage 10G does not flatten or duplicate all nested hashes.

### Finding 8 — evidence identity must not depend on report generation time

Fix:

`generated_at` is excluded from the evidence snapshot and `run_id` natural key, while remaining part of the outer report hash.

### Finding 9 — eligibility must remain non-authorizing

Schema and semantic verifier require:

```text
mode=REPORT_ONLY
target_band=R0
automation_authorized=false
pilot_authorized=false
```

Even an eligible result only sets:

```text
next_step=REQUEST_EXPLICIT_HUMAN_PILOT_AUTHORIZATION
```

No activation path was introduced.

## 3. Security properties

Stage 10G directly enforces or composes the following:

- evidence-root symlink rejection
- fixed top-level package filenames
- top-level source SHA-256 inventory
- deterministic inventory ordering
- deterministic evidence snapshot identity
- deterministic run ID
- semantic blocker/status recomputation
- exact evidence-root replay
- Stage 10C nested authority replay
- Stage 10F audit provenance replay
- Stage 10D observation policy/registry replay
- Stage 10E cross-artifact eligibility checks
- output symlink rejection
- atomic write preservation

## 4. Deliberate non-goals

Stage 10G does not:

- discover evidence from arbitrary folders
- copy tests/examples into an evidence package
- issue Independent Audit artifacts
- create Trust Root or issuer authority
- record human decisions or Outcomes
- relax Stage 10D thresholds
- convert `NOT_ELIGIBLE` into a failed CI merely to force progress
- authorize or activate a pilot
- merge/approve/comment/label through GitHub

## 5. Trust-model limit

A complete and internally valid evidence package can still be deliberately constructed by an operator. Stage 10G proves conformance to the repository's evidence authority chain, not external physical-world truth.

Stronger claims would require additional authority such as externally verifiable signatures, independent timestamping, or external observation provenance. Stage 10F explicitly does not claim such PKI/non-repudiation authority.

Therefore the strongest Stage 10G result is intentionally:

```text
ELIGIBLE_FOR_HUMAN_PILOT_AUTHORIZATION_REVIEW
```

not:

```text
PILOT_AUTHORIZED
```

## 6. Review conclusion

The implementation boundary is appropriate for an evidence-acquisition gate because it adds no mechanism to create the evidence needed to pass itself.

Current committed-repository evidence remains insufficient; implementation PASS therefore does not imply current pilot eligibility.
