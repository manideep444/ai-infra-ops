variable "subscription_id" {
  type        = string
  description = "Operator-provided Azure subscription."
}

variable "name" {
  type        = string
  description = "Globally unique lowercase alphanumeric prefix for ACR and Key Vault."
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{5,15}$", var.name))
    error_message = "Use 6-16 lowercase alphanumeric characters, starting with a letter."
  }
}

variable "location" {
  type        = string
  default     = "eastus2"
  description = "Verify regional availability and quotas before applying."
}

variable "admin_group_object_ids" {
  type        = list(string)
  description = "Entra groups authorized to administer AKS; no local admin credentials."
  validation {
    condition     = length(var.admin_group_object_ids) > 0
    error_message = "At least one operator-controlled Entra admin group is required."
  }
}