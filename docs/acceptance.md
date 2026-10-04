# Acceptance and implementation sequence

Each phase must keep the package executable. No unsupported action may produce a
successful remediation result. A finding is verified only if the original rule,
rollout health and non-target-field invariants all pass on freshly observed state.

| Phase | Deliverable | Gate |
| --- | --- | --- |
| 1 | Architecture, ADRs, seven diagrams | Boundaries, recovery and limitations stated |
| 2 | Strict models, config, durable store | Invalid inputs and illegal transitions rejected |
| 3 | Seven agent responsibilities | Typed contracts, provider failure blocks planning |
| 4 | MCP evidence tools | Real SDK transport tests, unknown target/tool denied |
| 5 | Approval and typed execution | Denial, expiry, tampering, stale target, dry-run tests |
| 6 | kind workload and admission | Real mutation, denied extra field, rollout and re-scan |
| 7 | CI and optional cloud | Lint, tests, CodeQL, scans and IaC validation jobs |
| 8 | Logs, metrics, traces | Bounded labels, outcome and duration metrics exercised |
| 9 | Failure scenarios | Unavailable services, crash, unhealthy rollout, regression |
| 10 | README and runbooks | Reproducible commands, examples, limitations, teardown |
| 11 | Readiness review | Findings fixed or explicitly retained as release limitations |

## Safety properties

- Request bodies, model output and scanner text cannot select actor roles.
- Unsupported targets, action names, command strings and arbitrary paths fail closed.
- Every write requires an unexpired approval for exactly the persisted plan.
- Policy changes, target replacement and target drift invalidate execution.
- Dry-run performs no target writes and consumes no approval.
- Concurrent and repeated execution cannot bypass durable state transitions.
- Validation failure and missing evidence never become success.
- Interruption after a write never triggers an automatic second write.
- Reports distinguish manual, denied, failed, intervention and verified outcomes.
- Demo identities and simulation backends are clearly labeled as such.

## Evidence honesty

Local Python checks can run without a cluster. kind, container, Terraform and Azure
claims require their own recorded checks; having a CI file is not evidence it ran.
Security scanners may find newly disclosed issues after publication. Do not hide
findings with blanket ignores, mutable dependencies or misleading badges.