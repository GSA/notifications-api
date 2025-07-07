from unittest.mock import MagicMock

import pytest
from aiohttp import ClientError

from app.clients.pinpoint.aws_pinpoint import AwsPinpointClient


def test_validate_phone_number_success():
    phone = "+1234567890"
    mock_response = {
        "NumberValidateResponse": {
            "PhoneType": "MOBILE",
            "CleansedPhoneNumberE164": phone,
        }
    }
    client_instance = AwsPinpointClient()
    client_instance._client = MagicMock()
    client_instance._client.phone_number_validate.return_value = mock_response

    result = client_instance.validate_phone_number("US", phone)
    assert result is not None
    client_instance._client.phone_number_validate.assert_called_once_with(
        NumberValidateRequest={"IsoCountryCode": "US", "PhoneNumber": phone}
    )


def test_validate_phone_number_client_error():
    client_instance = AwsPinpointClient()
    client_instance._client = MagicMock()
    client_instance._client.phone_number_validate.side_effect = ClientError(
        {"Error": {"Code": "BadRequest1", "MEssage": "Invalid phone"}},
        "phone number validate",
    )

    with pytest.raises(ClientError):
        client_instance.validate_phone_number("US", "bad-number")
