##
# Cloud Foundry app initialization script
# https://docs.cloudfoundry.org/devguide/deploy-apps/deploy-app.html#profile
##

export http_proxy=$egress_proxy
export https_proxy=$egress_proxy
export NEW_RELIC_PROXY_HOST=$egress_proxy
export no_proxy="apps.internal,s3-fips.us-gov-west-1.amazonaws.com"
