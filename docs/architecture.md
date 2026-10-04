# Architecture

Status: implementation contract. This is independently designed reference software,
not an employer implementation. All demonstration assets are fictional.

## Scope and ownership

The system accepts normalized findings, SARIF, Dependabot and Trivy exports. It
executes one deliberately narrow catalog action: disable service-account token
automount on the named demo Deployment. Everything else produces a manual plan.
Breadth of ingestion is not breadth of authorized mutation. Dependency, image,
OS and source-code repairs require application-specific compatibility evidence;
we do not pretend a generated patch proves that evidence.

Python agents share a typed package, not seven independently operated services.
The CLI is the local control plane. SQLite transactions persist workflow state and
hash-linked audit events. A separately invoked executor owns Kubernetes credentials.
The reasoning process has no mutation tools. MCP serves bounded, read-only evidence.
The first release is single-host, single-worker, not highly available.

## Overall architecture

```mermaid
flowchart TD
  Inputs[Normalized / SARIF / Dependabot / Trivy] --> Collector[Collector]
  Collector --> State[Durable orchestrator]
  State --> Agents[Triage / Diagnosis / Planner]
  Agents <--> MCP[Read-only MCP]
  Agents --> Policy[Deterministic policy]
  Policy --> Approval[Plan-bound approval]
  Approval --> Executor[Separate executor invocation]
  Executor --> Checks[Health / original detector / regression]
  Checks --> State
  State --> Audit[Hash-linked events and reports]
```

## Agent interaction

```mermaid
sequenceDiagram
  participant O as Orchestrator
  participant T as Triage
  participant D as Diagnostic
  participant R as Remediation
  participant P as Risk/Policy
  participant V as Validation
  participant A as Reporting
  O->>T: Finding + bounded context
  T-->>O: Impact + uncertainty + priority
  O->>D: Finding + read-only evidence
  D-->>O: Diagnosis + target snapshot
  O->>R: Diagnosis + catalog
  R-->>O: Typed proposal
  O->>P: Canonical plan + policy
  P-->>O: Manual or approval required
  Note over O,V: Approval and execution are outside model authority
  O->>V: Before and observed after state
  V-->>O: Required checks + verdict
  O->>A: Persisted workflow and events
  A-->>O: JSON / Markdown evidence
```

## MCP tools

```mermaid
flowchart LR
  Agent[Agent host] --> Client[Official MCP SDK client]
  Client --> Server[stdio evidence server]
  Server --> Guard[Fixed tool names / strict schemas / size limits]
  Guard --> Snapshots[Allowlisted workload snapshots]
  Guard --> Metadata[Public fixture vulnerability and repository metadata]
  Guard --> History[Sanitized audit history and validation results]
  Guard -. no access .-> Denied[Shell / secrets / arbitrary paths / writes]
```

The server process has no Kubernetes credentials. A trusted operator exports a
snapshot or uses the demo fixture. Evidence is advisory: the executor always
re-reads the target from its own backend before mutation. stdio avoids exposing an
unauthenticated network service; remote MCP hosting is not part of this release.

## Security boundary

```mermaid
flowchart TB
  subgraph Untrusted
    Finding[Finding text / repository data / model output]
  end
  subgraph Reasoning
    Parse[Bounded parsing] --> Model[Optional model]
    Model --> Schema[Typed advisory analysis]
  end
  subgraph Trusted_Control
    Policy[Catalog and policy] --> Approval[Digest + actor + expiry]
    Approval --> Precondition[Target UID and resource version]
  end
  subgraph Mutation
    Executor[Executor identity] --> API[Kubernetes API]
    API --> Admission[RBAC + admission field restrictions]
  end
  Finding --> Parse
  Schema --> Policy
  Precondition --> Executor
```

Local actor identities come from a token-to-role file controlled by the operator,
not a request field. That demonstrates authorization, not enterprise federation.
A machine administrator can replace local policy, tokens, database and binaries.
Production requires stronger process isolation, trusted identity, artifact
integrity, externally retained audit checkpoints and separate administrative roles.

## CI/CD

```mermaid
flowchart LR
  PR[Pull request] --> Python[Lint / typing / tests / dependency audit]
  PR --> Security[CodeQL / secret and IaC scan]
  PR --> IaC[Terraform / Bicep / Kubernetes validation]
  PR --> Kind[Real kind integration]
  Python --> Image[Container build / scan / SBOM]
  Security --> Image
  IaC --> Image
  Kind --> Image
  Image --> Review[Protected environment approval]
  Review --> OIDC[Azure OIDC / optional infrastructure deployment]
```

## Kubernetes

```mermaid
flowchart TB
  subgraph Platform_Namespace
    Observer[Read-only evidence exporter]
    Account[Executor ServiceAccount: named Deployment only]
  end
  subgraph Demo_Namespace
    Deployment[Two-replica fictional workload]
    Service[ClusterIP service] --> Deployment
    PDB[Disruption budget] --> Deployment
    Config[ConfigMap / demo Secret] --> Deployment
    Network[Default deny + explicit internal paths]
  end
  Observer -. read .-> Deployment
  Account --> Admission[Admission guard]
  Admission --> Deployment
```

kind uses a NetworkPolicy-capable CNI. Workload token automount is the intentional
misconfiguration; other workload settings stay hardened. The executor cannot
create workloads, exec into containers, read Secrets, or select another target.
Probe health is necessary but not sufficient: validation also compares all
non-catalog fields against the before-state and re-runs the original detector.

## Workflow and recovery

```mermaid
stateDiagram-v2
  [*] --> analyzing
  analyzing --> awaiting_approval
  analyzing --> manual_required
  analyzing --> failed
  awaiting_approval --> approved
  awaiting_approval --> denied
  approved --> executing
  executing --> succeeded
  executing --> failed
  executing --> needs_intervention
```

Dry-run never changes workflow state or target. Approval covers the complete plan,
policy version, actor and expiry. Execution rechecks policy and target UID/version.
Intent is committed before external mutation. Interrupted executing runs are
reconciled, never blindly replayed. Target locks prevent overlapping local writes.
SQLite and Kubernetes cannot share a transaction: exactly-once execution is not
claimed. Unknown outcomes and unsafe recovery require intervention. Automatic
rollback is intentionally absent: rollback can reintroduce a security defect and
requires its own reviewed plan.

## Optional Azure

Terraform owns the resource group, private AKS API, ACR, Key Vault, managed identity,
network and log workspace. Bicep owns an optional monitoring action group only,
inside the Terraform-created resource group. No resource has dual state ownership.
AKS workload identity avoids cloud keys. Private-cluster application deployment
needs a network-connected runner; the hosted OIDC workflow provisions infrastructure
only. Azure is never required for the mock or kind workflows.