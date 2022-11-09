###
# Target space/org
###

data "cloudfoundry_org" "org" {
  name = var.cf_org_name
}

###
# Egress Space
###

resource "cloudfoundry_space" "public_egress" {
  name = "${var.cf_restricted_space_name}-egress"
  org = data.cloudfoundry_org.org.id
}

###
# User roles
###

data "cloudfoundry_user" "users" {
  for_each = var.deployers
  name = each.key
  org_id = data.cloudfoundry_org.org.id
}

locals {
  user_ids = [for user in data.cloudfoundry_user.users : user.id]
}

resource "cloudfoundry_space_users" "deployers" {
  space = cloudfoundry_space.public_egress.id
  managers = local.user_ids
  developers = local.user_ids
}
