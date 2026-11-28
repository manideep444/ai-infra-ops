# Operating Runbook

## CI dependency and container maintenance

Keep dependency updates within the supported major-version ranges and commit the
updated `uv.lock`. Run `make check` and `make scan` before publishing changes.
Provider major-version migrations require compatibility work; do not merge them
just to clear a dependency update PR. MCP remains on the stable 1.x SDK contract.

The container uses digest-pinned Python 3.15 on Alpine, with OS security updates
applied in a shared base stage so the builder and runtime use the same libraries.
This replaces the Debian base whose unresolved high/critical findings blocked
the scan. OS updates are resolved at build time, so the base digest alone does not
make builds byte-for-byte reproducible. Refresh the digest regularly and rerun
the container scan, read-only fixture smoke test, and real kind integration gate.
Do not suppress findings or bypass admission to make CI pass.
The runtime contains neither pip nor its ensurepip bootstrap bundle; their
vendored build-time dependencies are unnecessary for running the installed app.
Dependency installation belongs in the builder stage, not in a running container.

CI tests Python 3.12, 3.13, 3.14 and 3.15; the package minimum and lint/type-check
targets remain 3.12. CI and image builds use uv 0.13.10 so managed Python 3.15 is a
final release rather than the release candidate in older uv download catalogs.
Kubernetes client 37 uses its typed Deployment patch API with explicit JSON Patch
content type; dry-run, atomic drift preconditions and admission restrictions remain
covered by the real kind gate. Its kubeconfig loader is still untyped upstream,
so that single call has a narrow mypy exception.

The observability CI job validates the Prometheus and Collector configurations,
starts the Compose stack, checks Grafana dashboard provisioning and OTLP ingestion,
and requires Prometheus to scrape a fictional node-exporter textfile metric.

Admission handles the API server's `/validate?timeout=...` requests by routing on
the URL path. Policy denials return an AdmissionReview with status code 403;
transport failures must not be mistaken for a successful policy denial. The kind
test includes API response bodies in failed assertions to distinguish these cases.

## Local identities

`make setup` creates private local demo token files. The demo command reads them
internally without printing them. For separate CLI invocations, set `AIRP_TOKEN`
from the appropriate private file in your shell. Do not paste tokens into tickets,
chat, command output or GitHub. `jq` below reads locally; tokens are not printed.

```bash
export AIRP_TOKEN="$(jq -r .token .state/planner.token.json)"
uv run airp plan demo/findings.json
```

Inspect the resulting plan JSON and its `run_id` and `plan_digest`. The `inspect`
command displays the same digest and the entire persisted plan for later review:

```bash
export RUN_ID=<run-id-from-plan>
uv run airp inspect "$RUN_ID"
```

Use this digest only after inspecting the entire plan, including target, backend,
expiry and before/expected specs.

```bash
export AIRP_TOKEN="$(jq -r .token .state/approver.token.json)"
uv run airp approve "$RUN_ID" --digest <reviewed-plan-digest>
export AIRP_TOKEN="$(jq -r .token .state/executor.token.json)"
uv run airp execute "$RUN_ID"
uv run airp execute "$RUN_ID" --apply
uv run airp report "$RUN_ID"
uv run airp verify-audit
unset AIRP_TOKEN
```

The default `execute` is dry-run. Approval does not imply immediate execution, and
the target must still match its original UID, resource version and spec. Never
edit a persisted plan to resolve drift; export fresh evidence and create a new run.

## Export live local evidence

Provision kind first. The observer kubeconfig contains only read permission:

```bash
export AIRP_BACKEND=kubernetes
export AIRP_EVIDENCE_FILE=.state/evidence.json
export AIRP_TOKEN="$(jq -r .token .state/planner.token.json)"
AIRP_KUBECONFIG=.state/observer.kubeconfig uv run airp snapshot
uv run airp plan demo/findings.json
```

Planning uses the exported backend fingerprint and does not construct a Kubernetes
client. Execute later with the executor kubeconfig and executor identity. For local
token refresh, run `uv run python scripts/provision-kind.py --credentials-only`;
this requires the trusted kind administrator context and never prints tokens.

## Scanner exports

```bash
uv run airp plan path/to/codeql.sarif --format sarif
uv run airp plan path/to/dependabot-alerts.json --format dependabot
uv run airp plan path/to/trivy.json --format trivy
```

Dependabot expects an array of alert objects with `security_advisory` and `dependency`.
SARIF consumes `runs[].results[]`; Trivy consumes `Results[].Vulnerabilities[]`.
These paths are operator-selected local imports, not model-selected filesystem tools.
Inputs are bounded; identical duplicate findings deduplicate, conflicting IDs fail.
Source exports do not automatically become trusted Kubernetes targets.

## Interrupted execution

1. Stop new executor invocations for the target. Preserve the DB and external checkpoint.
2. Inspect the Kubernetes Deployment, rollout status, recent events and persisted plan.
3. For a run still `executing`, use `airp reconcile <run-id>` with the executor role.
4. Reconciliation observes only. If the expected state is healthy, it can verify success.
5. A missing patch, unhealthy rollout or unexplained drift becomes `needs_intervention`.

Intervention states retain their target lock. There is intentionally no one-command
unlock/rollback. On the disposable local demo, archive evidence and rebuild the
environment using a fresh state directory. Production would require a separately
authorized incident-resolution workflow before retiring a lock. Do not delete a
database row to bypass a stuck approval or conceal a failed outcome.

## State and backup

SQLite uses WAL and `synchronous=FULL`. Back up using SQLite's backup API rather than
copying just the main DB file while a writer runs. Treat the DB, reports and snapshots
as sensitive operational data. Keep identity tokens separate from any shared evidence
archive. Hash checkpoints retained only beside the database are not independent proof.
There is no HA/failover or point-in-time recovery service in this reference.

## Fresh fixture demo without losing evidence

```bash
AIRP_STATE_DIR=.state/another-run uv run airp init-demo
AIRP_STATE_DIR=.state/another-run uv run airp demo
```

Never automatically restore the insecure fixture during normal execution. The
explicit fresh-state command makes demonstration resets distinguishable from repairs.

## Observability and SLIs

Audit outcomes are durable. Logs and spans correlate run IDs; Prometheus labels use
only bounded agent/state/outcome values. The textfile exporter mounts only
`.state/telemetry`, not tokens, reports or the database. It runs as root with all
capabilities dropped solely to read owner-only generated snapshots; this is a local
demo choice, not a production exporter deployment pattern.

The CLI snapshot resets each invocation. Dashboard titles reflect that limitation.
For an operational service, derive these SLIs from durable events over a defined window:

- Verified remediation ratio: verified executions / all attempted executions.
- Safe-stop ratio: unsafe or uncertain outcomes correctly stopped / injected unsafe cases.
- Decision latency: collection-to-plan duration, excluding human approval wait.
- Execution latency: execution intent-to-validated-terminal-state duration.
- Evidence completeness: terminal runs with required checks and verifiable audit linkage.

No numerical production SLO is asserted without workload data. Separate approval
waiting from system latency. Alert on intervention, stale evidence, missing audit
writes and admission unavailability; do not page merely because a finding is manual.