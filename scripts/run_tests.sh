#!/bin/bash
#
# Run project tests
#
# NOTE: This script expects to be run from the project root with
# ./scripts/run_tests.sh

# Use default environment vars for localhost if not already set

set -o pipefail

source environment_test.sh

function display_result {
  RESULT=$1
  EXIT_STATUS=$2
  TEST=$3

  if [ $RESULT -ne 0 ]; then
    echo -e "\033[31m$TEST failed\033[0m"
    exit $EXIT_STATUS
  else
    echo -e "\033[32m$TEST passed\033[0m"
  fi
}

if [[ -z "$VIRTUAL_ENV" ]] && [[ -d venv ]]; then
  source ./venv/bin/activate
fi
echo -e "\033[31mWARNING. NOT RUNNING flake8 AGAINST TEST DIRECTORY DUE TO LARGE AMOUNT OF EXISTING ISSUES.\033[0m"
flake8 app/
display_result $? 1 "Code style check"

# run with four concurrent threads
py.test --cov=app --cov-report=term-missing tests/ --junitxml=test_results.xml -n 4 -v
display_result $? 2 "Unit tests"
