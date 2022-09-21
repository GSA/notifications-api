#!/usr/bin/env bash

../destroy_service_account.sh -s 10x-notifications -u config-bootstrap-deployer

rm secrets.auto.tfvars
