import json
import os
import re
import time

from boto3 import client
from flask import current_app

from app.clients import AWS_CLIENT_CONFIG, Client
from app.cloudfoundry_config import cloud_config


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
        now = round(time.time() * 1000)
        beginning = sent_at
        next_token = None
        all_log_events = []
        while True:
            if next_token:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    filterPattern=my_filter,
                    nextToken=next_token,
                    startTime=beginning,
                    endTime=now,
                )
            else:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    filterPattern=my_filter,
                    startTime=beginning,
                    endTime=now,
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

    def _extract_account_number(self, ses_domain_arn, region):
        account_number = ses_domain_arn
        # handle cloud.gov case
        if "aws-us-gov" in account_number:
            account_number = account_number.replace(f"arn:aws-us-gov:ses:{region}:", "")
            account_number = account_number.split(":")
            account_number = account_number[0]
        # handle staging case
        else:
            account_number = account_number.replace(f"arn:aws:ses:{region}:", "")
            account_number = account_number.split(":")
            account_number = account_number[0]
        return account_number

    def check_sms(self, message_id, notification_id, created_at):
        region = cloud_config.sns_region
        # TODO this clumsy approach to getting the account number will be fixed as part of notify-api #258
        account_number = self._extract_account_number(
            cloud_config.ses_domain_arn, region
        )

        log_group_name = f"sns/{region}/{account_number}/DirectPublishToPhoneNumber"
        current_app.logger.info(
            f"Log group name: {log_group_name} message id: {message_id}"
        )
        filter_pattern = '{$.notification.messageId="XXXXX"}'
        filter_pattern = filter_pattern.replace("XXXXX", message_id)
        all_log_events = self._get_log(filter_pattern, log_group_name, created_at)
        if all_log_events and len(all_log_events) > 0:
            event = all_log_events[0]
            message = json.loads(event["message"])
            current_app.logger.info(f"MESSAGE {message}")
            return "success", message["delivery"]["providerResponse"]

        log_group_name = (
            f"sns/{region}/{account_number}/DirectPublishToPhoneNumber/Failure"
        )
        # current_app.logger.info(f"Failure log group name: {log_group_name}")
        all_failed_events = self._get_log(filter_pattern, log_group_name, created_at)
        if all_failed_events and len(all_failed_events) > 0:
            current_app.logger.info("SHOULD RETURN FAILED BECAUSE WE FOUND A FAILURE")
            event = all_failed_events[0]
            message = json.loads(event["message"])
            current_app.logger.info(f"MESSAGE {message}")
            return "failure", message["delivery"]["providerResponse"]

        raise Exception(
            f"No event found for message_id {message_id} notification_id {notification_id}"
        )
