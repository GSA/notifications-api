#!/bin/bash

# Run migrations on the first instance only.
# On Cloud Foundry, CF_INSTANCE_INDEX identifies the instance.
# On Render, RENDER_INSTANCE_ID is available but there's no index;
# migrations run in the build command instead, so skip here.
if [[ -z "$RENDER" && $CF_INSTANCE_INDEX -eq 0 ]]; then
  flask db upgrade
fi

# On Render, New Relic is optional — run gunicorn directly if not configured.
if [[ -n "$NEW_RELIC_LICENSE_KEY" ]]; then
  exec newrelic-admin run-program gunicorn -c ${HOME:-$(pwd)}/gunicorn_config.py gunicorn_entry:application
else
  exec gunicorn -c ${HOME:-$(pwd)}/gunicorn_config.py gunicorn_entry:application
fi
