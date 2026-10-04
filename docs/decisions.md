# Architecture decisions

| Decision | Rationale | Cost / reconsider when |
| --- | --- | --- |
| Typed action catalog, not generated shell | Model output cannot expand authority | Each new action needs its own safety case and tests |
| One real Kubernetes action | Prove approval, drift and verification deeply | Broader repairs need workload-specific test evidence |
| Structured LLM advice, deterministic decisions | Prompt injection cannot grant capabilities | Models cannot invent executable repairs |
| Real MCP over stdio | Protocol interoperability without a public endpoint | Remote service needs transport authentication and tenant authorization |
| Snapshot MCP evidence | No infrastructure credentials in the model process | Freshness enforced separately at execution |
| SQLite, one worker | Runnable locally, transactional state and evidence | Multi-worker requires durable queue, leases, PostgreSQL and fencing |
| Manual approval for every mutation | No surprising default writes | Auto-approval requires measured action-specific reliability |
| No automatic rollback | Reverse mutations can be unsafe or conflict with operators | Add reversible actions with explicit compensation policy |
| Mock is a provider, fixture is a backend | Demonstrates offline analysis without disguising simulated infrastructure | Real kind validation remains a separate required CI job |
| Separate executor invocation | Separates credentials from analysis | Local processes share an administrative trust domain |
| Hash-linked events, not immutable claims | Detect accidental edits and tampering against checkpoints | External retention required to resist database administrator rewrite |
| Terraform plus narrowly owned Bicep | Demonstrate both without duplicate resource ownership | Remove Bicep if optional alerting is not needed |

## Production admission criteria

This reference is not approved for unattended production use. Before that: trusted
OIDC identity and approval separation, signed executor images and plans, external
audit retention, highly available durable scheduling, environment-specific admission
policies, backup/restore drills, rate/budget limits, and representative load/failure
testing. An LLM confidence score is never a substitute for these controls.