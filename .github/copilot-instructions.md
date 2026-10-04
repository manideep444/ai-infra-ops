# Repository engineering constraints

- This is independently designed public reference software. Use fictional or public
  data only; never introduce employer-derived systems, prompts, credentials or details.
- Model output is advisory. Never add arbitrary shell, filesystem or network tools
  to an agent or broaden mutation authority without policy, admission and failure tests.
- Read `docs/architecture.md`, `docs/security.md` and `docs/decisions.md` before
  changing execution or authorization behavior.
- Use strict Pydantic contracts and typed interfaces. Preserve fail-closed outcomes,
  plan-bound approval, drift checks and independent validation.
- Run `make check`; infrastructure changes also require schema validation and the
  real kind integration gate. Do not claim a check ran if the environment lacked it.
- MCP uses the official Python SDK, pinned to its stable 1.x API in the lockfile.
  References: https://github.com/modelcontextprotocol/python-sdk/tree/v1.x and
  https://modelcontextprotocol.io/specification/latest . Review API compatibility
  before changing major SDK versions; do not copy examples for another major.