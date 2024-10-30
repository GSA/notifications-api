#!/bin/bash

# Create a requirements.txt file so dependencies are properly managed with the
# deploy.  This will overwrite any existing requirements.txt file to make sure
# it is always up-to-date.
poetry export --without-hashes --format=requirements.txt > requirements.txt

# Target the notify-sandbox space and deploy to cloud.gov with a cf push.
# All environment variables are accounted for in the deploy-config/sandbox.yml
# file, no need to add any of your own or source a .env* file.

# If this errors out because you need to be logged in, login first with this:
# cf login -a api.fr.cloud.gov --sso
cf target -o gsa-tts-benefits-studio -s notify-sandbox
cf push -f manifest.yml --vars-file deploy-config/sandbox.yml --strategy rolling
