#!/usr/bin/env bash

../destroy_service_account.sh -s notify-management -u config-bootstrap-deployer

rm secrets.auto.tfvars
