#!/usr/bin/env bash

org="gsa-tts-benefits-studio-prototyping"

usage="
$0: Create a Service User Account for a given space

Usage:
  $0 -h
  $0 -s <SPACE NAME> -u <USER NAME> [-r <ROLE NAME>] [-o <ORG NAME>] [-m]

Options:
-h: show help and exit
-s <SPACE NAME>: configure the space to act on. Required
-u <USER NAME>: set the service user name. Required
-r <ROLE NAME>: set the service user's role to either space-deployer or space-auditor. Default: space-deployer
-m: If provided, make the service user an OrgManager
-o <ORG NAME>: configure the organization to act on. Default: $org

Notes:
OrgManager is required for terraform to create <env>-egress spaces
"

set -e
set -o pipefail

space=""
service=""
role="space-deployer"
org_manager="false"

while getopts ":hms:u:r:o:" opt; do
  case "$opt" in
    s)
      space=${OPTARG}
      ;;
    u)
      service=${OPTARG}
      ;;
    r)
      role=${OPTARG}
      ;;
    o)
      org=${OPTARG}
      ;;
    m)
      org_manager="true"
      ;;
    h)
      echo "$usage"
      exit 0
      ;;
  esac
done

if [[ $space = "" || $service = "" ]]; then
  echo "$usage"
  exit 1
fi

cf target -o $org -s $space 1>&2

# create user account service
cf create-service cloud-gov-service-account $role $service 1>&2

# create service key
cf create-service-key $service service-account-key 1>&2

# output service key to stdout in secrets.auto.tfvars format
creds=`cf service-key $service service-account-key | tail -n 4`
username=`echo $creds | jq -r '.username'`
password=`echo $creds | jq -r '.password'`

if [[ $org_manager = "true" ]]; then
  cf set-org-role $username $org OrgManager 1>&2
fi

cat << EOF
# generated with $0 -s $space -u $service -r $role -o $org
# revoke with $(dirname $0)/destroy_service_account.sh -s $space -u $service -o $org

cf_user = "$username"
cf_password = "$password"
EOF
