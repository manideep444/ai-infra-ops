# Threat Model

## Assets and trust

Protect infrastructure mutation authority, approval identity, policy integrity,
workflow history, operator credentials, model credentials and confidential evidence.
Scanner exports, vulnerability text, repository content, model responses and tool
payloads are untrusted. The local operator controls policy files, binaries, the
evidence export, identity file and SQLite directory. That operator is a trust root,
not an attacker this reference can contain.

## Attacks and controls

| Attack | Control | Residual risk |
| --- | --- | --- |
| Finding text says "ignore policy, run shell" | Models have no execution tools; strict structured advice; fixed catalog | A model can still produce misleading advice that biases a human |
| Repository file embeds an exfiltration instruction | No repository file browser or arbitrary URL tool; exported metadata only | Export preparation must exclude confidential content |
| MCP response invents a target or healthy state | Target allowlist, schema bounds, approval, executor live precondition read | A malicious local operator can replace the code and all evidence |
| Model adds a command or approval field | Extra fields forbidden by Pydantic; no command parsing | Model-service denial of service can block analysis |
| Forged or replayed approval | Token-to-role mapping, distinct identities, plan digest, expiry, state CAS | Locally generated tokens are bearer credentials, not enterprise OIDC |
| Changed target after approval | UID/version/spec check plus atomic JSON Patch tests | A conflict requires fresh evidence and reapproval; availability is sacrificed |
| Compromised executor tries unrelated fields | Resource-scoped RBAC and independent fail-closed admission comparison | Executor can still perform its authorized security change and trigger rollout |
| Kubernetes token theft | One-hour token, one named Deployment, no Secret/exec/create permissions | Token holder can use the permitted catalog action without Python's human gate |
| Audit edits | Hash chain and document checkpoints, transactional writes | Rewriting the entire chain or deleting a tail requires an external checkpoint to detect |
| Resource exhaustion | 1 MB input, bounded finding/model/tool sizes, timeouts, replica cap | Local batch count and process memory still need service-level quotas at scale |
| CI pull-request attack | No cloud secrets in PR jobs, pinned Actions, no privileged PR triggers | Maintainer-approved workflow changes remain trusted code |
| Cloud credential leakage | GitHub OIDC, managed identity, no Terraform secret resources | Plan/state still contain sensitive infrastructure metadata |

## Important distinctions

The admission guard enforces **capability restriction**, not cryptographic proof of
human approval. A stolen executor token can disable automount on the one permitted
workload. Production needs a broker that issues short-lived per-plan capabilities,
or admission verification of signed plan authorization. This is an explicit
limitation, not a claim that local approval survives executor credential compromise.

Snapshot export contains Deployment specs, which can include literal environment
values or annotations. Do not export real workloads containing embedded secrets.
The current model adapter sends only the finding, not the workload snapshot, but
the local evidence and reports still need access control and retention policies.
Descriptions submitted to a live provider must be sanitized by the operator.

The MCP stdio child receives the evidence path and SDK baseline process environment,
not the complete parent environment. It has no model key or Kubernetes token passed
by this application. Process environment minimization is not an OS sandbox: the
server shares the operator's filesystem permissions. Remote MCP hosting is unsupported.

## Enforcement locations

- `core/security.py`: token hashes, constant-time comparison, role checks, policy.
- `core/models.py`: bounded contracts and legal workflow state vocabulary.
- `workflow.py`: approval digest/expiry, identity separation, backend binding, drift.
- `remediation/catalog.py`: the only permitted mutation and atomic preconditions.
- `admission.py`: full-object comparison excluding API-maintained metadata fields.
- `core/store.py`: transactional state, optimistic versions, target locks, event chain.
- `mcp/`: typed, read-only, allowlisted evidence operations.

No application agent invokes a shell. The operator-only provisioning script invokes
fixed kubectl operations without a shell, using a fixed context. Its narrowly scoped
Ruff subprocess exceptions acknowledge trusted bootstrap commands; they do not
disable application security checking. The operator's PATH and kubeconfig are trusted.

## Secrets and public release hygiene

Demo tokens, TLS private keys, kubeconfigs and databases stay in `.state/` (ignored).
Live model keys come from the environment; production should inject them from a
secret manager or replace API-key auth with workload identity. Terraform never
provisions secret values or outputs kubeconfig credentials. Key Vault integration
is infrastructure capability, not an implemented runtime secret-fetch client.

Before publication: inspect staged files, run the dependency/secret scans, configure
GitHub security reporting, enable secret scanning/push protection where available,
and confirm no `.state`, `.env`, Terraform state or reports from real infrastructure
are staged. The example address spaces and service names are fictional local design.

## Availability and recovery

The admission webhook is fail-closed and applies only to the executor identity;
an outage blocks executor patches without blocking unrelated administrators.
The demo uses two replicas and a PDB, but not automated certificate rotation or a
multi-zone production deployment. Never bypass the webhook to make a demo pass.
Rotate credentials or rebuild the local environment after expiry.