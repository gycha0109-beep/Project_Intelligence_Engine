# PIE Stage 10H — Validation

## Validation objective

Validate the acquisition boundary independently from whether genuine runtime evidence is currently available.

## Focused regression

Tests cover:

- missing required workspace inputs -> valid `BLOCKED_MISSING_INPUT`,
- missing manifest source closure -> valid `BLOCKED_MISSING_SOURCE_CLOSURE`,
- complete workspace -> `READY_TO_POPULATE` only,
- invalid/sample acquisition attestation rejection,
- symlinked source closure rejection,
- existing package target rejection,
- verified Stage 10G `NOT_ELIGIBLE` result may still publish a truthful package,
- Stage 10G source replay failure prevents package publication,
- report finalization failure leaves no published target,
- published package byte mutation is detected,
- semantic rehash cannot set `pilot_authorized=true`,
- standalone and delegated CLI command registration.

## Full regression

Terminal validation requires the repository CI matrix on the documentation-inclusive exact Stage 10H head:

```text
Python 3.11
Python 3.13
Python 3.14
```

Each matrix job must complete:

- editable package installation,
- package asset synchronization,
- full unittest discovery,
- existing `urs` version/profile/Finding validation,
- wheel build.

Root/package copies of both Stage 10H schemas must be byte-identical.

## Runtime evidence validation

A real Stage 10H runtime execution additionally requires a genuine acquisition workspace.

No such workspace was available through the connected GitHub repository, GitHub Actions artifact, or issue surfaces during implementation. Therefore implementation CI cannot be substituted for runtime acquisition evidence.

Current external state:

```text
RUNTIME_ACQUISITION=BLOCKED_EXTERNAL_EVIDENCE_REQUIRED
```

When a genuine workspace is supplied, validation sequence is:

1. `inspect-r0-evidence-acquisition`,
2. resolve any missing source-closure blockers,
3. `populate-r0-evidence-package`,
4. verify the Stage 10H acquisition report against workspace and package,
5. verify Stage 10G exact replay result,
6. preserve the resulting eligibility status without relaxation or synthetic substitution.

## Success interpretation

Stage 10H implementation PASS means the acquisition mechanism is ready for real inputs.

It does not mean:

- sufficient R0 cases exist,
- observations meet thresholds,
- independent audits exist,
- Stage 10G reached eligibility,
- pilot activation is authorized.

Those are runtime evidence facts and remain fail-closed until actually demonstrated.
