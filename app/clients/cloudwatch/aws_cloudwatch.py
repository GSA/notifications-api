import json
import os
import re

from boto3 import client

from app.clients import AWS_CLIENT_CONFIG, Client
from app.cloudfoundry_config import cloud_config
from app.utils import hilite


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

    def _get_log(self, log_group_name, start, end):
        # Check all cloudwatch logs from the time the notification was sent (currently 5 minutes previously) until now
        print(hilite(f"START {start} END {end}"))
        next_token = None
        all_log_events = []

        while True:
            if next_token:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    nextToken=next_token,
                    startTime=int(start.timestamp() * 1000),
                    endTime=int(end.timestamp() * 1000),
                )
            else:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    startTime=int(start.timestamp() * 1000),
                    endTime=int(end.timestamp() * 1000),
                )
            log_events = response.get("events", [])
            all_log_events.extend(log_events)
            next_token = response.get("nextToken")
            if not next_token:
                break
        return all_log_events

    def _extract_account_number(self, ses_domain_arn):
        account_number = ses_domain_arn.split(":")
        return account_number

    def event_to_db_format(self, event):

        # massage the data into the form the db expects.  When we switch
        # from filter_log_events to log insights this will be convenient
        if isinstance(event, str):
            event = json.loads(event)

        return {
            "notification.messageId": event["notification"]["messageId"],
            "status": event["status"],
            "delivery.phoneCarrier": event["delivery"]["phoneCarrier"],
            "delivery.providerResponse": event["delivery"]["providerResponse"],
            "@timestamp": event["notification"]["timestamp"],
        }

    # Here is an example of how to get the events with log insights
    # def do_log_insights():
    #     query = """
    #     fields @timestamp, status, message, recipient
    #     | filter status = "DELIVERED"
    #     | sort @timestamp asc
    #     """
    #     temp_client = boto3.client(
    #             "logs",
    #             region_name="us-gov-west-1",
    #             aws_access_key_id=AWS_ACCESS_KEY_ID,
    #             aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    #             config=AWS_CLIENT_CONFIG,
    #         )
    #     start = utc_now()
    #     end = utc_now - timedelta(hours=1)
    #     response = temp_client.start_query(
    #         logGroupName = LOG_GROUP_NAME_DELIVERED,
    #         startTime = int(start.timestamp()),
    #         endTime= int(end.timestamp()),
    #         queryString = query

    #     )
    #     query_id = response['queryId']
    #     while True:
    #         result = temp_client.get_query_results(queryId=query_id)
    #         if result['status'] == 'Complete':
    #             break
    #         time.sleep(1)

    #     delivery_receipts = []
    #     for log in result['results']:
    #         receipt = {field['field']: field['value'] for field in log}
    #         delivery_receipts.append(receipt)
    #         print(receipt)

    #     print(len(delivery_receipts))

    # In the long run we want to use Log Insights because it is more efficient
    # that filter_log_events.  But we are blocked by a permissions issue in the broker.
    # So for now, use filter_log_events and grab all log_events over a 10 minute interval,
    # and run this on a schedule.
    def check_delivery_receipts(self, start, end):
        region = cloud_config.sns_region
        # TODO this clumsy approach to getting the account number will be fixed as part of notify-api #258
        account_number = self._extract_account_number(cloud_config.ses_domain_arn)
        delivered_event_set = set()
        log_group_name = f"sns/{region}/{account_number[4]}/DirectPublishToPhoneNumber"
        print(hilite(f"LOG GROUP NAME {log_group_name}"))
        all_delivered_events = self._get_log(log_group_name, start, end)
        print(f"ALL DELIVEREDS {len(all_delivered_events)}")

        for event in all_delivered_events:
            actual_event = self.event_to_db_format(event["message"])
            delivered_event_set.add(json.dumps(actual_event))

        failed_event_set = set()
        log_group_name = (
            f"sns/{region}/{account_number[4]}/DirectPublishToPhoneNumber/Failure"
        )
        all_failed_events = self._get_log(log_group_name, start, end)
        print(f"ALL FAILEDS {len(all_failed_events)}")
        for event in all_failed_events:
            actual_event = self.event_to_db_format(event["message"])
            failed_event_set.add(json.dumps(actual_event))

        return delivered_event_set, failed_event_set
