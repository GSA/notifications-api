import json
import os
import re

from boto3 import client
from flask import current_app

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

    def _extract_account_number(self, ses_domain_arn):
        account_number = ses_domain_arn.split(":")
        return account_number

    def event_to_db_format(self, event):

        # massage the data into the form the db expects.  When we switch
        # from filter_log_events to log insights this will be convenient
        if isinstance(event, str):
            event = json.loads(event)

        # Don't trust AWS to always send the same JSON structure back
        # However, if we don't get message_id and status we might as well blow up
        # because it's pointless to continue
        phone_carrier = self._aws_value_or_default(event, "delivery", "phoneCarrier")
        provider_response = self._aws_value_or_default(
            event, "delivery", "providerResponse"
        )
        message_cost = self._aws_value_or_default(event, "delivery", "priceInUSD")
        if message_cost is None or message_cost == "":
            message_cost = 0.0
        else:
            message_cost = float(message_cost)

        my_timestamp = self._aws_value_or_default(event, "notification", "timestamp")
        return {
            "notification.messageId": event["notification"]["messageId"],
            "status": event["status"],
            "delivery.phoneCarrier": phone_carrier,
            "delivery.providerResponse": provider_response,
            "@timestamp": my_timestamp,
            "delivery.priceInUSD": message_cost,
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
        account_number = self._extract_account_number(cloud_config.ses_domain_arn)
        log_group_name = f"sns/{region}/{account_number[4]}/DirectPublishToPhoneNumber"
        delivered_event_set = self._get_receipts(log_group_name, start, end)
        current_app.logger.info(
            (f"Delivered message count: {len(delivered_event_set)}")
        )
        log_group_name = (
            f"sns/{region}/{account_number[4]}/DirectPublishToPhoneNumber/Failure"
        )
        failed_event_set = self._get_receipts(log_group_name, start, end)
        current_app.logger.info((f"Failed message count: {len(failed_event_set)}"))
        raise_exception = False
        for failure in failed_event_set:
            try:
                failure = json.loads(failure)
                if "No quota left for account" == failure["delivery.providerResponse"]:
                    current_app.logger.warning(
                        hilite("**********NO QUOTA LEFT TO SEND MESSAGES!!!**********")
                    )
                    raise_exception = True
            except Exception:
                current_app.logger.exception("Malformed delivery receipt")
        if raise_exception:
            raise Exception("No Quota Left")

        return delivered_event_set, failed_event_set

    def _get_receipts(self, log_group_name, start, end):
        event_set = set()
        try:
            all_events = self._get_log(log_group_name, start, end)
            for event in all_events:
                try:
                    actual_event = self.event_to_db_format(event["message"])
                    event_set.add(json.dumps(actual_event))
                except Exception:
                    current_app.logger.exception(
                        f"Could not format delivery receipt {event} for db insert"
                    )
        except Exception as e:
            current_app.logger.error(f"Could not find log group {log_group_name}")
            raise e
        return event_set

    def _aws_value_or_default(self, event, top_level, second_level):
        if event.get(top_level) is None or event[top_level].get(second_level) is None:
            my_var = ""
        else:
            my_var = event[top_level][second_level]

        return my_var
