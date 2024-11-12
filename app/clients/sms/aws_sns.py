import os
import re
from time import monotonic

import botocore
import phonenumbers
from boto3 import client

from app.clients import AWS_CLIENT_CONFIG
from app.clients.sms import SmsClient
from app.cloudfoundry_config import cloud_config


class AwsSnsClient(SmsClient):
    """
    AwsSns sms client
    """

    def init_app(self, current_app, *args, **kwargs):
        if os.getenv("LOCALSTACK_ENDPOINT_URL"):
            self._client = client(
                "sns",
                region_name=cloud_config.sns_region,
                aws_access_key_id=cloud_config.sns_access_key,
                aws_secret_access_key=cloud_config.sns_secret_key,
                config=AWS_CLIENT_CONFIG,
                endpoint_url=os.getenv("LOCALSTACK_ENDPOINT_URL"),
            )
        else:
            self._client = client(
                "sns",
                region_name=cloud_config.sns_region,
                aws_access_key_id=cloud_config.sns_access_key,
                aws_secret_access_key=cloud_config.sns_secret_key,
                config=AWS_CLIENT_CONFIG,
            )

        super(SmsClient, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self._valid_sender_regex = re.compile(r"^\+?\d{5,14}$")

    @property
    def name(self):
        return "sns"

    def _valid_sender_number(self, sender):
        return sender and re.match(self._valid_sender_regex, sender)

    def send_sms(self, to, content, reference, sender=None, international=False):
        matched = False
        for match in phonenumbers.PhoneNumberMatcher(to, "US"):
            matched = True
            to = phonenumbers.format_number(
                match.number, phonenumbers.PhoneNumberFormat.E164
            )

            # See documentation
            # https://docs.aws.amazon.com/sns/latest/dg/sms_publish-to-phone.html#sms_publish_sdk
            attributes = {
                "AWS.SNS.SMS.SMSType": {
                    "DataType": "String",
                    "StringValue": "Transactional",
                }
            }

            non_scrubbable = " ".join(sender)
            default_num = " ".join(self.current_app.config["AWS_US_TOLL_FREE_NUMBER"])
            self.current_app.logger.info(
                f"notify-api-1385 sender {non_scrubbable} is a {type(sender)} default is a {type(default_num)}"
            )
            if self._valid_sender_number(sender):
                self.current_app.logger.info(
                    f"notify-api-1385 use valid sender {non_scrubbable} instead of default {default_num}"
                )

                attributes["AWS.MM.SMS.OriginationNumber"] = {
                    "DataType": "String",
                    "StringValue": sender,
                }
            else:
                self.current_app.logger.info(
                    f"notify-api-1385 use default {default_num} instead of invalid sender {non_scrubbable}"
                )

                attributes["AWS.MM.SMS.OriginationNumber"] = {
                    "DataType": "String",
                    "StringValue": self.current_app.config["AWS_US_TOLL_FREE_NUMBER"],
                }

            try:
                start_time = monotonic()
                response = self._client.publish(
                    PhoneNumber=to, Message=content, MessageAttributes=attributes
                )
            except botocore.exceptions.ClientError as e:
                self.current_app.logger.exception("An error occurred sending sms")
                raise str(e)
            except Exception as e:
                self.current_app.logger.exception("An error occurred sending sms")
                raise str(e)
            finally:
                elapsed_time = monotonic() - start_time
                self.current_app.logger.info(
                    "AWS SNS request finished in {}".format(elapsed_time)
                )
            return response["MessageId"]

        if not matched:
            self.current_app.logger.error("No valid numbers found in {}".format(to))
            raise ValueError("No valid numbers found for SMS delivery")
