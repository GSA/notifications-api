.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

CF_SPACE ?= ${DEPLOY_ENV}
CF_HOME ?= ${HOME}
$(eval export CF_HOME)


## DEVELOPMENT

.PHONY: bootstrap
bootstrap: generate-version-file ## Set up everything to run the app
	pip3 install -r requirements_for_test.txt
	createdb notification_api || true
	(flask db upgrade) || true

.PHONY: bootstrap-with-docker
bootstrap-with-docker: ## Build the image to run the app in Docker
	docker build -f docker/Dockerfile -t notifications-api .

.PHONY: run-flask
run-flask: ## Run flask
	flask run -p 6011 --host=0.0.0.0

.PHONY: run-celery
run-celery: ## Run celery, TODO remove purge for staging/prod
	celery -A run_celery.notify_celery purge -f
	celery \
		-A run_celery.notify_celery worker \
		--pidfile="/tmp/celery.pid" \
		--loglevel=INFO \
		--concurrency=4

.PHONY: run-celery-with-docker
run-celery-with-docker: ## Run celery in Docker container (useful if you can't install pycurl locally)
	./scripts/run_with_docker.sh make run-celery

.PHONY: run-celery-beat
run-celery-beat: ## Run celery beat
	celery \
	-A run_celery.notify_celery beat \
	--loglevel=INFO

.PHONY: run-celery-beat-with-docker
run-celery-beat-with-docker: ## Run celery beat in Docker container (useful if you can't install pycurl locally)
	./scripts/run_with_docker.sh make run-celery-beat

.PHONY: help
help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: generate-version-file
generate-version-file: ## Generates the app version file
	@echo -e "__git_commit__ = \"${GIT_COMMIT}\"\n__time__ = \"${DATE}\"" > ${APP_VERSION_FILE}

.PHONY: test
test: ## Run tests
	# flake8 .
	isort --check-only ./app ./tests
	pytest -n4 --maxfail=10

.PHONY: freeze-requirements
freeze-requirements: ## Pin all requirements including sub dependencies into requirements.txt
	pip install --upgrade pip-tools
	pip-compile requirements.in

.PHONY: audit
audit:
	pip install --upgrade pip-audit
	pip-audit -r requirements.txt -l --ignore-vuln PYSEC-2022-237
	-pip-audit -r requirements_for_test.txt -l

.PHONY: static-scan
static-scan:
	pip install bandit
	bandit -r app/

.PHONY: clean
clean:
	rm -rf node_modules cache target venv .coverage build tests/.cache ${CF_MANIFEST_PATH}


## DEPLOYMENT

.PHONY: cf-login
cf-login: ## Log in to Cloud Foundry
	$(if ${CF_USERNAME},,$(error Must specify CF_USERNAME))
	$(if ${CF_PASSWORD},,$(error Must specify CF_PASSWORD))
	$(if ${CF_SPACE},,$(error Must specify CF_SPACE))
	@echo "Logging in to Cloud Foundry on ${CF_API}"
	@cf login -a "${CF_API}" -u ${CF_USERNAME} -p "${CF_PASSWORD}" -o "${CF_ORG}" -s "${CF_SPACE}"

.PHONY: cf-check-api-db-migration-task
cf-check-api-db-migration-task: ## Get the status for the last notifications-api task
	@cf curl /v3/apps/`cf app --guid notifications-api`/tasks?order_by=-created_at | jq -r ".resources[0].state"

.PHONY: check-if-migrations-to-run
check-if-migrations-to-run:
	@echo $(shell python3 scripts/check_if_new_migration.py)

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
