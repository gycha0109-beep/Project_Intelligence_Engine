# PIE Intelligence Configuration

- `config.yml`: project components used by the knowledge graph.
- `approved-rules.yml`: human-approved project rules used during impact analysis.
- `candidate-rules.yml`: automatically discovered rules awaiting human approval.
- `graph.json`: generated locally by `pie index-project` or `pie analyze-pr`.

Do not place GitHub tokens in this directory. PIE reuses the authenticated GitHub CLI session.
