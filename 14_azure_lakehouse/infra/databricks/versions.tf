terraform {
  required_version = ">= 1.6"
  required_providers {
    databricks = { source = "databricks/databricks", version = "~> 1.50" }
  }
}

# Authenticates with your Azure CLI login against the workspace from stage 1
provider "databricks" {
  host                        = var.workspace_url
  azure_workspace_resource_id = var.workspace_resource_id
}
