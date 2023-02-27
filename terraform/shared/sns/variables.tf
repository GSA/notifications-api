variable "cf_org_name" {
  type        = string
  description = "cloud.gov organization name"
}

variable "cf_space_name" {
  type        = string
  description = "cloud.gov space name (staging or prod)"
}

variable "name" {
  type        = string
  description = "name of the service instance"
}

variable "recursive_delete" {
  type        = bool
  description = "when true, deletes service bindings attached to the resource (not recommended for production)"
  default     = false
}

variable "aws_region" {
  type        = string
  description = "AWS region the SNS settings are set in"
}

variable "monthly_spend_limit" {
  type        = number
  description = "SMS budget limit in USD. Support request must be made before raising above 1"
}
