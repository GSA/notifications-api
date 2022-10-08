import re
from time import monotonic

import boto3
import botocore
import phonenumbers

from app.clients.sms import SmsClient


class AwsSnsClient(SmsClient):
    """
    AwsSns sms client
    """

    def init_app(self, current_app, statsd_client, *args, **kwargs):
        self._client = boto3.client("sns", region_name=current_app.config["AWS_REGION"])
        self._long_codes_client = boto3.client("sns", region_name=current_app.config["AWS_PINPOINT_REGION"])
        super(SmsClient, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self.statsd_client = statsd_client
        self.long_code_regex = re.compile(r"^\+1\d{10}$")
        
    @property
    def name(self):
        return 'sns'

    def get_name(self):
        return 'sns'

    def send_sms(self, to, content, reference, sender=None, international=False):
        matched = False

        for match in phonenumbers.PhoneNumberMatcher(to, "US"):
            matched = True
            to = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)

            client = self._client
            # See documentation
            # https://docs.aws.amazon.com/sns/latest/dg/sms_publish-to-phone.html#sms_publish_sdk
            attributes = {
                "AWS.SNS.SMS.SMSType": {
                    "DataType": "String",
                    "StringValue": "Transactional",
                },
                "AWS.MM.SMS.OriginationNumber": {
                    "DataType": "String",
                    "StringValue": self.current_app.config["AWS_US_TOLL_FREE_NUMBER"],
                }
            }

            # sender is managed in the UI in settings > Text message senders
            send_with_dedicated_phone_number = self._send_with_dedicated_phone_number(sender)
            
            if send_with_dedicated_phone_number:
                client = self._long_codes_client
                attributes["AWS.MM.SMS.OriginationNumber"] = {
                    "DataType": "String",
                    "StringValue": sender,
                }
            
            country = phonenumbers.region_code_for_number(match.number)

            try:
                start_time = monotonic()
                response = client.publish(PhoneNumber=to, Message=content, MessageAttributes=attributes)
                self.current_app.logger.info('RESPONSE FROM AWS SNS:')
                for k,v in response.items():
                    self.current_app.logger.info(f'{k}: {v}')
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

    def _send_with_dedicated_phone_number(self, sender):
        return sender and re.match(self.long_code_regex, sender)