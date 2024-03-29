from time import monotonic

import botocore
from boto3 import client
from flask import current_app

from app.clients import AWS_CLIENT_CONFIG
from app.clients.email import (
    EmailClient,
    EmailClientException,
    EmailClientNonRetryableException,
)
from app.cloudfoundry_config import cloud_config
from app.enums import NotificationStatus, StatisticsType

ses_response_map = {
    "Permanent": {
        "message": "Hard bounced",
        "success": False,
        "notification_status": NotificationStatus.PERMANENT_FAILURE,
        "notification_statistics_status": StatisticsType.FAILURE,
    },
    "Temporary": {
        "message": "Soft bounced",
        "success": False,
        "notification_status": NotificationStatus.TEMPORARY_FAILURE,
        "notification_statistics_status": StatisticsType.FAILURE,
    },
    "Delivery": {
        "message": "Delivered",
        "success": True,
        "notification_status": NotificationStatus.DELIVERED,
        "notification_statistics_status": StatisticsType.DELIVERED,
    },
    "Complaint": {
        "message": "Complaint",
        "success": True,
        "notification_status": NotificationStatus.DELIVERED,
        "notification_statistics_status": StatisticsType.DELIVERED,
    },
}


def get_aws_responses(status):
    return ses_response_map[status]


class AwsSesClientException(EmailClientException):
    pass


class AwsSesClientThrottlingSendRateException(AwsSesClientException):
    pass


class AwsSesClient(EmailClient):
    """
    Amazon SES email client.
    """

    def init_app(self, *args, **kwargs):
        self._client = client(
            "ses",
            region_name=cloud_config.ses_region,
            aws_access_key_id=cloud_config.ses_access_key,
            aws_secret_access_key=cloud_config.ses_secret_key,
            config=AWS_CLIENT_CONFIG,
        )
        super(AwsSesClient, self).__init__(*args, **kwargs)

    @property
    def name(self):
        return "ses"

    def send_email(
        self, source, to_addresses, subject, body, html_body="", reply_to_address=None
    ):
        try:
            if isinstance(to_addresses, str):
                to_addresses = [to_addresses]

            reply_to_addresses = [reply_to_address] if reply_to_address else []

            body = {"Text": {"Data": body}}

            if html_body:
                body.update({"Html": {"Data": html_body}})

            start_time = monotonic()
            response = self._client.send_email(
                Source=source,
                Destination={
                    "ToAddresses": [
                        punycode_encode_email(addr) for addr in to_addresses
                    ],
                    "CcAddresses": [],
                    "BccAddresses": [],
                },
                Message={
                    "Subject": {
                        "Data": subject,
                    },
                    "Body": body,
                },
                ReplyToAddresses=[
                    punycode_encode_email(addr) for addr in reply_to_addresses
                ],
            )
        except botocore.exceptions.ClientError as e:
            _do_fancy_exception_handling(e)

        except Exception as e:
            raise AwsSesClientException(str(e))
        else:
            elapsed_time = monotonic() - start_time
            current_app.logger.info(
                "AWS SES request finished in {}".format(elapsed_time)
            )
            return response["MessageId"]


def punycode_encode_email(email_address):
    # only the hostname should ever be punycode encoded.
    local, hostname = email_address.split("@")
    return "{}@{}".format(local, hostname.encode("idna").decode("utf-8"))


def _do_fancy_exception_handling(e):
    # http://docs.aws.amazon.com/ses/latest/DeveloperGuide/api-error-codes.html
    if e.response["Error"]["Code"] == "InvalidParameterValue":
        raise EmailClientNonRetryableException(e.response["Error"]["Message"])
    elif (
        e.response["Error"]["Code"] == "Throttling"
        and e.response["Error"]["Message"] == "Maximum sending rate exceeded."
    ):
        raise AwsSesClientThrottlingSendRateException(str(e))
    else:
        raise AwsSesClientException(str(e))
