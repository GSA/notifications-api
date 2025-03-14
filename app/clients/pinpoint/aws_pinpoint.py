from boto3 import client
from botocore.exceptions import ClientError
from flask import current_app

from app.clients import AWS_CLIENT_CONFIG, Client
from app.cloudfoundry_config import cloud_config
from app.utils import hilite


class AwsPinpointClient(Client):

    def init_app(self, current_app, *args, **kwargs):
        self._client = client(
            "pinpoint",
            region_name=cloud_config.sns_region,
            aws_access_key_id=cloud_config.sns_access_key,
            aws_secret_access_key=cloud_config.sns_secret_key,
            config=AWS_CLIENT_CONFIG,
        )

        super(Client, self).__init__(*args, **kwargs)
        self.current_app = current_app

    @property
    def name(self):
        return "pinpoint"

    def validate_phone_number(self, country_code, phone_number):
        try:
            response = self._client.phone_number_validate(
                NumberValidateRequest={
                    "IsoCountryCode": country_code,
                    "PhoneNumber": phone_number,
                }
            )

            # TODO right now this will only print with AWS simulated numbers,
            # but remove this when that changes
            current_app.logger.info(hilite(response))
        except ClientError:
            current_app.logger.exception(
                "#notify-debug-validate-phone-number Could not validate with pinpoint"
            )

        # TODO This is the structure of the response.  When the phone validation
        # capability we want to offer is better defined (it may just be a question
        # of checking PhoneType -- i.e., landline or mobile) then do something with
        # this info.
        # {
        #     'NumberValidateResponse': {
        #         'Carrier': 'string',
        #         'City': 'string',
        #         'CleansedPhoneNumberE164': 'string',
        #         'CleansedPhoneNumberNational': 'string',
        #         'Country': 'string',
        #         'CountryCodeIso2': 'string',
        #         'CountryCodeNumeric': 'string',
        #         'County': 'string',
        #         'OriginalCountryCodeIso2': 'string',
        #         'OriginalPhoneNumber': 'string',
        #         'PhoneType': 'string',
        #         'PhoneTypeCode': 123,
        #         'Timezone': 'string',
        #         'ZipCode': 'string'
        #     }
        # }
