from unittest.mock import MagicMock, patch

import pytest

from notifications_python_client.base import BaseAPIClient


def get_api_key():
    fake_service_id = "12345678-1234-1234-1234-123456789abc"
    fake_key_part = "abcdef12-3456-7890-abcd-ef1234567890"
    api_key = "x" + fake_service_id + fake_key_part
    return api_key


@pytest.fixture
def client():

    return BaseAPIClient(api_key=get_api_key())


def test_init_sets_values_correctly():
    api_key = get_api_key()
    client = BaseAPIClient(api_key=api_key)
    assert client.base_url == "https://api.notifications.service.gov.uk"

    assert client.api_key == api_key[-36:]
    assert client.service_id == api_key[-73:-37]
    assert client.timeout == 30


@patch("notifications_python_client.base.create_jwt_token")
@patch("notifications_python_client.base.requests.Session.request")
def test_get_request_success(mock_request, mock_jwt, client):
    mock_jwt.return_value = "jwt-token"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"foo": "bar"}
    mock_request.return_value = mock_response
    result = client.get("/test")
    assert result == {"foo": "bar"}
    mock_jwt.assert_called_once_with(client.api_key, client.service_id)
    mock_request.assert_called_once()
    assert mock_request.call_args[1]["headers"]["Authorization"] == "Bearer jwt-token"


def main():
    test_init_sets_values_correctly()
    test_get_request_success()


if __name__ == "__main__":
    main()
