#!/bin/bash

if [[ $CF_INSTANCE_INDEX -eq 0 ]]; then
  flask db upgrade
fi

exec newrelic-admin run-program gunicorn -c ${HOME}/gunicorn_config.py gunicorn_entry:application
