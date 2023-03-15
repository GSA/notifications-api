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

### Development

There are several remote services required for local development:

* s3
* ses
* sns

Credentials for these services are created by running:

1. `cd terraform/development`
1. `./run.sh`

This will append credentials to your `.env` file. You will need to manually clean up any prior runs from that file if you run that command again.

Offboarding: Service key bindings can be cleaned up from cloud.gov by running `./run.sh -d` yourself, or another developer running `./run.sh -d -u USER_TO_CLEANUP`

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

### Steps to prepare SES

1. After the first deploy of the application with the SSB-brokered SES service completes:
    1. Log into the SES console and navigate to the SNS subscription page.
    1. Select "Request confirmation" for any subscriptions still in "Pending Confirmation" state
1. Find and replace instances in the repo of "testsender", "testreceiver" and "dispostable.com", with your origin and destination email addresses, which you verified in step 1 above.

TODO: create env vars for these origin and destination email addresses for the root service, and create new migrations to update postgres seed fixtures

### Steps to prepare SNS

#### Move SNS out of sandbox.

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
1. Set this phone number as the `AWS_US_TOLL_FREE_NUMBER` in the environment you are creating
