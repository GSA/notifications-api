import os
import re
from time import sleep

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

    def check_delivery_receipts(self, start, end):

        result = self._client.describe_log_groups()
        print(result)
        return

        region = cloud_config.sns_region
        account_number = self._extract_account_number(cloud_config.ses_domain_arn)

        log_group_name = f"sns/{region}/{account_number[4]}/DirectPublishToPhoneNumber"
        log_group_name_failed = (
            f"sns/{region}/{account_number[4]}/DirectPublishToPhoneNumber/Failed"
        )

        query = """
        fields @timestamp, status, delivery.providerResponse, delivery.destination,
          notification.messageId, delivery.phoneCarrier
        | sort @timestamp asc
        """

        delivered = self.run_log_insights_query(log_group_name, start, end, query)
        failed = self.run_log_insights_query(log_group_name_failed, start, end, query)
        return delivered + failed

    def run_log_insights_query(self, log_group_name, start, end, query):
        response = self._client.start_query(
            logGroupName=log_group_name,
            startTime=int(start.timestamp()),
            endTime=int(end.timestamp()),
            queryString=query,
        )
        query_id = response["queryId"]
        while True:
            result = self._client.get_query_results(queryId=query_id)
            if result["status"] == "Complete":
                break
            sleep(1)

        delivery_receipts = []
        for log in result["results"]:
            receipt = {field["field"]: field["value"] for field in log}
            delivery_receipts.append(receipt)
        return delivery_receipts
