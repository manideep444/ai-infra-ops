data "azurerm_client_config" "current" {}

locals {
  tags = { project = "ai-infra-ops", environment = "reference", managed_by = "terraform" }
}

resource "azurerm_resource_group" "platform" {
  name     = "${var.name}-rg"
  location = var.location
  tags     = local.tags
}

resource "azurerm_virtual_network" "platform" {
  name                = "${var.name}-vnet"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  address_space       = ["10.80.0.0/16"]
  tags                = local.tags
}

resource "azurerm_subnet" "aks" {
  name                 = "aks"
  resource_group_name  = azurerm_resource_group.platform.name
  virtual_network_name = azurerm_virtual_network.platform.name
  address_prefixes     = ["10.80.0.0/20"]
}

resource "azurerm_subnet" "endpoints" {
  name                 = "private-endpoints"
  resource_group_name  = azurerm_resource_group.platform.name
  virtual_network_name = azurerm_virtual_network.platform.name
  address_prefixes     = ["10.80.16.0/24"]
}

resource "azurerm_log_analytics_workspace" "platform" {
  name                = "${var.name}-logs"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_registry" "platform" {
  name                          = "${var.name}acr"
  resource_group_name           = azurerm_resource_group.platform.name
  location                      = var.location
  sku                           = "Premium"
  admin_enabled                 = false
  public_network_access_enabled = false
  tags                          = local.tags
}

resource "azurerm_key_vault" "platform" {
  name                          = "${var.name}-kv"
  resource_group_name           = azurerm_resource_group.platform.name
  location                      = var.location
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 7
  public_network_access_enabled = false
  network_acls {
    bypass         = "AzureServices"
    default_action = "Deny"
  }
  tags = local.tags
}

resource "azurerm_user_assigned_identity" "cluster" {
  name                = "${var.name}-cluster"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.tags
}

resource "azurerm_role_assignment" "network" {
  scope                = azurerm_subnet.aks.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.cluster.principal_id
}

resource "azurerm_kubernetes_cluster" "platform" {
  name                                = "${var.name}-aks"
  location                            = var.location
  resource_group_name                 = azurerm_resource_group.platform.name
  dns_prefix                          = var.name
  private_cluster_enabled             = true
  private_cluster_public_fqdn_enabled = false
  local_account_disabled              = true
  role_based_access_control_enabled   = true
  oidc_issuer_enabled                 = true
  workload_identity_enabled           = true
  azure_policy_enabled                = true
  sku_tier                            = "Standard"
  automatic_upgrade_channel           = "patch"
  node_os_upgrade_channel             = "NodeImage"
  default_node_pool {
    name                         = "system"
    node_count                   = 2
    vm_size                      = "Standard_D2s_v5"
    vnet_subnet_id               = azurerm_subnet.aks.id
    only_critical_addons_enabled = true
    upgrade_settings {
      max_surge = "1"
    }
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.cluster.id]
  }
  azure_active_directory_role_based_access_control {
    azure_rbac_enabled     = true
    admin_group_object_ids = var.admin_group_object_ids
  }
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    network_policy      = "cilium"
    pod_cidr            = "10.81.0.0/16"
    service_cidr        = "10.82.0.0/16"
    dns_service_ip      = "10.82.0.10"
    outbound_type       = "loadBalancer"
  }
  oms_agent {
    log_analytics_workspace_id      = azurerm_log_analytics_workspace.platform.id
    msi_auth_for_monitoring_enabled = true
  }
  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }
  depends_on = [azurerm_role_assignment.network]
  tags       = local.tags
}

resource "azurerm_kubernetes_cluster_node_pool" "workload" {
  name                  = "workload"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.platform.id
  vm_size               = "Standard_D2s_v5"
  node_count            = 2
  vnet_subnet_id        = azurerm_subnet.aks.id
  mode                  = "User"
  tags                  = local.tags
}

resource "azurerm_role_assignment" "pull" {
  scope                = azurerm_container_registry.platform.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.platform.kubelet_identity[0].object_id
}

resource "azurerm_user_assigned_identity" "observer" {
  name                = "${var.name}-observer"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "observer" {
  name                = "kubernetes-observer"
  resource_group_name = azurerm_resource_group.platform.name
  parent_id           = azurerm_user_assigned_identity.observer.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.platform.oidc_issuer_url
  subject             = "system:serviceaccount:airp-system:airp-observer"
}

resource "azurerm_private_dns_zone" "service" {
  for_each            = toset(["privatelink.azurecr.io", "privatelink.vaultcore.azure.net"])
  name                = each.key
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "service" {
  for_each              = azurerm_private_dns_zone.service
  name                  = "platform"
  resource_group_name   = azurerm_resource_group.platform.name
  private_dns_zone_name = each.value.name
  virtual_network_id    = azurerm_virtual_network.platform.id
  tags                  = local.tags
}

resource "azurerm_private_endpoint" "service" {
  for_each = {
    registry = { id = azurerm_container_registry.platform.id, group = "registry", dns = "privatelink.azurecr.io" }
    vault    = { id = azurerm_key_vault.platform.id, group = "vault", dns = "privatelink.vaultcore.azure.net" }
  }
  name                = "${var.name}-${each.key}-endpoint"
  location            = var.location
  resource_group_name = azurerm_resource_group.platform.name
  subnet_id           = azurerm_subnet.endpoints.id
  private_service_connection {
    name                           = each.key
    private_connection_resource_id = each.value.id
    subresource_names              = [each.value.group]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "service"
    private_dns_zone_ids = [azurerm_private_dns_zone.service[each.value.dns].id]
  }
  tags = local.tags
}

resource "azurerm_monitor_diagnostic_setting" "aks" {
  name                       = "control-plane-audit"
  target_resource_id         = azurerm_kubernetes_cluster.platform.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.platform.id
  enabled_log {
    category = "kube-audit-admin"
  }
  enabled_log {
    category = "kube-apiserver"
  }
}