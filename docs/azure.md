# Optional Azure Deployment

The local demo requires no Azure subscription. This directory documents an optional
infrastructure foundation, not a deployed production service. Terraform validation
does not prove Azure capacity, permissions, networking or regional SKU availability.

## Ownership and cost

Terraform owns the resource group, private AKS cluster, four nodes across separate
system/workload pools, network, private Premium ACR, private Key Vault, private DNS,
managed identities, role assignments and diagnostics. Bicep owns only its action
group and resource-health alert. No resource is co-managed.

The four VMs, AKS Standard tier, Premium registry, private endpoints, load balancer
and log ingestion incur ongoing charges. Use the Azure pricing calculator for your
region before applying. Key Vault purge protection delays name reuse after teardown.
This is deliberately not presented as a free-tier deployment.

## Bootstrap prerequisites

An Azure administrator must prepare the subscription, register the required resource
providers, create an Entra admin group, allocate globally unique resource names and
establish a protected Terraform state account/container. Enable state versioning,
soft-delete, Entra authentication and restricted network access. Hosted runners need
access to that backend; a private backend needs a private-network runner.

Configure two Entra application identities with GitHub federated credentials, scoped
to this exact repository and the `azure-plan` and `azure-apply` environments. Restrict
both environments to `main`; require independent reviewers on `azure-apply` and
disable self-approval. Use environment-specific `AZURE_CLIENT_ID` variables.

Plan identity: infrastructure read access and state blob access sufficient for locking.
Apply identity: resource provisioning and narrowly scoped role-assignment rights.
Do not assign subscription Owner merely to make the example run. An administrator
can precreate/import the resource group and delegate permissions there, keeping
subscription-level bootstrap separate. Terraform role assignments require explicit
authorization beyond ordinary resource Contributor.

Required GitHub variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_PREFIX`, `AZURE_ADMIN_GROUP_IDS_JSON`,
`TF_STATE_RESOURCE_GROUP`, `TF_STATE_STORAGE_ACCOUNT`. None are client secrets.
The admin group variable is a JSON array of Entra object IDs.

## Plan and apply

Local validation is credential-free:

```bash
terraform -chdir=terraform/azure init -backend=false
terraform -chdir=terraform/azure validate
az bicep build --file bicep/monitoring.bicep
```

Use the optional workflow with `apply=false` first. Review the Terraform plan, then
run with apply enabled and review the new saved plan before approving the apply job.
The apply job consumes the same-run artifact, not a newly calculated plan. It cannot
run from a PR or another branch.

**Plan artifacts can contain sensitive values and topology.** This reference creates
no secret values, but a public repository's plan artifacts/logs still expose its
infrastructure metadata. Do not enable this workflow for confidential infrastructure.
Use a private deployment repository or an access-controlled plan store before adding
secrets or real organizational infrastructure. One-day artifact retention is not a
confidentiality boundary.

## Application deployment boundary

AKS and ACR use private endpoints. Publishing images or talking to the Kubernetes API
requires a network-connected operator/runner. This reference workflow provisions
infrastructure only. It does not bypass the private API with public admin credentials.

To deploy the local components as a starting point, build and scan the image, push
to the private registry from a connected runner, replace `airp:local` with a pinned
registry digest and remove `imagePullPolicy: Never`. Replace local TLS generation
with managed certificate rotation and install the admission guard before granting
executor permissions. Do not deploy intentionally misconfigured fixtures to production.

The observer identity has a federated Kubernetes subject but no cloud data-access
role by default. Annotate the matching service account and grant only a demonstrated
required scope when adding Azure evidence integrations. Key Vault CSI support is
enabled, but application secret retrieval and Entra model authentication are not
implemented runtime features in this release.

## Bicep monitoring

After Terraform deployment, supply the real cluster resource ID and an operator
notification destination:

```bash
az deployment group create --resource-group "$RESOURCE_GROUP" \
  --template-file bicep/monitoring.bicep \
  --parameters clusterResourceId="$CLUSTER_ID" notificationEmail="$OPERATIONS_EMAIL"
```

The alert targets AKS resource health, not individual remediation outcomes. Those
remain application telemetry. Test notification routing before treating it as on-call coverage.

## Production gaps and teardown

Outbound traffic uses the load balancer, not an egress firewall. Add egress restrictions,
private model endpoints, zone-aware capacity, backups, enterprise identity, policy
automation and measured SLOs before production. The example does not claim an
enterprise landing zone, HA control plane for the application or verified disaster recovery.

Destroy only through the same reviewed Terraform state. The optional Bicep resources
reside inside the Terraform resource group, so deleting that group also removes them;
coordinate owners first. Retain audit evidence separately. There is no scheduled
automatic destroy that might surprise an operator.