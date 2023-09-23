- [Infrastructure overview](#infrastructure-overview)
  - [GitHub Repositories](#github-repositories)
  - [Terraform](#terraform)
  - [AWS](#aws)
  - [New Relic](#new-relic)
  - [Onboarding](#onboarding)
  - [Setting up the infrastructure](#setting-up-the-infrastructure)
- [Using the logs](#using-the-logs)
- [Testing](#testing)
  - [CI testing](#ci-testing)
  - [Manual testing](#manual-testing)
  - [To run a local OWASP scan](#to-run-a-local-owasp-scan)
- [Deploying](#deploying)
  - [Egress Proxy](#egress-proxy)
  - [Managing environment variables](#managing-environment-variables)
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


# Infrastructure overview

A diagram of the system is available [in our compliance repo](https://github.com/GSA/us-notify-compliance/blob/main/diagrams/rendered/apps/application.boundary.png).

Notify is a Flask application running on [cloud.gov](https://cloud.gov), which also brokers access to a PostgreSQL database and Redis store.

In addition to the Flask app, Notify uses Celery to manage the task queue. Celery stores tasks in Redis.

## GitHub Repositories

Application, infrastructure, and compliance work is spread across several repositories:

### Application

* [notifications-api](https://github.com/GSA/notifications-api) for the API app
* [notifications-admin](https://github.com/GSA/notifications-admin) for the Admin UI app
* [notifications-utils](https://github.com/GSA/notifications-utils) for common library functions

### Infrastructure

In addition to terraform directories in the api and admin apps above:

#### We maintain:

* [usnotify-ssb](https://github.com/GSA/usnotify-ssb) A supplemental service broker that provisions SES and SNS for us
* [ttsnotify-brokerpak-sms](https://github.com/GSA/ttsnotify-brokerpak-sms) The brokerpak defining SNS (SMS sending)

#### We use:

* [datagov-brokerpak-smtp](https://github.com/GSA-TTS/datagov-brokerpak-smtp) The brokerpak defining SES
* [cg-egress-proxy](https://github.com/GSA-TTS/cg-egress-proxy/) The caddy proxy that allows external API calls

### Compliance

* [us-notify-compliance](https://github.com/GSA/us-notify-compliance) for OSCAL control documentation and diagrams

## Terraform

We use Terraform to manage our infrastructure, providing consistent setups across the environments.

Our Terraform configurations manage components via cloud.gov. This means that the configurations should work out of the box if you are using a Cloud Foundry platform, but will not work for setups based on raw AWS.

### Development

There are several remote services required for local development:

* S3
* SES
* SNS

Credentials for these services are created by running:

1. `cd terraform/development`
1. `./run.sh`

in both the api repository as well as the admin repository.

This will append credentials to your `.env` file. You will need to manually clean up any prior runs from that file if you run that command again.

You can remove your development infrastructure by running `./run.sh -d`

#### Resetting

`./reset.sh` can be used to import your development infrastructure information in case of a new computer or new working tree and the old terraform state file was not transferred.

#### Offboarding

`./reset.sh -u USER_TO_OFFBOARD` can be used to import another user's development resources in order to clean them up. Steps for use:

1. Move your existing terraform state file aside temporarily, so it is not overwritten.
1. `./reset.sh -u USER_TO_OFFBOARD`
1. Answer no to the prompt about creating missing resources.
1. Run `./run.sh -u USER_TO_OFFBOARD -d` to fully remove the rest of that user's resources.

### Cloud.gov

The cloud.gov environment is configured with Terraform. See [the `terraform` folder](../terraform/) to learn about that.

## AWS

In addition to services provisioned through cloud.gov, we have several services provisioned via [supplemental service brokers](https://github.com/GSA/usnotify-ssb) in AWS. Our AWS services are currently located in [several regions](https://github.com/GSA/usnotify-ssb#aws-accounts-and-regions-in-use) using Studio-controlled AWS accounts.

To send messages, we use Amazon Web Services SNS and SES. In addition, we use AWS Pinpoint to provision and manage phone numbers, short codes, and long codes for sending SMS.

In SNS, we have 3 topics for SMS receipts. These are not currently functional, so senders won't know the status of messages.

Through Pinpoint, the API needs at least one number so that the application itself can send SMS for authentication codes.

The API also has access to AWS S3 buckets for storing CSVs of messages and contact lists. It does not access a third S3 bucket that stores agency logos.

## New Relic

We are using [New Relic](https://one.newrelic.com/nr1-core?account=3389907) for application monitoring and error reporting. When requesting access to New Relic, ask to be added to the Benefits-Studio subaccount.

## Onboarding

- [ ] Join [the GSA GitHub org](https://github.com/GSA/GitHub-Administration#join-the-gsa-organization)
- [ ] Get permissions for the repos
- [ ] Get access to the cloud.gov org && spaces
- [ ] Get [access to AWS](https://handbook.tts.gsa.gov/launching-software/infrastructure/#cloud-service-provider-csp-sandbox-accounts), if necessary
- [ ] Get [access to New Relic](https://handbook.tts.gsa.gov/tools/new-relic/#how-do-i-get-access-to-new-relic), if necessary
- [ ] Create the local `.env` file by copying `sample.env` and running `./run.sh` within the `terraform/development` folder
- [ ] Do stuff!

## Setting up the infrastructure

These steps are required for new cloud.gov environments. Local development borrows SES & SNS infrastructure from the `notify-staging` cloud.gov space, so these steps are not required for new developers.

### Steps to do a clean prod deploy to cloud.gov

Steps for deploying production from scratch. These can be updated for a new cloud.gov environment by subbing out `prod` or `production` for your desired environment within the steps.

1. Deploy API app
    1. Update `terraform-production.yml` and `deploy-prod.yml` to point to the correct space and git branch.
    1. Ensure that the `domain` module is commented out in `terraform/production/main.tf`
    1. Run CI/CD pipeline on the `production` branch by opening a PR from `main` to `production`
    1. Create any necessary DNS records (check `notify-api-ses-production` service credentials for instructions) within https://github.com/18f/dns
    1. Follow the `Steps to prepare SES` below
    1. (Optional) if using a public API route, uncomment the `domain` module and re-trigger a deploy
1. Deploy Admin app
    1. Update `terraform-production.yml` and `deploy-prod.yml` to point to the correct space and git branch.
    1. Ensure that the `api_network_route` and `domain` modules are commented out in `terraform/production/main.tf`
    1. Run CI/CD pipeline on the `production` branch by opening a PR from `main` to `production`
    1. Create DNS records for `domain` module within https://github.com/18f/dns
    1. Uncomment the `api_network_route` and `domain` modules and re-trigger a deploy

### Steps to prepare SES

1. After the first deploy of the application with the SSB-brokered SES service completes:
    1. Log into the SES console and navigate to the SNS subscription page.
    1. Select "Request confirmation" for any subscriptions still in "Pending Confirmation" state
1. Find and replace instances in the repo of "testsender", "testreceiver" and "dispostable.com", with your origin and destination email addresses, which you verified in step 1 above.

TODO: create env vars for these origin and destination email addresses for the root service, and create new migrations to update postgres seed fixtures

### Steps to prepare SNS

#### Move SNS out of sandbox.

This should be complete for all regions Notify.gov has been deployed to or is currently planned to be deployed to.

1. Visit the SNS console for the region you will be sending from. Notes:
    1. SNS settings are per-region, so each environment must have its own region
    1. Pinpoint and SNS have confusing regional availability, so ensure both are available before submitting any requests.
1. Choose `Text messaging (SMS)` from the sidebar
1. Click the `Exit SMS Sandbox` button and submit the support request. This request should take at most a day to complete. Be sure to request a higher sending limit at the same time.

#### Request new phone numbers

1. Go to Pinpoint console for the same region you are using SNS in.
1. In the lefthand sidebar, go the `SMS and Voice` (bottom) and choose `Phone Numbers`
1. Under `Number Settings` choose `Request Phone Number`
1. Choose Toll-free number, tick SMS, untick Voice, choose `transactional`, hit next and then `request`
1. Select `Toll-free registrations` and `Create registration`
1. Select the number you just created and then `Register existing toll-free number`
1. Complete and submit the form. Approval usually takes about 2 weeks.
1. See the [run book](./run-book.md) for information on how to set those numbers.

Example answers for toll-free registration form

![example answers for toll-free registration form](./toll-free-registration.png)

# Using the logs

If you're using the `cf` CLI, you can run `cf logs notify-api-ENV` and/or `cf logs notify-admin-ENV` to stream logs in real time. Add `--recent` to get the last few logs, though logs often move pretty quickly.

For general log searching, [the cloud.gov Kibana instance](https://logs.fr.cloud.gov/) is powerful, though quite complex to get started. For shortcuts to errors, some team members have New Relic access.

The links below will open a filtered view with logs from both applications, which can then be filtered further. However, for the links to work, you need to paste them into the URL bar while *already* logged into and viewing the Kibana page. If not, you'll just be redirected to the generic dashboard.

Production: https://logs.fr.cloud.gov/app/discover#/view/218a6790-596d-11ee-a43a-090d426b9a38
Demo: https://logs.fr.cloud.gov/app/discover#/view/891392a0-596e-11ee-921a-1b6b2f4d89ed
Staging: https://logs.fr.cloud.gov/app/discover#/view/73d7c820-596e-11ee-a43a-090d426b9a38

Once in the view, you'll likely want to adjust the time range in the upper right of the page.

# Testing

```
# install dependencies, etc.
make bootstrap

make test
```

This will run:
- flake8 for code styling
- isort for import styling
- pytest for the test suite

On GitHub, in addition to these tests, we run:
- bandit for code security
- pip-audit for dependency vulnerabilities
- OWASP for dynamic scanning

## CI testing

We're using GitHub Actions. See [/.github](../.github/) for the configuration.

In addition to commit-triggered scans, the `daily_checks.yml` workflow runs the relevant dependency audits, static scan, and/or dynamic scans at 10am UTC each day. Developers will be notified of failures in daily scans by GitHub notifications.

### Nightly Scans

Within GitHub Actions, several scans take place every day to ensure security and compliance.


#### [daily-checks.yml](../.github/workflows/daily_checks.yml)

`daily-checks.yml` runs `pip-audit`, `bandit`, and `owasp` scans to ensure that any newly found vulnerabilities do not impact notify. Failures should be addressed quickly as they will also block the next attempted deploy.

#### [drift.yml](../.github/workflows/drift.yml)

`drift.yml` checks the deployed infrastructure against the expected configuration. A failure here is a flag to check audit logs for unexpected access and/or behavior and potentially destroy and re-deploy the application. Destruction and redeployment of all underlying infrastructure is an extreme remediation, and should only be attempted after ensuring that a good database backup is in hand.

## Manual testing

If you're checking out the system locally, you may want to create a user quickly.

`poetry run flask command create-test-user`

This will run an interactive prompt to create a user, and then mark that user as active. *Use a real mobile number* if you want to log in, as the SMS auth code will be sent here.

## To run a local OWASP scan

1. Run `make run-flask` from within the dev container.
2. On your host machine run:

```
docker run -v $(pwd):/zap/wrk/:rw --network="notify-network" -t owasp/zap2docker-weekly zap-api-scan.py -t http://dev:6011/docs/openapi.yml -f openapi -c zap.conf
```

The equivalent command if you are running the API locally:

```
docker run -v $(pwd):/zap/wrk/:rw -t owasp/zap2docker-weekly zap-api-scan.py -t http://host.docker.internal:6011/docs/openapi.yml -f openapi -c zap.conf -r report.html
```


# Deploying

We deploy automatically to cloud.gov for production, demo, and staging environments.

Deployment to staging runs via the [base deployment action](../.github/workflows/deploy.yml) on GitHub, which pulls credentials from GitHub's secrets store in the staging environment.

Deployment to demo runs via the [demo deployment action](../.github/workflows/deploy-demo.yml) on GitHub, which pulls credentials from GitHub's secrets store in the demo environment.

Deployment to production runs via the [production deployment action](../.github/workflows/deploy-prod.yml) on GitHub, which pulls credentials from GitHub's secrets store in the production environment.

The [action that we use](https://github.com/18F/cg-deploy-action) deploys using [a rolling strategy](https://docs.cloudfoundry.org/devguide/deploy-apps/rolling-deploy.html), so all deployments should have zero downtime.

The API has 3 deployment environments:

- Staging, which deploys from `main`
- Demo, which deploys from `production`
- Production, which deploys from `production`

Configurations for these are located in [the `deploy-config` folder](../deploy-config/).

In the event that a deployment includes a Terraform change, that change will run before any code is deployed to the environment. Each environment has its own Terraform GitHub Action to handle that change.

Failures in any of these GitHub workflows will be surfaced in the Pull Request related to the code change, and in the case of `checks.yml` actively prevent the PR from being merged. Failure in the Terraform workflow will not actively prevent the PR from being merged, but reviewers should not approve a PR with a failing terraform plan.

## Egress Proxy

The API app runs in a [restricted egress space](https://cloud.gov/docs/management/space-egress/).
This allows direct communication to cloud.gov-brokered services, but
not to other APIs that we require.

As part of the deploy, we create an
[egress proxy application](https://github.com/GSA/cg-egress-proxy) that allows traffic out of our
application to a select list of allowed domains.

Update the allowed domains by updating `deploy-config/egress_proxy/notify-api-<env>.allow.acl`
and deploying an updated version of the application throught he normal deploy process.

## Managing environment variables

For an environment variable to make its way into the cloud.gov environment, it *must* end up in the `manifest.yml` file. Based on the deployment approach described above, there are 2 ways for this to happen.

### Secret environment variables

Because secrets are pulled from GitHub, they must be passed from our action to the deploy action and then placed into `manifest.yml`. This means that they should be in a 4 places:

- [ ] The GitHub secrets store
- [ ] The deploy action in the `env` section using the format `{secrets.SECRET_NAME}`
- [ ] The deploy action in the `push_arguments` section using the format `--var SECRET_NAME="$SECRET_NAME"`
- [ ] The manifest using the format `((SECRET_NAME))`

### Public environment variables

Public env vars make up the configuration in `deploy-config`. These are pulled in together by the `--vars-file` line in the deploy action. To add or update one, it should be in 2 places:

- [ ] The relevant YAML file in `deploy-config` using the format `var_name: value`
- [ ] The manifest using the format `((var_name))`

## Sandbox environment

There is a sandbox space, complete with terraform and `deploy-config/sandbox.yml` file available
for experimenting with infrastructure changes without going through the full CI/CD cycle each time.

Rules for use:

1. Ensure that no other developer is using the environment, as there is nothing stopping changes from overwriting each other.
1. Clean up when you are done:
    - `terraform destroy` from within the `terraform/sandbox` directory will take care of the provisioned services
    - Delete the apps and routes shown in `cf apps` by running `cf delete APP_NAME -r`
    - Delete the space deployer you created by following the instructions within `terraform/sandbox/secrets.auto.tfvars`

### Deploying to the sandbox

1. Set up services:
    ```
    $ cd terraform/sandbox
    $ ../create_service_account.sh -s notify-sandbox -u <your-name>-terraform -m > secrets.auto.tfvars
    $ terraform init
    $ terraform plan
    $ terraform apply
    ```
1. start a poetry shell as a shortcut to load `.env` file variables: `$ poetry shell`
1. Output requirements.txt file: `poetry export --without-hashes --format=requirements.txt > requirements.txt`
1. Deploy the application:
  ```
  cf push --vars-file deploy-config/sandbox.yml --var NEW_RELIC_LICENSE_KEY=$NEW_RELIC_LICENSE_KEY
  ```


# Database management

## Initial state

In Notify, several aspects of the system are loaded into the database via migration. This means that
application setup requires loading and overwriting historical data in order to arrive at the current
configuration.

[Here are notes](https://docs.google.com/document/d/1ZgiUtJFvRBKBxB1ehiry2Dup0Q5iIwbdCU5spuqUFTo/edit#)
about what is loaded into which tables, and some plans for how we might manage that in the future.

Flask does not seem to have a great way to squash migrations, but rather wants you to recreate them
from the DB structure. This means it's easy to recreate the tables, but hard to recreate the initial data.

## Data Model Diagram

A diagram of Notify's data model is available [in our compliance repo](https://github.com/GSA/us-notify-compliance/blob/main/diagrams/rendered/apps/data.logical.pdf).

## Migrations

Create a migration:

```
flask db migrate
```

Trim any auto-generated stuff down to what you want, and manually rename it to be in numerical order.
We should only have one migration branch.

Running migrations locally:

```
flask db upgrade
```

This should happen automatically on cloud.gov, but if you need to run a one-off migration for some reason:

```
cf run-task notifications-api-staging --commmand "flask db upgrade" --name db-upgrade
```

## Purging user data

There is a Flask command to wipe user-created data (users, services, etc.).

The command should stop itself if it's run in a production environment, but, you know, please don't run it
in a production environment.

Running locally: 

```
flask command purge_functional_test_data -u <functional tests user name prefix>
```

Running on cloud.gov:

```
cf run-task notify-api "flask command purge_functional_test_data -u <functional tests user name prefix>"
```


# One-off tasks

For these, we're using Flask commands, which live in [`/app/commands.py`](../app/commands.py).

This includes things that might be one-time operations! If we're running it on production, it should be a Flask 
command Using a command allows the operation to be tested, both with `pytest` and with trial runs in staging.

To see information about available commands, you can get a list with:

`poetry run flask command`

Appending `--help` to any command will give you more information about parameters.

To run a command on cloud.gov, use this format:

`cf run-task CLOUD-GOV-APP --commmand "YOUR COMMAND HERE" --name YOUR-COMMAND`

[Here's more documentation](https://docs.cloudfoundry.org/devguide/using-tasks.html) about Cloud Foundry tasks.

# How messages are queued and sent

There are several ways for notifications to come into the API.

- Messages sent through the API enter through `app/notifications/post_notifications.py`
- One-off messages sent from the UI enter through `create_one_off_notification` in `app/service/rest.py`
- CSV uploads enter through `app/job/rest.py`

API messages and one-off UI messages come in one at a time, and take slightly-separate routes
that both end up at `persist_notification`, which writes to the database, and `provider_tasks.deliver_sms`,
which enqueues the sending.

For CSV uploads, the CSV is first stored in S3 and queued as a `Job`. When the job runs, it iterates
through the rows, running `process_job.save_sms` to send notifications through `persist_notification` and 
`provider_tasks.deliver_sms`.

# Writing public APIs

_Most of the API endpoints in this repo are for internal use. These are all defined within top-level folders under `app/` and tend to have the structure `app/<feature>/rest.py`._

## Overview

Public APIs are intended for use by services and are all located under `app/v2/` to distinguish them from internal endpoints. Originally we did have a "v1" public API, where we tried to reuse / expose existing internal endpoints. The needs for public APIs are sufficiently different that we decided to separate them out. Any "v1" endpoints that remain are now purely internal and no longer exposed to services.

## Documenting APIs

New and existing APIs should be documented within [openapi.yml](./openapi.yml). Tools to help
with editing this file:

* [OpenAPI Editor for VSCode](https://marketplace.visualstudio.com/items?itemName=42Crunch.vscode-openapi)
* [OpenAPI specification](https://spec.openapis.org/oas/v3.0.2)


## New APIs

Here are some pointers for how we write public API endpoints.

### Each endpoint should be in its own file in a feature folder

Example: `app/v2/inbound_sms/get_inbound_sms.py`

This helps keep the file size manageable but does mean a bit more work to register each endpoint if we have many that are related. Note that internal endpoints are grouped differently: in large `rest.py` files.

### Each group of endpoints should have an `__init__.py` file

Example:

```
from flask import Blueprint

from app.v2.errors import register_errors

v2_notification_blueprint = Blueprint("v2_notifications", __name__, url_prefix='/v2/notifications')

register_errors(v2_notification_blueprint)
```

Note that the error handling setup by `register_errors` (defined in [`app/v2/errors.py`](../app/v2/errors.py)) for public API endpoints is different to that for internal endpoints (defined in [`app/errors.py`](../app/errors.py)).

### Each endpoint should have an adapter in each API client

Example: [Ruby Client adapter to get template by ID](https://github.com/alphagov/notifications-ruby-client/blob/d82c85452753b97e8f0d0308c2262023d75d0412/lib/notifications/client.rb#L110-L115).

All our clients should fully support all of our public APIs.

Each adapter should be documented in each client ([example](https://github.com/alphagov/notifications-ruby-client/blob/d82c85452753b97e8f0d0308c2262023d75d0412/DOCUMENTATION.md#get-a-template-by-id)). We should also document each public API endpoint in our generic API docs ([example](https://github.com/alphagov/notifications-tech-docs/blob/2700f1164f9d644c87e4c72ad7223952288e8a83/source/documentation/_api_docs.md#send-a-text-message)). Note that internal endpoints are not documented anywhere.

### Each endpoint should specify the authentication it requires

This is done as part of registering the blueprint in `app/__init__.py` e.g.

```
post_letter.before_request(requires_auth)
application.register_blueprint(post_letter)
```

# API Usage

## Connecting to the API

To make life easier, the [UK API client libraries](https://www.notifications.service.gov.uk/documentation) are compatible with Notify and the [UK API Documentation](https://docs.notifications.service.gov.uk/rest-api.html) is applicable.

For a usage example, see [our Python demo](https://github.com/GSA/notify-python-demo).

An API key can be created at https://HOSTNAME/services/YOUR_SERVICE_ID/api/keys. This is the same API key that is referenced as `USER_API_TOKEN` below.

## Postman Documentation

Internal-only  [documentation for exploring the API using Postman](https://docs.google.com/document/d/1S5c-LxuQLhAtZQKKsECmsllVGmBe34Z195sbRVEzUgw/edit#heading=h.134fqdup8d3m)


## Using OpenAPI documentation

An [OpenAPI](https://www.openapis.org/) specification [file](./openapi.yml) can be found at https://notify-staging.app.cloud.gov/docs/openapi.yml.

See [writing-public-apis.md](./writing-public-apis.md) for links to tools to make it easier to use the OpenAPI spec within VSCode.

### Retrieving a jwt-encoded bearer token for use

On a mac, run:

#### Admin UI token

The admin UI token is required for any of the `internal-api` tagged methods. To create one and copy it to your pasteboard, run:

```
flask command create-admin-jwt | tail -n 1 | pbcopy
```

#### User token

A user token is required for any of the `external-api` tagged methods. To create one and copy it to your pasteboard, run:

```
flask command create-user-jwt --token=<USER_API_TOKEN> | tail -n 1 | pbcopy
```

### Disable token expiration checking in development

Because jwt tokens expire so quickly, the development server can be set to allow tokens older than 30 seconds:

```
env ALLOW_EXPIRED_API_TOKEN=1 make run-flask
```



# Queues and tasks

The API puts tasks into Celery queues for dispatch.

There are a bunch of queues:
- priority tasks
- database tasks
- send sms tasks
- send email tasks
- research mode tasks
- reporting tasks
- job tasks
- retry tasks
- notify internal tasks
- service callbacks
- service callbacks retry
- letter tasks
- sms callbacks
- antivirus tasks
- save api email tasks
- save api sms tasks

And these tasks:
- check for missing rows in completed jobs
- check for services with high failure rates or sending to tv numbers
- check if letters still in created
- check if letters still pending virus check
- check job status
- create fake letter response file
- create nightly billing
- create nightly billing for day
- create nightly notification status
- create nightly notification status for service and day
- delete email notifications
- delete inbound sms
- delete invitations
- delete letter notifications
- delete notifications for service and type
- delete notifications older than retention
- delete sms notifications
- delete verify codes
- deliver email
- deliver sms
- process incomplete jobs
- process job
- process returned letters list
- process ses result
- process virus scan error
- process virus scan failed
- raise alert if letter notifications still sending
- raise alert if no letter ack file
- record daily sorted counts
- remove letter jobs
- remove sms email jobs
- replay created notifications
- run scheduled jobs
- save api email
- save api sms
- save daily notification processing time
- save email
- save letter
- save sms
- send complaint
- send delivery status
- send inbound sms
- switch current sms provider on slow delivery
- tend providers back to middle
- timeout sending notifications
- update billable units for letter
- update letter notifications statuses
- update letter notifications to error
- update letter notifications to sent
- update validation failed for templated letter

## Priority queue

For tasks that should happen before other stuff, there's a priority queue. Platform admins
can set templates to use this queue.

Currently, this queue doesn't do anything special. If the normal queue is very busy, it's
possible that this queue will be faster merely because it's shorter. By the same logic, a 
busy priority queue is likely to be _slower_ than the normal queue

## Celery scheduled tasks

After scheduling some tasks, run celery beat to get them moving:

```
make run-celery-beat
```






US Notify
=========

System Description
------------------

US Notify is a service being developed by the TTS Public Benefits Studio to increase the availability of
SMS and email notifications to Federal, State, and Local Benefits agencies.

Agencies that sign up will be able to create and use personalized message templates for sending
notifications to members of the public regarding their benefits. These could include reminders
about upcoming enrollment deadlines and tasks, or information about upcoming appointments, events,
or services.

The templates are sent by the agency using one of two methods:

* using the US Notify API to send a message to a given recipient with given personalization values
* using the US Notify website to upload a CSV file of recipients and their personalization values, one row per message

### Environment

US Notify is comprised of two applications both running on cloud.gov:

* Admin, a Flask website running on the python_buildpack which hosts agency user-facing UI
* API, a Flask application running on the python_buildpack hosting the US Notify API

US Notify utilizes several cloud.gov-provided services:

* S3 buckets for temporary file storage
* Elasticache (redis) for cacheing data and enqueueing background tasks
* RDS (PostgreSQL) for system data storage

US Notify also provisions and uses two AWS services via a [supplemental service broker](https://github.com/GSA/usnotify-ssb):

* [SNS](https://aws.amazon.com/sns/) for sending SMS messages
* [SES](https://aws.amazon.com/ses/) for sending email messages

For further details of the system and how it connects to supporting services, see the [application boundary diagram](https://github.com/GSA/us-notify-compliance/blob/main/diagrams/rendered/apps/application.boundary.png)


Run Book
========

Policies and Procedures needed before and during US Notify Operations. Many of these policies are taken from the Notify.gov System Security & Privacy Plan (SSPP).

Any changes to policies and procedures defined both here and in the SSPP must be kept in sync, and should be done collaboratively with the System ISSO and ISSM to ensure
that the security of the system is maintained.

1. [Alerts, Notifications, Monitoring](#alerts)
1. [Restaging Apps](#restaging-apps)
1. [Smoke-testing the App](#smoke-testing)
1. [Configuration Management](#cm)
1. [DNS Changes](#dns)
1. [Known Gotchas](#gotcha)
1. [User Account Management](#ac)
1. [SMS Phone Number Management](#phone-numbers)

## <a name="alerts"></a> Alerts, Notifications, Monitoring

Operational alerts are posted to the [#pb-notify-alerts](https://gsa-tts.slack.com/archives/C04U9BGHUDB) Slack channel. Please join this channel and enable push notifications for all messages whenever you are on call.

[NewRelic](https://one.newrelic.com/) is being used for monitoring the application. [NewRelic Dashboard](https://onenr.io/08wokrnrvwx) can be filtered by environment and API, Admin, or Both.

[Cloud.gov Logging](https://logs.fr.cloud.gov/) is used to view and search application and platform logs.

In addition to the application logs, there are several tables in the application that store useful information for audit logging purposes:

* `events`
* the various `*_history` tables


## <a name="restaging-apps"></a> Restaging Apps

Our apps must be restaged whenever cloud.gov releases updates to buildpacks. Cloud.gov will send email notifications whenever buildpack updates affect a deployed app.

Restaging the apps rebuilds them with the new buildpack, enabling us to take advantage of whatever bugfixes or security updates are present in the new buildpack.

There are two GitHub Actions that automate this process. Each are run manually and must be run once for each environment to enable testing any changes in staging before running within demo and production environments.

When `notify-api-<env>`, `notify-admin-<env>`, `egress-proxy-notify-api-<env>`, and/or `egress-proxy-notify-admin-<env>` need to be restaged:

1. Navigate to [the Restage apps GitHub Action](https://github.com/GSA/notifications-api/actions/workflows/restage-apps.yml)
1. Click the `Run workflow` button to open a popup
1. Leave `Use workflow from` on it's default of `Branch: main`
1. Select the environment you need to restage from the dropdown
1. Click `Run workflow` within the popup
1. Repeat for other environments

When `ssb-sms`, and/or `ssb-smtp` need to be restaged:

1. Navigate to the [SSB Restage apps GitHub Action](https://github.com/GSA/usnotify-ssb/actions/workflows/restage-apps.yml)
1. Click the `Run workflow` button to open a popup
1. Leave `Use workflow from` on it's default of `Branch: main`
1. Select the environment (either `staging` or `production`) you need to restage from the dropdown
1. Click `Run workflow` within the popup
1. Repeat for other environments

When `ssb-devel-sms` and/or `ssb-devel-smtp` need to be restaged:

1. Navigate to the [SSB Restage apps GitHub Action](https://github.com/GSA/usnotify-ssb/actions/workflows/restage-apps.yml)
1. Click the `Run workflow` button to open a popup
1. Leave `Use workflow from` on it's default of `Branch: main`
1. Select the `development` environment from the dropdown
1. Click `Run workflow` within the popup


## <a name="smoke-testing"></a> Smoke-testing the App

To ensure that notifications are passing through the application properly, the following steps can be taken to ensure all parts are operating correctly:

1. Send yourself a password reset email. This will verify SES integration. The email can be deleted once received if you don't wish to change your password.
1. Log into the app. This will verify SNS integration for a one-off message.
1. Upload a CSV and schedule send for the soonest time after "Now". This will verify S3 connections as well as scheduler and worker processes are running properly.

## <a name="cm"></a> Configuration Management

Also known as: **How to move code from my machine to production**

### Common Policies and Procedures

1. All changes must be made in a feature branch and opened as a PR targetting the `main` branch.
1. All PRs must be approved by another developer
1. PRs to `main` and `production` branches must be merged by a someone with the `Administrator` role.
1. PR documentation includes a Security Impact Analysis
1. PRs that will impact the Security Posture must be approved by the US Notify ISSO.
1. Any PRs waiting for approval should be talked about during daily Standup meetings.

### notifications-api & notifications-admin

1. Changes are deployed to the `staging` environment after a successful `checks.yml` run on `main` branch. Branch Protections prevent pushing directly to `main`
1. Changes are deployed to the `demo` _and_ `production` environments after merging `main` into `production`. Branch Protections prevent pushing directly to `production`

### usnotify-ssb

1. Changes are deployed to `staging` and `production` environments after merging to the `main` branch. The `staging` deployment must be successful before `production` is attempted. Branch Protections prevent pushing directly to `main`

### ttsnotify-brokerpak-sms

1. A new release is created by pushing a tag to the repository on the `main` branch.
1. To include the new version in released SSB code, create a PR in the `usnotify-ssb` repo updating the version in use in `app-setup-sms.sh`

### datagov-brokerpak-smtp

1. To include new verisons of the SMTP brokerpak in released SSB code, create a PR in the `usnotify-ssb` repo updating the version in use in `app-setup-smtp.sh`

### Vulnerability Mitigation Changes

US_Notify Administrators are responsible for ensuring that remediations for vulnerabilities are implemented. Response times vary based on the level of vulnerability as follows:

* Critical (Very High) - 15 days
* High - 30 days
* Medium - 90 days
* Low - 180 days
* Informational - 365 days (depending on the analysis of the issue)

## <a name="dns"></a> DNS Changes

Notify.gov DNS records are maintained within [the 18f/dns repository](https://github.com/18F/dns/blob/main/terraform/notify.gov.tf). To create new DNS records for notify.gov or any subdomains:

1. Update the `notify.gov.tf` terraform to update oƒr create the new records within Route53 and push the branch to the 18f/dns repository.
1. Open a PR.
1. Verify that the plan output within circleci creates the records that you expect.
1. Request a PR review from the 18F/tts-tech-portfolio team
1. Once the PR is approved and merged, verify that the apply step happened correctly within [CircleCI](https://app.circleci.com/pipelines/github/18F/dns)

## Exporting test results for compliance monitoring

- Head to https://github.com/GSA/notifications-api/actions/workflows/daily_checks.yml
- Open the most recent scan (it should be today's)
- Scroll down to "Artifacts", click to download the .zip of OWASP ZAP results
- Rename to `api_zap_scan_DATE.zip` and add it to 🔒 https://drive.google.com/drive/folders/1CFO-hFf9UjzU2JsZxdZeGRfw-a47u7e1
- Click any of the jobs to open the logs
- In top right of logs, click the gear icon
- Select "Download log archive" to download a .zip of the test output for all jobs
- Rename to `api_static_scan_DATE.zip` and add it to 🔒 https://drive.google.com/drive/folders/1dSe9H7Ag_hLfi5hmQDB2ktWaDwWSf4_R
- Repeat for https://github.com/GSA/notifications-admin/actions/workflows/daily_checks.yml


## <a name="gotcha"></a> Known Gotchas

### SSB Service Bindings are failing

<dl>
<dt>Problem:</dt>
<dd>Creating or deleting service keys is failing. SSB Logs reference failing to verify certificate/certificate valid for <code>GUID A</code> but not for <code>GUID B</code></dd>
<dt>Solution:</dt>
<dd>Restage SSB apps using the <a href="#restaging-apps">restage apps action</a>
</dl>

### SNS Topic Subscriptions Don't Succeed

<dl>
<dt>Problem:</dt>
<dd>When deploying a new environment, a race condition prevents SNS topic subscriptions from being successfully verified on the AWS side</dd>
<dt>Solution:</dt>
<dd>Manually re-request subscription confirmation from the AWS Console. </dd>
</dl>

## <a name="ac"></a> User Account Management

Important policies:

* Infrastructure Accounts and Application Platform Administrators must be approved by the System Owner (Amy) before creation, but people with `Administrator` role can actually do the creation and role assignments.
* At least one agency partner must act as the `User Manager` for their service, with permissions to manage their team according to their agency's policies and procedures.
* All users must utilize `.gov` email addresses.
* Users who leave the team or otherwise have role changes must have their accounts updated to reflect the new roles required (or disabled) within 14 days.
* SpaceDeployer credentials must be rotated within 14 days of anyone with SpaceDeveloper cloud.gov access leaving the team.
* A user report must be created annually (See AC-2(j)). `make cloudgov-user-report` can be used to create a full report of all cloud.gov users.

### Types of Infrastructure Users

| Role Name | System | Permissions | Who | Responsibilities |
| --------- | ------ | ----------- | --- | ---------------- |
| Administrator | GitHub | Admin | PBS Fed | Approve & Merge PRs into main and production |
| Administrator | AWS | `NotifyAdministrators` IAM UserGroup | PBS Fed | Read audit logs, verify & fix any AWS service issues within Production AWS account |
| Administrator | Cloud.gov | `OrgManager` | PBS Fed | Manage cloud.gov roles and permissions. Access to production spaces |
| DevOps Engineer | Cloud.gov | `SpaceManager` | PBS Fed or Contractor | Access to non-production spaces |
| DevOps Engineer | AWS | `NotifyAdministrators` IAM UserGroup | PBS Fed or Contractor | Access to non-production AWS accounts to verify & fix any AWS issues in the lower environments |
| Engineer | GitHub | Write | PBS Fed or Contractor | Write code & issues, submit PRs |

### Types of Application Users

| Role Name | Permissions | Who | Responsibilities |
| --------- | ----------- | --- | ---------------- |
| Platform Administrator | `platform_admin` | PBS Fed | Administer system settings within US Notify across Services |
| User Manager | `MANAGE_USERS` | Agency Partner | Manage service team members |
| User | any except `MANAGE_USERS` | Agency Partner | Use US Notify |

### Service Accounts

| Role Name | System | Permissions | Notes |
| --------- | ------ | ----------- | ----- |
| Cloud.gov Service Account | Cloud.gov | `OrgManager` and `SpaceDeveloper` | Creds stored in GitHub Environment secrets within api and admin app repos |
| SSB Deployment Account | AWS | `IAMFullAccess` | Creds stored in GitHub Environment secrets within usnotify-ssb repo |
| SSB Cloud.gov Service Account | Cloud.gov | `SpaceDeveloper` | Creds stored in GitHub Environment secrets within usnotify-ssb repo |
| SSB AWS Accounts | AWS | `sms_broker` or `smtp_broker` IAM role | Creds created and maintained by usnotify-ssb terraform |

## <a name="phone-numbers"></a> SMS Phone Number Management

See [Infrastructure Overview](./infra-overview.md#request-new-phone-numbers) for information about SMS phone numbers in AWS.

Once you have a number, it must be set in the app in one of two ways:

* For the default phone number, to be used by Notify itself for OTP codes and the default from number for services, set the phone number as the `AWS_US_TOLL_FREE_NUMBER` ENV variable in the environment you are creating
* For service-specific phone numbers, set the phone number in the Service's `Text message senders` in the settings tab.

### Current Production Phone Numbers

* +18447952263 - in use as default number. Notify's OTP messages and trial service messages are sent from this number
* +18447891134 - to be used by Pilot Partner 1
* +18888402596 - to be used by Pilot Partner 2


Data Storage Policies & Procedures
==================================


Potential PII Locations
-----------------------

### Tables

#### users<sup>1</sup>

* name
* email_address
* mobile_number

#### invited_users<sup>1</sup>

* email_address

#### invited_organization_users<sup>1</sup>

* email_address

#### jobs

No db data is PII, but each job has a csv file in s3 containing phone numbers and personalization data.

#### notifications

* to
* normalized_to
* _personalization<sup>2</sup>
* phone_prefix<sup>3</sup>

#### notification_history

* phone_prefix<sup>3</sup>

#### inbound_sms

* content<sup>2</sup>
* user_number

#### events

* data (contains user IP addresses)<sup>1</sup>

### Notes

#### Note 1.

Users and invited users are Federal, State, or Local government employees or contractors. Members of the general public are _not_ users of the system

#### Note 2.

Field-level encryption is used on these fields.

Details on encryption schemes and algorithms can be found in [SC-28(1)](https://github.com/GSA/us-notify-compliance/blob/main/dist/system-security-plans/lato/sc-28.1.md)

#### Note 3.

Probably not PII, this is the country code of the phone.


Data Retention Policy
---------------------

Seven (7) days by default. Each service can be set with a custom policy via `ServiceDataRetention` by a Platform Admin. The `ServiceDataRetention` setting applies per-service and per-message type and controls both entries in the `notifications` table as well as `csv` contact files uploaded to s3

Data cleanup is controlled by several tasks in the `nightly_tasks.py` file, kicked off by Celery Beat.
