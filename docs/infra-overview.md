# Infrastructure overview

A diagram of the system is available [in our compliance repo](https://github.com/GSA/us-notify-compliance/blob/main/diagrams/rendered/apps/application.boundary.png).

Notify is a Flask application running on [cloud.gov](https://cloud.gov), which also brokers access to a PostgreSQL database and Redis store.

In addition to the Flask app, Notify uses Celery to manage the task queue. Celery stores tasks in Redis.

## Terraform

The cloud.gov environment is configured with Terraform. See [the `terraform` folder](../terraform/) to learn about that.

## AWS

In addition to services provisioned through cloud.gov, we have several services provisioned directly in AWS. Our AWS services are currently located in the us-west-2 region using the tts-sandbox account. We plan to move to GovCloud shortly.

To send messages, we use Amazon Web Services SNS and SES. In addition, we use AWS Pinpoint to provision and manage phone numbers, short codes, and long codes for sending SMS.

In SES, we are currently using the "sandbox" mode. This requires email addresses to be pre-registered in the AWS console in order to receive emails. The DKIM settings live under the verified domain entry.

In SNS, we have 3 topics for SMS receipts. These are not currently functional, so senders won't know the status of messages.

Through Pinpoint, the API needs at least one number so that the application itself can send SMS for authentication codes.

The API also has access to AWS S3 buckets for storing CSVs of messages and contact lists. It does not access a third S3 bucket that stores agency logos.

We may be able to provision these services through cloud.gov, as well. In addition to [s3 support](https://cloud.gov/docs/services/s3/), there is [an SES brokerpak](https://github.com/GSA-TTS/datagov-brokerpak-smtp) and work on an SNS brokerpak.

## New Relic

We are using [New Relic](https://one.newrelic.com/nr1-core?account=3389907) for application monitoring and error reporting. When requesting access to New Relic, ask to be added to the Benefits-Studio subaccount.

## Onboarding

- [ ] Join [the GSA GitHub org](https://github.com/GSA/GitHub-Administration#join-the-gsa-organization)
- [ ] Get permissions for the repos
- [ ] Get access to the cloud.gov org && space
- [ ] Get [access to AWS](https://handbook.tts.gsa.gov/launching-software/infrastructure/#cloud-service-provider-csp-sandbox-accounts), if necessary
- [ ] Get [access to New Relic](https://handbook.tts.gsa.gov/tools/new-relic/#how-do-i-get-access-to-new-relic), if necessary
- [ ] Pull down creds from cloud.gov and create the local .env file
- [ ] Do stuff!

## Setting up the infrastructure

### Steps to prepare SES

1. Go to SES console for \$AWS_REGION and create new origin and destination emails. AWS will send a verification via email which you'll need to complete.
2. Find and replace instances in the repo of "testsender", "testreceiver" and "dispostable.com", with your origin and destination email addresses, which you verified in step 1 above.

TODO: create env vars for these origin and destination email addresses for the root service, and create new migrations to update postgres seed fixtures

### Steps to prepare SNS

1. Go to Pinpoints console for \$AWS_PINPOINT_REGION and choose "create new project", then "configure for sms"
2. Tick the box at the top to enable SMS, choose "transactional" as the default type and save
3. In the lefthand sidebar, go the "SMS and Voice" (bottom) and choose "Phone Numbers"
4. Under "Number Settings" choose "Request Phone Number"
5. Choose Toll-free number, tick SMS, untick Voice, choose "transactional", hit next and then "request"
6. Go to SNS console for \$AWS_PINPOINT_REGION, look at lefthand sidebar under "Mobile" and go to "Text Messaging (SMS)"
7. Scroll down to "Sandbox destination phone numbers" and tap "Add phone number" then follow the steps to verify (you'll need to be able to retrieve a code sent to each number)

At this point, you _should_ be able to complete both the email and phone verification steps of the Notify user sign up process! 🎉
