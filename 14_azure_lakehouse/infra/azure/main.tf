# Stage 1 — Azure resources: ADLS Gen2 lake, Databricks workspace (Premium, for
# Unity Catalog), an access connector whose managed identity reads the lake, and
# a budget alert so a forgotten cluster can't quietly run up a bill.

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

locals {
  name = "${var.prefix}${random_string.suffix.result}"
  tags = { project = "azure-lakehouse-demo", managed_by = "terraform" }
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.prefix}-lakehouse"
  location = var.location
  tags     = local.tags
}

# ADLS Gen2: hierarchical namespace on, no public blobs, no account keys —
# everything authenticates with Entra ID (managed identity or your login).
resource "azurerm_storage_account" "lake" {
  name                            = "st${local.name}"
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = azurerm_resource_group.rg.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  tags                            = local.tags
}

resource "azurerm_storage_container" "layer" {
  for_each              = toset(["landing", "bronze", "silver", "gold"])
  name                  = each.key
  storage_account_id    = azurerm_storage_account.lake.id
  container_access_type = "private"
}

resource "azurerm_databricks_workspace" "ws" {
  name                        = "dbw-${local.name}"
  resource_group_name         = azurerm_resource_group.rg.name
  location                    = azurerm_resource_group.rg.location
  sku                         = "premium"
  managed_resource_group_name = "rg-${var.prefix}-dbx-managed"
  tags                        = local.tags
}

# Managed identity Unity Catalog uses to reach the lake (no secrets to rotate)
resource "azurerm_databricks_access_connector" "uc" {
  name                = "dbac-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  identity {
    type = "SystemAssigned"
  }
  tags = local.tags
}

resource "azurerm_role_assignment" "uc_lake" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.uc.identity[0].principal_id
}

# Lets you upload the sample CSVs with `az storage blob upload-batch --auth-mode login`
resource "azurerm_role_assignment" "me_lake" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_consumption_budget_resource_group" "budget" {
  name              = "budget-${var.prefix}-lakehouse"
  resource_group_id = azurerm_resource_group.rg.id
  amount            = var.monthly_budget_usd
  time_grain        = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp())
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    contact_emails = [var.alert_email]
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
