.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

## DEVELOPMENT

.PHONY: bootstrap
bootstrap: ## Set up everything to run the app
	make generate-version-file
	pipenv install --dev
	createdb notification_api || true
	(pipenv run flask db upgrade) || true

.PHONY: bootstrap-with-docker
bootstrap-with-docker: ## Build the image to run the app in Docker
	docker build -f docker/Dockerfile -t notifications-api .

.PHONY: run-procfile
run-procfile:
	pipenv run honcho start -f Procfile.dev

.PHONY: avg-complexity
avg-complexity:
	echo "*** Shows average complexity in radon of all code ***"
	pipenv run radon cc ./app -a -na

.PHONY: too-complex
too-complex:
	echo "*** Shows code that got a rating of D or F in radon ***"
	pipenv run radon cc ./app -a -nd

.PHONY: run-flask
run-flask: ## Run flask
	pipenv run newrelic-admin run-program flask run -p 6011 --host=0.0.0.0

.PHONY: run-celery
run-celery: ## Run celery, TODO remove purge for staging/prod
	pipenv run celery -A run_celery.notify_celery purge -f
	pipenv run newrelic-admin run-program celery \
		-A run_celery.notify_celery worker \
		--pidfile="/tmp/celery.pid" \
		--loglevel=INFO \
		--concurrency=4

.PHONY: run-celery-beat
run-celery-beat: ## Run celery beat
	pipenv run celery \
	-A run_celery.notify_celery beat \
	--loglevel=INFO

.PHONY: cloudgov-user-report
cloudgov-user-report:
	@pipenv run python -m terraform.ops.cloudgov_user_report

.PHONY: help
help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: generate-version-file
generate-version-file: ## Generates the app version file
	@echo -e "__git_commit__ = \"${GIT_COMMIT}\"\n__time__ = \"${DATE}\"" > ${APP_VERSION_FILE}

.PHONY: test
test: export NEW_RELIC_ENVIRONMENT=test
test: ## Run tests and create coverage report
	pipenv run flake8 .
	pipenv run isort --check-only ./app ./tests
	pipenv run coverage run --omit=*/notifications_utils/* -m pytest --maxfail=10
	pipenv run coverage report --fail-under=88
	pipenv run coverage html -d .coverage_cache

.PHONY: freeze-requirements
freeze-requirements: ## Pin all requirements including sub dependencies into requirements.txt
	pipenv lock
	pipenv requirements

.PHONY: audit
audit:
	pipenv requirements > requirements.txt
	pipenv requirements --dev > requirements_for_test.txt
	pipenv run pip-audit -r requirements.txt
	-pipenv run pip-audit -r requirements_for_test.txt

.PHONY: static-scan
static-scan:
	pipenv run bandit -r app/

.PHONY: clean
clean:
	rm -rf node_modules cache target venv .coverage build tests/.cache ${CF_MANIFEST_PATH}


## DEPLOYMENT

# .PHONY: cf-deploy-failwhale
# cf-deploy-failwhale:
# 	$(if ${CF_SPACE},,$(error Must target space, eg `make preview cf-deploy-failwhale`))
# 	cd ./paas-failwhale; cf push notify-api-failwhale -f manifest.yml

# .PHONY: enable-failwhale
# enable-failwhale: ## Enable the failwhale app and disable api
# 	$(if ${DNS_NAME},,$(error Must target space, eg `make preview enable-failwhale`))
# 	# make sure failwhale is running first
# 	cf start notify-api-failwhale

# 	cf map-route notify-api-failwhale ${DNS_NAME} --hostname api
# 	cf unmap-route notify-api ${DNS_NAME} --hostname api
# 	@echo "Failwhale is enabled"

# .PHONY: disable-failwhale
# disable-failwhale: ## Disable the failwhale app and enable api
# 	$(if ${DNS_NAME},,$(error Must target space, eg `make preview disable-failwhale`))

# 	cf map-route notify-api ${DNS_NAME} --hostname api
# 	cf unmap-route notify-api-failwhale ${DNS_NAME} --hostname api
# 	cf stop notify-api-failwhale
# 	@echo "Failwhale is disabled"
