# The notify-management space contains resources that don't belong in our
# deployed environment spaces (notify-sandbox, etc.) including:
#   * the bucket that holds Terraform state
#   * supplemental service brokers, letting cloud.gov provision AWS services
#   * some service accounts used for deployment

import {
  to = cloudfoundry_space.notify-management
  id = "a022fabe-056c-4329-9d4f-3f7a67442d36"
}
