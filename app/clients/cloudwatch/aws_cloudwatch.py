import json
import os
import re
import time

from boto3 import client

from app.clients.cloudwatch import CloudwatchClient
from app.cloudfoundry_config import cloud_config


class AwsCloudwatchClient(CloudwatchClient):
    """
    This client is responsible for retrieving sms delivery receipts from cloudwatch.
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

        # Check all events in the last 30 minutes
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
        """
        Go through the cloudwatch logs, filtering by message id.  Check the success logs first.  If we find
        the message id there, we are done.  Otherwise check the failure logs.  If we don't find the message
        in the success or failure logs, raise an exception.  This method is called on a five minute delay,
        which is presumably enough time for the cloudwatch log to be populated.
        """
        # TODO presumably there is a better way to get the aws account number
        account_number = os.getenv("SES_DOMAIN_ARN")
        account_number = account_number.replace('arn:aws:ses:us-west-2:', '')
        account_number = account_number.split(":")
        account_number = account_number[0]

        log_group_name = f'sns/us-west-2/{account_number}/DirectPublishToPhoneNumber'
        filter_pattern = '{$.notification.messageId="XXXXX"}'
        filter_pattern = filter_pattern.replace("XXXXX", message_id)
        all_log_events = self._get_all_logs(filter_pattern, log_group_name)

        if all_log_events and len(all_log_events) > 0:
            event = all_log_events[0]
            message = json.loads(event['message'])
            return "success", message['delivery']['providerResponse']

        log_group_name = f'sns/us-west-2/{account_number}/DirectPublishToPhoneNumber/Failure'
        all_failed_events = self._get_all_logs(filter_pattern, log_group_name)
        if all_failed_events and len(all_failed_events) > 0:
            event = all_failed_events[0]
            message = json.loads(event['message'])
            return "fail", message['delivery']['providerResponse']

        raise Exception(f'No event found for message_id {message_id} notification_id {notification_id}')
