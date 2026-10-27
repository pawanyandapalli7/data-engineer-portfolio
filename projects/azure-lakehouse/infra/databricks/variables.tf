variable "workspace_url" { type = string }
variable "workspace_resource_id" { type = string }
variable "access_connector_id" { type = string }
variable "storage_account_name" { type = string }

variable "catalog" {
  type    = string
  default = "lakehouse_demo"
}
