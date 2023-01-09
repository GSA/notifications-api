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
