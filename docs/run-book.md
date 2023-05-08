Run Book
========

Policies and Procedures needed before and during US Notify Operations. Many of these policies are taken from the U.S. Notify System Security & Privacy Plan (SSPP).

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

U.S. Notify DNS records are maintained within [the 18f/dns repository](https://github.com/18F/dns/blob/main/terraform/notify.gov.tf). To create new DNS records for notify.gov or any subdomains:

1. Update the `notify.gov.tf` terraform to update or create the new records within Route53 and push the branch to the 18f/dns repository.
1. Open a PR.
1. Verify that the plan output within circleci creates the records that you expect.
1. Request a PR review from the 18F/tts-tech-portfolio team
1. Once the PR is approved and merged, verify that the apply step happened correctly within [CircleCI](https://app.circleci.com/pipelines/github/18F/dns)


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
