# Stage 2 — Unity Catalog: a storage credential backed by the access connector,
# one external location per lake container, and a catalog whose bronze / silver /
# gold schemas each store their tables in their own container.

locals {
  layers = ["landing", "bronze", "silver", "gold"]
  url    = { for l in local.layers : l => "abfss://${l}@${var.storage_account_name}.dfs.core.windows.net/" }
}

resource "databricks_storage_credential" "lake" {
  name = "lakehouse-demo-mi"
  azure_managed_identity {
    access_connector_id = var.access_connector_id
  }
  comment = "Managed identity for the lakehouse demo ADLS account"
}

resource "databricks_external_location" "layer" {
  for_each        = toset(local.layers)
  name            = "lakehouse-demo-${each.key}"
  url             = local.url[each.key]
  credential_name = databricks_storage_credential.lake.id
  comment         = "${each.key} container"
}

resource "databricks_catalog" "lakehouse" {
  name         = var.catalog
  storage_root = local.url["gold"]
  comment      = "Bronze/Silver/Gold lakehouse on Synthea synthetic data"
  depends_on   = [databricks_external_location.layer]
}

resource "databricks_schema" "layer" {
  for_each     = toset(["bronze", "silver", "gold"])
  catalog_name = databricks_catalog.lakehouse.name
  name         = each.key
  storage_root = local.url[each.key]
  comment      = "${each.key} layer"
}
