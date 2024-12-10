import json
import os
import re
from datetime import timedelta

from boto3 import client
from flask import current_app

from app.clients import AWS_CLIENT_CONFIG, Client
from app.cloudfoundry_config import cloud_config
from app.exceptions import NotificationTechnicalFailureException
from app.utils import hilite, utc_now


class AwsCloudwatchClient(Client):
    """
    This client is responsible for retrieving sms delivery receipts from cloudwatch.
    """

    def init_app(self, current_app, *args, **kwargs):
        if os.getenv("LOCALSTACK_ENDPOINT_URL"):
            self._client = client(
                "logs",
                region_name=cloud_config.sns_region,
                aws_access_key_id=cloud_config.sns_access_key,
                aws_secret_access_key=cloud_config.sns_secret_key,
                config=AWS_CLIENT_CONFIG,
                endpoint_url=os.getenv("LOCALSTACK_ENDPOINT_URL"),
            )
            self._is_localstack = True
        else:
            self._client = client(
                "logs",
                region_name=cloud_config.sns_region,
                aws_access_key_id=cloud_config.sns_access_key,
                aws_secret_access_key=cloud_config.sns_secret_key,
                config=AWS_CLIENT_CONFIG,
            )
            self._is_localstack = False

        super(Client, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self._valid_sender_regex = re.compile(r"^\+?\d{5,14}$")

    @property
    def name(self):
        return "cloudwatch"

    def is_localstack(self):
        return self._is_localstack

    def _get_log(self, my_filter, log_group_name, sent_at):
        # Check all cloudwatch logs from the time the notification was sent (currently 5 minutes previously) until now
        now = utc_now()
        beginning = sent_at
        next_token = None
        all_log_events = []
        current_app.logger.info(f"START TIME {beginning} END TIME {now}")
        # There has been a change somewhere and the time range we were previously using has become too
        # narrow or wrong in some way, so events can't be found.  For the time being, adjust by adding
        # a buffer on each side of 12 hours.
        TWELVE_HOURS = 12 * 60 * 60 * 1000
        while True:
            if next_token:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    filterPattern=my_filter,
                    nextToken=next_token,
                    startTime=int(beginning.timestamp() * 1000) - TWELVE_HOURS,
                    endTime=int(now.timestamp() * 1000) + TWELVE_HOURS,
                )
            else:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    filterPattern=my_filter,
                    startTime=int(beginning.timestamp() * 1000) - TWELVE_HOURS,
                    endTime=int(now.timestamp() * 1000) + TWELVE_HOURS,
                )
            log_events = response.get("events", [])
            all_log_events.extend(log_events)
            if len(log_events) > 0:
                # We found it

                break
            next_token = response.get("nextToken")
            if not next_token:
                break
        return all_log_events

    def _extract_account_number(self, ses_domain_arn):
        account_number = ses_domain_arn.split(":")
        return account_number

    def warn_if_dev_is_opted_out(self, provider_response, notification_id):
        if (
            "is opted out" in provider_response.lower()
            or "has blocked sms" in provider_response.lower()
        ):
            if os.getenv("NOTIFY_ENVIRONMENT") in ["development", "test"]:
                ansi_red = "\033[31m"
                ansi_reset = "\033[0m"
                logline = (
                    ansi_red
                    + f"The phone number for notification_id {notification_id} is OPTED OUT. You need to opt back in"
                    + ansi_reset
                )
                current_app.logger.warning(logline)
                return logline
        return None

    def check_sms(self, message_id, notification_id, created_at):
        region = cloud_config.sns_region
        # TODO this clumsy approach to getting the account number will be fixed as part of notify-api #258
        account_number = self._extract_account_number(cloud_config.ses_domain_arn)

        time_now = utc_now()
        log_group_name = f"sns/{region}/{account_number[4]}/DirectPublishToPhoneNumber"
        filter_pattern = '{$.notification.messageId="XXXXX"}'
        filter_pattern = filter_pattern.replace("XXXXX", message_id)
        all_log_events = self._get_log(filter_pattern, log_group_name, created_at)
        if all_log_events and len(all_log_events) > 0:
            event = all_log_events[0]
            message = json.loads(event["message"])
            self.warn_if_dev_is_opted_out(
                message["delivery"]["providerResponse"], notification_id
            )
            # Here we map the answer from aws to the message_id.
            # Previously, in send_to_providers, we mapped the job_id and row number
            # to the message id.  And on the admin side we mapped the csv filename
            # to the job_id.  So by tracing through all the logs we can go:
            # filename->job_id->message_id->what really happened
            current_app.logger.info(
                hilite(f"DELIVERED: {message} for message_id {message_id}")
            )
            return (
                "success",
                message["delivery"]["providerResponse"],
                message["delivery"].get("phoneCarrier", "Unknown Carrier"),
            )

        log_group_name = (
            f"sns/{region}/{account_number[4]}/DirectPublishToPhoneNumber/Failure"
        )
        all_failed_events = self._get_log(filter_pattern, log_group_name, created_at)
        if all_failed_events and len(all_failed_events) > 0:
            event = all_failed_events[0]
            message = json.loads(event["message"])
            self.warn_if_dev_is_opted_out(
                message["delivery"]["providerResponse"], notification_id
            )

            current_app.logger.info(
                hilite(f"FAILED: {message} for message_id {message_id}")
            )
            return (
                "failure",
                message["delivery"]["providerResponse"],
                message["delivery"].get("phoneCarrier", "Unknown Carrier"),
            )

        if time_now > (created_at + timedelta(hours=73)):
            # see app/models.py Notification. This message corresponds to "permanent-failure",
            # but we are copy/pasting here to avoid circular imports.
            return "failure", "Unable to find carrier response."
        raise NotificationTechnicalFailureException(
            f"No event found for message_id {message_id} notification_id {notification_id}"
        )
