output "resource_group" {
  value = azurerm_resource_group.platform.name
}

output "cluster_name" {
  value = azurerm_kubernetes_cluster.platform.name
}

output "registry" {
  value = azurerm_container_registry.platform.login_server
}

output "observer_client_id" {
  value = azurerm_user_assigned_identity.observer.client_id
}

output "key_vault_uri" {
  value = azurerm_key_vault.platform.vault_uri
}