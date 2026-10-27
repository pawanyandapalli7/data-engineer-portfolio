variable "subscription_id" {
  type        = string
  description = "Azure subscription to deploy into"
}

variable "location" {
  type    = string
  default = "westus2"
}

variable "prefix" {
  type        = string
  default     = "lkh"
  description = "Short lowercase prefix for resource names"
  validation {
    condition     = can(regex("^[a-z0-9]{2,6}$", var.prefix))
    error_message = "prefix must be 2-6 lowercase letters or digits."
  }
}

variable "alert_email" {
  type        = string
  description = "Where the monthly budget alert goes"
}

variable "monthly_budget_usd" {
  type    = number
  default = 25
}
