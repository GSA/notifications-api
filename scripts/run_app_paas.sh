#!/bin/bash

set -e -o pipefail

TERMINATE_TIMEOUT=9
MAX_DISK_SPACE_USAGE=75

function check_params {
  if [ -z "${NOTIFY_APP_NAME}" ]; then
    echo "You must set NOTIFY_APP_NAME"
    exit 1
  fi
}

function on_exit {
  echo "Terminating application process with pid ${APP_PID}"
  kill ${APP_PID} || true
  wait_time=0
  while (kill -0 ${APP_PID} 2&>/dev/null); do
    echo "Application is still running.."
    sleep 1
    let wait_time=wait_time+1
    if [ "$wait_time" -ge "$TERMINATE_TIMEOUT" ]; then
      echo "Timeout reached, killing process with pid ${APP_PID}"
      kill -9 ${APP_PID} || true
      break
    fi
  done
  echo "Terminating remaining subprocesses.."
  kill 0
}

function start_application {
  exec "$@" &
  APP_PID=`jobs -p`
  echo "Application process pid: ${APP_PID}"
}

function check_disk_space {
    # get something like:
    #
    # Filesystem     Use%
    # overlay         56%
    # tmpfs            0%
    #
    # and only keep '56'
    SPACE_USAGE=$(df --output="source,pcent" | grep overlay | tr --squeeze-repeats " " | cut -f2 -d" "| cut -f1 -d"%")

    if [[ "${SPACE_USAGE}" -ge "${MAX_DISK_SPACE_USAGE}" ]]; then
        echo "Terminating ${NOTIFY_APP_NAME}, instance ${INSTANCE_INDEX} because we're running out of disk space"
        echo "Usage: ${SPACE_USAGE}% - limit ${MAX_DISK_SPACE_USAGE}%"
        exit
    fi
}

function run {
  while true; do
    kill -0 ${APP_PID} 2&>/dev/null || break
    check_disk_space
    sleep 1
  done
}

echo "Run script pid: $$"

check_params

trap "on_exit" EXIT

# The application has to start first!
start_application "$@"

run
