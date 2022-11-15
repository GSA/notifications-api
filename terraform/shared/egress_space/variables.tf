variable "cf_password" {
  type = string
  sensitive = true
}
variable "cf_user" {}
variable "cf_org_name" {}
variable "cf_restricted_space_name" {}
variable "deployers" {
  type = set(string)
}
