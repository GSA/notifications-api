US Notify
=========

System Description
------------------

US Notify is a service being developed by the TTS Benefits Studio to increase the availability of
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

US Notify also provides access to two AWS services via a supplemental service broker:

* SNS for sending SMS messages
* SES for sending email messages

For further details of the system and how it connects to supporting services, see the [application boundary diagram](https://github.com/GSA/us-notify-compliance/blob/main/diagrams/rendered/apps/application.boundary.png)
