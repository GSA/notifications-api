# Brings resources created outside of Terraform (e.g. created via "ClickOps")
# under Terraform managmenet. The id required by the import block comes from:
# `cf space notify-sandbox --guid`

import {
  to = cloudfoundry_space.notify-sandbox
  id = "420bb231-f99f-4dea-8cda-d342981d2718"
}
