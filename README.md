# US Notify API

This project is the core of [Notify](https://notifications-admin.app.cloud.gov/). It's cloned from the brilliant work of the team at [GOV.UK Notify](https://github.com/alphagov/notifications-api), cheers!

This repo contains:

- A public-facing REST API for Notify, which teams can integrate with using [API clients built by UK](https://www.notifications.service.gov.uk/documentation)
- An internal-only REST API built using Flask to manage services, users, templates, etc., which the [admin UI](http://github.com/18F/notifications-admin) talks to)
- Asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc.

Our other repositories are:

- [notifications-admin](https://github.com/GSA/notifications-admin)
- [notifications-utils](https://github.com/GSA/notifications-utils)
- [us-notify-compliance](https://github.com/GSA/us-notify-compliance/)
- [notify-python-demo](https://github.com/GSA/notify-python-demo)


## Local setup

### Common steps

On MacOS, using [Homebrew](https://brew.sh/) for package management is highly recommended. This helps avoid some known installation issues.

1. Install pre-requisites for setup:
    * [jq](https://stedolan.github.io/jq/): `brew install jq`
    * [terraform](https://www.terraform.io/): `brew install terraform` or `brew install tfenv` and use `tfenv` to install `terraform ~> 1.4.0`
    * [cf-cli@8](https://docs.cloudfoundry.org/cf-cli/install-go-cli.html): `brew install cloudfoundry/tap/cf-cli@8`
    * [postgresql](https://www.postgresql.org/): `brew install postgresql@15` (Homebrew requires a version pin, but any recent version will work)
    * [redis](https://redis.io/): `brew install redis`
    * [pyenv](https://github.com/pyenv/pyenv): `brew install pyenv`
1. [Log into cloud.gov](https://cloud.gov/docs/getting-started/setup/#set-up-the-command-line): `cf login -a api.fr.cloud.gov --sso`
1. Ensure you have access to the `notify-local-dev` and `notify-staging` spaces in cloud.gov
1. Run the development terraform with:

        ```
        $ cd terraform/development
        $ ./run.sh
        ```

1. If you want to send data to New Relic from your local develpment environment, set `NEW_RELIC_LICENSE_KEY` within `.env`
1. Follow the instructions for either `Direct installation` or `Docker installation` below

### Direct installation

1. Set up Postgres && Redis on your machine

1. Install [poetry](https://python-poetry.org/docs/#installation)

1. Run the project setup

    `make bootstrap`

1. Run the web server and background worker

    `make run-procfile`

1. Or run them individually:

    * Run Flask (web server)

        `make run-flask`

    * Run Celery (background worker)

        `make run-celery`


### VS Code && Docker installation

If you're working in VS Code, you can also leverage Docker for a containerized dev environment

1. Uncomment the `Local Docker setup` lines in `.env` and comment out the `Local direct setup` lines.

1. Install the Remote-Containers plug-in in VS Code

1. With Docker running, create the network:

    `docker network create notify-network`

1. Using the command palette (shift+cmd+p) or green button thingy in the bottom left, search and select “Remote Containers: Open Folder in Container...” When prompted, choose **devcontainer-api** folder (note: this is a *subfolder* of notifications-api). This will start the container in a new window, replacing the current one.

1. Wait a few minutes while things happen 🍵

1. Open a VS Code terminal and run the Flask application:

    `make run-flask`

1. Open another VS Code terminal and run Celery:

    `make run-celery`

NOTE: when you change .env in the future, you'll need to rebuild the devcontainer for the change to take effect. VS Code _should_ detect the change and prompt you with a toast notification during a cached build. If not, you can find a manual rebuild in command pallette or just `docker rm` the notifications-api container.

### Known installation issues

On M1 Macs, if you get a `fatal error: 'Python.h' file not found` message, try a different method of installing Python. Installation via `pyenv` is known to work.

A direct installation of PostgreSQL will not put the `createdb` command on your `$PATH`. It can be added there in your shell startup script, or a Homebrew-managed installation of PostgreSQL will take care of it.

## Documentation

- [Infrastructure overview](#infrastructure-overview)
  - [GitHub Repositories](#github-repositories)
  - [Terraform](#terraform)
  - [AWS](#aws)
  - [New Relic](#new-relic)
  - [Onboarding](#onboarding)
  - [Setting up the infrastructure](#setting-up-the-infrastructure)
- [Testing](#testing)
  - [CI testing](#ci-testing)
  - [Manual testing](#manual-testing)
  - [To run a local OWASP scan](#to-run-a-local-owasp-scan)
- [Deploying](#deploying)
  - [Egress Proxy](#egress-proxy)
  - [Sandbox environment](#sandbox-environment)
- [Database management](#database-management)
  - [Initial state](#initial-state)
  - [Data Model Diagram](#data-model-diagram)
  - [Migrations](#migrations)
  - [Purging user data](#purging-user-data)
- [One-off tasks](#one-off-tasks)
- [How messages are queued and sent](#how-messages-are-queued-and-sent)
- [Writing public APIs](#writing-public-apis)
  - [Overview](#overview)
  - [Documenting APIs](#documenting-apis)
  - [New APIs](#new-apis)
- [API Usage](#api-usage)
  - [Connecting to the API](#connecting-to-the-api)
  - [Postman Documentation](#postman-documentation)
  - [Using OpenAPI documentation](#using-openapi-documentation)
- [Queues and tasks](#queues-and-tasks)
  - [Priority queue](#priority-queue)
  - [Celery scheduled tasks](#celery-scheduled-tasks)
- [US Notify](#us-notify)
  - [System Description](#system-description)
- [Run Book](#run-book)
  - [ Alerts, Notifications, Monitoring](#-alerts-notifications-monitoring)
  - [ Restaging Apps](#-restaging-apps)
  - [ Smoke-testing the App](#-smoke-testing-the-app)
  - [ Configuration Management](#-configuration-management)
  - [ DNS Changes](#-dns-changes)
  - [Exporting test results for compliance monitoring](#exporting-test-results-for-compliance-monitoring)
  - [ Known Gotchas](#-known-gotchas)
  - [ User Account Management](#-user-account-management)
  - [ SMS Phone Number Management](#-sms-phone-number-management)
- [Data Storage Policies \& Procedures](#data-storage-policies--procedures)
  - [Potential PII Locations](#potential-pii-locations)
  - [Data Retention Policy](#data-retention-policy)

## License && public domain

Work through [commit `e604385`](https://github.com/GSA/notifications-api/commit/e604385e0cf4c2ab8c6451b7120ceb196cce21b5) is licensed by the UK government under the MIT license. Work after that commit is in the worldwide public domain. See [LICENSE.md](./LICENSE.md) for more information.

## Contributing

As stated in [CONTRIBUTING.md](CONTRIBUTING.md), all contributions to this project will be released under the CC0 dedication. By submitting a pull request, you are agreeing to comply with this waiver of copyright interest.