# False-positive guards

Reject or downgrade a candidate when:

- the path is unreachable in the configured scope,
- a verified control already prevents the impact,
- the behavior is explicitly required and accepted,
- the finding depends on an unsupported runtime assumption,
- only style preference remains after impact analysis,
- the issue exists solely in excluded or generated files.
