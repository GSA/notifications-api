variable "cf_org_name" {}
variable "cf_restricted_space_name" {}
variable "deployers" {
  type = set(string)
}

variable "delete_recursive_allowed" {
  type        = bool
  default     = true
  description = "Flag for allowing resources to be recursively deleted - not recommended in production environments"
}

variable "allow_ssh" {
  type        = bool
  default     = true
  description = "Flag for allowing SSH access in a space - not recommended in production environments"
}
