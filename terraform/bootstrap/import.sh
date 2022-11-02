#!/usr/bin/env bash

read -p "Are you sure you want to import terraform state (y/n)? " verify

if [[ $verify == "y" ]]; then
  echo "Importing bootstrap state"
  ./run.sh import module.s3.cloudfoundry_service_instance.bucket 6b759c13-6253-4a64-9bda-dd1f620185b0
  ./run.sh import cloudfoundry_service_key.bucket_creds a8e40295-68b7-42ba-8955-d82ba262e948
  ./run.sh plan
else
  echo "Not importing bootstrap state"
fi
