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
  description = "AWS region the SES instance is in"
}

variable "email_domain" {
  type        = string
  default     = ""
  description = "domain name that emails will be coming from"
}

variable "email_receipt_error" {
  type        = string
  description = "email address to list in SPF records for errors to be sent to"
}
