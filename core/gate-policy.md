# Gate Policy

The gate engine is deterministic. Narrative language cannot override a triggered rule.

Default ordering:

1. `FAIL`
2. `HOLD`
3. `CONDITIONAL_PASS`
4. `PASS`

A stronger decision always dominates weaker decisions.
