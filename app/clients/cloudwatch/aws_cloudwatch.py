import json
import os
import re
import time

from boto3 import client

from app.clients.cloudwatch import CloudwatchClient
from app.cloudfoundry_config import cloud_config


class AwsCloudwatchClient(CloudwatchClient):
    """
    AwsCloudwatch cloudwatch client
    """

    def init_app(self, current_app, *args, **kwargs):
        self._client = client(
            "logs",
            region_name=cloud_config.sns_region,
            aws_access_key_id=cloud_config.sns_access_key,
            aws_secret_access_key=cloud_config.sns_secret_key
        )
        super(CloudwatchClient, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self._valid_sender_regex = re.compile(r"^\+?\d{5,14}$")

    @property
    def name(self):
        return 'cloudwatch'

    def _get_all_logs(self, my_filter, log_group_name):
        now = round(time.time() * 1000)
        beginning = now - 30 * 60 * 1000

        next_token = None
        all_log_events = []
        while True:
            if next_token:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    filterPattern=my_filter,
                    nextToken=next_token,
                    startTime=beginning,
                    endTime=now
                )
            else:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    filterPattern=my_filter,
                    startTime=beginning,
                    endTime=now
                )
            log_events = response.get('events', [])
            all_log_events.extend(log_events)
            next_token = response.get('nextToken')
            if not next_token:
                break
        return all_log_events

    def check_sms(self, message_id, notification_id):
        # TODO presumably there is a better way to get the account number
        account_number = os.getenv("SES_DOMAIN_ARN")
        account_number = account_number.replace('arn:aws:ses:us-west-2:', '')
        account_number = account_number.split(":")
        account_number = account_number[0]

        log_group_name = f'sns/us-west-2/{account_number}/DirectPublishToPhoneNumber'
        filter_pattern = '{$.notification.messageId="XXXXX"}'
        filter_pattern = filter_pattern.replace("XXXXX", message_id)
        all_log_events = self._get_all_logs(filter_pattern, log_group_name)

        self.current_app.logger.warning(f"ALL EVENTS {all_log_events}")

        if all_log_events and len(all_log_events) > 0:
            event = all_log_events[0]
            self.current_app.logger.warning(f"HERE IS AN EVENT {event} of type {type(event)}")
            message = json.loads(event['message'])
            self.current_app.logger.warning(f"HERE IS THE message {message}")
            return "success", message['delivery']['providerResponse']

        log_group_name = f'sns/us-west-2/{account_number}/DirectPublishToPhoneNumber/Failure'
        all_failed_events = self._get_all_logs(filter_pattern, log_group_name)
        if all_failed_events and len(all_failed_events) > 0:
            event = all_failed_events[0]
            message = json.loads(event['message'])
            return "fail", message['delivery']['providerResponse']

        raise Exception(f'No event found for message_id {message_id}')
