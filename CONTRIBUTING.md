# Contributing

Start with `make setup` and `make check`. Do not include `.state`, credentials,
employer material or real operational data in a contribution.

New remediation actions need all of the following in the same review:

- A typed action schema and narrow target/field authority.
- Policy and admission enforcement that cannot be changed by model output.
- A plan-bound approval and explicit drift preconditions.
- Independent original-finding, health and regression validation.
- Tests for denied approval, partial failure, interruption, drift and replay.
- A recovery procedure, blast-radius explanation and updated threat model.

Avoid adding LLM wrappers where deterministic code is more reliable. Never broaden
executor permissions merely to simplify an implementation. A manual outcome is
preferable to an unsupported automated fix.

Pull requests should state what was executed locally and what requires CI/cluster
verification. Follow the existing locked dependency, Ruff and strict mypy conventions.
The project is a fictional reference architecture; do not imply employer provenance.