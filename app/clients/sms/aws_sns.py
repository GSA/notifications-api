from time import monotonic

import botocore
import phonenumbers
from boto3 import client

from app.clients.sms import SmsClient
from app.cloudfoundry_config import cloud_config


class AwsSnsClient(SmsClient):
    """
    AwsSns sms client
    """

    def init_app(self, current_app, statsd_client, *args, **kwargs):
        self._client = client(
            "sns",
            region_name=cloud_config.sns_region,
            aws_access_key_id=cloud_config.sns_access_key,
            aws_secret_access_key=cloud_config.sns_secret_key
        )
        super(SmsClient, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self.statsd_client = statsd_client

    @property
    def name(self):
        return 'sns'

    def get_name(self):
        return self.name

    def send_sms(self, to, content, reference, sender=None, international=False):
        matched = False

        for match in phonenumbers.PhoneNumberMatcher(to, "US"):
            matched = True
            to = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)

            # See documentation
            # https://docs.aws.amazon.com/sns/latest/dg/sms_publish-to-phone.html#sms_publish_sdk
            attributes = {
                "AWS.SNS.SMS.SMSType": {
                    "DataType": "String",
                    "StringValue": "Transactional",
                }
            }

            if sender:
                attributes["AWS.MM.SMS.OriginationNumber"] = {
                    "DataType": "String",
                    "StringValue": sender,
                }
            else:
                attributes["AWS.MM.SMS.OriginationNumber"] = {
                    "DataType": "String",
                    "StringValue": self.current_app.config["AWS_US_TOLL_FREE_NUMBER"],
                }

            try:
                start_time = monotonic()
                response = self._client.publish(PhoneNumber=to, Message=content, MessageAttributes=attributes)
            except botocore.exceptions.ClientError as e:
                self.statsd_client.incr("clients.sns.error")
                raise str(e)
            except Exception as e:
                self.statsd_client.incr("clients.sns.error")
                raise str(e)
            finally:
                elapsed_time = monotonic() - start_time
                self.current_app.logger.info("AWS SNS request finished in {}".format(elapsed_time))
                self.statsd_client.timing("clients.sns.request-time", elapsed_time)
                self.statsd_client.incr("clients.sns.success")
            return response["MessageId"]

        if not matched:
            self.statsd_client.incr("clients.sns.error")
            self.current_app.logger.error("No valid numbers found in {}".format(to))
            raise ValueError("No valid numbers found for SMS delivery")
