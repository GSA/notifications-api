"""
Format of the yaml file looks like:

1:
  attributes:
    alpha: 'NO'
    comment: null
    dlr: Carrier DLR
    generic_sender: ''
    numeric: LIMITED
    sc: 'NO'
    sender_and_registration_info: All senders CONVERTED into random long numeric senders
    text_restrictions: Bulk/marketing traffic NOT allowed
  billable_units: 1
  names:
  - Canada
  - United States
  - Dominican Republic
"""

import os

import yaml

dir_path = os.path.dirname(os.path.realpath(__file__))

with open("{}/international_billing_rates.yml".format(dir_path)) as f:
    INTERNATIONAL_BILLING_RATES = yaml.safe_load(f)
    COUNTRY_PREFIXES = list(
        reversed(sorted(INTERNATIONAL_BILLING_RATES.keys(), key=len))
    )
