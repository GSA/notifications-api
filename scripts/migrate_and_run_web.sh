#!/bin/bash

if [[ $CF_INSTANCE_INDEX -eq 0 ]]; then
  flask db upgrade
fi

exec newrelic-admin run-program gunicorn -c ${HOME}/gunicorn_config.py -b 0.0.0.0:6011 gunicorn_entry:application
