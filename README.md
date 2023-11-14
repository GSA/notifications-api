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

_Note: If brew is not found: Verify that Homebrew is in your system's PATH. You may need to follow additional instructions to add Homebrew to your PATH in /Users/homefolder/.zprofile:_

1.  Install pre-requisites for setup:
    - [jq](https://stedolan.github.io/jq/): `brew install jq`
    - [terraform](https://www.terraform.io/): `brew install terraform` or `brew install tfenv` and use `tfenv` to install `terraform ~> 1.4.0`
    - [cf-cli@8](https://docs.cloudfoundry.org/cf-cli/install-go-cli.html): `brew install cloudfoundry/tap/cf-cli@8`
    - [postgresql](https://www.postgresql.org/): `brew install postgresql@15` (Homebrew requires a version pin, but any recent version will work)
    - [redis](https://redis.io/): `brew install redis`
    - [pyenv](https://github.com/pyenv/pyenv): `brew install pyenv`
    - [poetry](https://python-poetry.org/docs/#installation): `brew install poetry`
1.  [Log into cloud.gov](https://cloud.gov/docs/getting-started/setup/#set-up-the-command-line): `cf login -a api.fr.cloud.gov --sso`
1.  Ensure you have access to the `notify-local-dev` and `notify-staging` spaces in cloud.gov
1.  Run the development terraform
    _(Be sure to clone the repository first and navigate to the terraform directory):_

            ```
            $ cd terraform/development
            $ ./run.sh
            ```

1.  If you want to send data to New Relic from your local develpment environment, set `NEW_RELIC_LICENSE_KEY` within `.env`
1.  Start Postgres && Redis

         ```
         brew services start postgresql@15
         brew services start redis
         ```

#### Install

1. Run the project setup (If there are errors, check for Python versions >=3.9,<3.12. Ensure that you have the required database set up and migrations)

   `make bootstrap`

1. Run the web server and background workers

   `make run-procfile`

- Or run them individually:

- Run Flask (web server)

  `make run-flask`

- Run Celery (background worker)

  `make run-celery`

### Python dependency management

We're using [`Poetry`](https://python-poetry.org/) for managing our Python
dependencies and local virtual environments. When it comes to managing the
Python dependencies, there are a couple of things to bear in mind.

For situations where you manually manipulate the `pyproject.toml` file, you
should use the `make py-lock` command to sync the `poetry.lock` file. This will
ensure that you don't inadvertently bring in other transitive dependency updates
that have not been fully tested with the project yet.

If you're just trying to update a dependency to a newer (or the latest) version,
you should let Poetry take care of that for you by running the following:

```
poetry update <dependency> [<dependency>...]
```

You can specify more than one dependency together. With this command, Poetry
will do the following for you:

- Find the latest compatible version(s) of the specified dependency/dependencies
- Install the new versions
- Update and sync the `poetry.lock` file

In either situation, once you are finished and have verified the dependency
changes are working, please be sure to commit both the `pyproject.toml` and
`poetry.lock` files.

### Keeping the notification-utils dependency up-to-date

The `notifications-utils` dependency references the other repository we have at
https://github.com/GSA/notifications-utils - this dependency requires a bit of
extra legwork to ensure it stays up-to-date.

Whenever a PR is merged in the `notifications-utils` repository, we need to make
sure the changes are pulled in here and committed to this repository as well.
You can do this by going through these steps:

- Make sure your local `main` branch is up-to-date
- Create a new branch to work in
- Run `make update-utils`
- Commit the updated `poetry.lock` file and push the changes
- Make a new PR with the change
- Have the PR get reviewed and merged

### Known installation issues

On M1 Macs, if you get a `fatal error: 'Python.h' file not found` message, try a
different method of installing Python. Installation via `pyenv` is known to
work.

A direct installation of PostgreSQL will not put the `createdb` command on your
`$PATH`. It can be added there in your shell startup script, or a
Homebrew-managed installation of PostgreSQL will take care of it.

## Documentation

- [Infrastructure overview](./docs/all.md#infrastructure-overview)
  - [GitHub Repositories](./docs/all.md#github-repositories)
  - [Terraform](./docs/all.md#terraform)
  - [AWS](./docs/all.md#aws)
  - [New Relic](./docs/all.md#new-relic)
  - [Onboarding](./docs/all.md#onboarding)
  - [Setting up the infrastructure](./docs/all.md#setting-up-the-infrastructure)
- [Using the logs](./docs/all.md#using-the-logs)
- [Testing](./docs/all.md#testing)
  - [CI testing](./docs/all.md#ci-testing)
  - [Manual testing](./docs/all.md#manual-testing)
  - [To run a local OWASP scan](./docs/all.md#to-run-a-local-owasp-scan)
- [Deploying](./docs/all.md#deploying)
  - [Egress Proxy](./docs/all.md#egress-proxy)
  - [Managing environment variables](./docs/all.md#managing-environment-variables)
  - [Sandbox environment](./docs/all.md#sandbox-environment)
- [Database management](./docs/all.md#database-management)
  - [Initial state](./docs/all.md#initial-state)
  - [Data Model Diagram](./docs/all.md#data-model-diagram)
  - [Migrations](./docs/all.md#migrations)
  - [Purging user data](./docs/all.md#purging-user-data)
- [One-off tasks](./docs/all.md#one-off-tasks)
- [How messages are queued and sent](./docs/all.md#how-messages-are-queued-and-sent)
- [Writing public APIs](./docs/all.md#writing-public-apis)
  - [Overview](./docs/all.md#overview)
  - [Documenting APIs](./docs/all.md#documenting-apis)
  - [New APIs](./docs/all.md#new-apis)
- [API Usage](./docs/all.md#api-usage)
  - [Connecting to the API](./docs/all.md#connecting-to-the-api)
  - [Postman Documentation](./docs/all.md#postman-documentation)
  - [Using OpenAPI documentation](./docs/all.md#using-openapi-documentation)
- [Queues and tasks](./docs/all.md#queues-and-tasks)
  - [Priority queue](./docs/all.md#priority-queue)
  - [Celery scheduled tasks](./docs/all.md#celery-scheduled-tasks)
- [US Notify](./docs/all.md#us-notify)
  - [System Description](./docs/all.md#system-description)
- [Run Book](./docs/all.md#run-book)
  - [ Alerts, Notifications, Monitoring](./docs/all.md#-alerts-notifications-monitoring)
  - [ Restaging Apps](./docs/all.md#-restaging-apps)
  - [ Smoke-testing the App](./docs/all.md#-smoke-testing-the-app)
  - [ Configuration Management](./docs/all.md#-configuration-management)
  - [ DNS Changes](./docs/all.md#-dns-changes)
  - [Exporting test results for compliance monitoring](./docs/all.md#exporting-test-results-for-compliance-monitoring)
  - [ Known Gotchas](./docs/all.md#-known-gotchas)
  - [ User Account Management](./docs/all.md#-user-account-management)
  - [ SMS Phone Number Management](./docs/all.md#-sms-phone-number-management)
- [Data Storage Policies \& Procedures](./docs/all.md#data-storage-policies--procedures)
  - [Potential PII Locations](./docs/all.md#potential-pii-locations)
  - [Data Retention Policy](./docs/all.md#data-retention-policy)

## License && public domain

Work through [commit `e604385`](https://github.com/GSA/notifications-api/commit/e604385e0cf4c2ab8c6451b7120ceb196cce21b5) is licensed by the UK government under the MIT license. Work after that commit is in the worldwide public domain. See [LICENSE.md](./LICENSE.md) for more information.

## Contributing

As stated in [CONTRIBUTING.md](CONTRIBUTING.md), all contributions to this project will be released under the CC0 dedication. By submitting a pull request, you are agreeing to comply with this waiver of copyright interest.
