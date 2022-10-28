#!/bin/bash

if [[ $CF_INSTANCE_INDEX -eq 0 ]]; then
  flask db upgrade
fi

${HOME}/scripts/run_app_paas.sh gunicorn -c ${HOME}/gunicorn_config.py application
