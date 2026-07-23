# Evidence Policy

| Level | Meaning |
|---|---|
| E0 | Opinion or ungrounded hypothesis |
| E1 | Concrete code, configuration, or documentation evidence |
| E2 | Reachable execution path or data-flow proof |
| E3 | Reproduced by a focused automated or deterministic manual test |
| E4 | Reproduced in the real technology stack or representative runtime |
| E5 | Fix applied and full required regression evidence passed |

Rules:

- `HYPOTHESIS` may use E0–E1.
- `SUPPORTED` requires E2 or stronger.
- `CONFIRMED` requires E3 or stronger.
- `RESOLVED` requires E5.
- A P0/P1 blocker normally requires `CONFIRMED`.
- A security finding may be held as `SUPPORTED` only when the attack path is explicit and delay would create unacceptable exposure.
- Evidence must be attributable to a file, symbol, command, log, test, query result, or immutable artifact.
