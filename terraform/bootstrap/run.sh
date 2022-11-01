#!/usr/bin/env bash

if [[ ! -f "secrets.auto.tfvars" ]]; then
  ../create_service_account.sh -s notify-management -u config-bootstrap-deployer > secrets.auto.tfvars
fi

if [[ $# -gt 0 ]]; then
  echo "Running terraform $@"
  terraform $@
else
  echo "Not running terraform"
fi
