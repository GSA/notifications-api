#!/usr/bin/env bash

read -p "Are you sure you want to import terraform state (y/n)? " verify

if [[ $verify == "y" ]]; then
  echo "Importing bootstrap state"
  ./run.sh import module.s3.cloudfoundry_service_instance.bucket 31204bcc-aae3-4cd3-8b59-5055a338d44f
  ./run.sh import cloudfoundry_service_key.bucket_creds 483a6ac5-4ba0-48ad-9850-ef87b51aaa08
  ./run.sh plan
else
  echo "Not importing bootstrap state"
fi
