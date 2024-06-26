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

variable "mail_from_subdomain" {
  type        = string
  description = "Subdomain of email_domain to set as the mail-from header"
  default     = ""
}
