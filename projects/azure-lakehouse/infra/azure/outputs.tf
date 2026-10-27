output "workspace_url" {
  value = "https://${azurerm_databricks_workspace.ws.workspace_url}"
}

output "workspace_resource_id" {
  value = azurerm_databricks_workspace.ws.id
}

output "access_connector_id" {
  value = azurerm_databricks_access_connector.uc.id
}

output "storage_account_name" {
  value = azurerm_storage_account.lake.name
}

output "landing_path" {
  value = "abfss://landing@${azurerm_storage_account.lake.name}.dfs.core.windows.net/synthea"
}
