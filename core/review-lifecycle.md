# Review Lifecycle

1. **INTAKE** — Lock scope, baseline, prohibited actions, and expected outputs.
2. **BASELINE** — Run current build/test/migration commands before any modification.
3. **MAP** — Reconstruct architecture, data flow, trust boundaries, and transaction boundaries without changing code.
4. **REVIEW** — Execute selected packs independently.
5. **CHALLENGE** — Attempt to disprove or downgrade each proposed finding.
6. **VERIFY** — Reproduce surviving findings using tests, commands, database evidence, or reachable-path proof.
7. **REMEDIATE** — Modify only confirmed or explicitly accepted supported findings.
8. **REGRESSION** — Run baseline and targeted regression evidence after remediation.
9. **GATE** — Calculate an evidence-backed decision.
10. **ARCHIVE** — Store profile, versions, findings, commands, outputs, residual risks, and hashes.
