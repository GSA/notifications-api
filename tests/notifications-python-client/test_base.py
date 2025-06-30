from unittest.mock import MagicMock, patch

import pytest

from notifications_python_client.base import BaseAPIClient

VALID_API_KEY = "key" + "-" * 68 + "service-id-uuid" + "-" * 32 # pragma: allowlist secret
FULL_API_KEY = VALID_API_KEY[-73:]


@pytest.fixture
def client():
    return BaseAPIClient(api_key=FULL_API_KEY)


def test_init_sets_values_correctly():
    client = BaseAPIClient(api_key=FULL_API_KEY)
    assert client.base_url == "https://api.notifications.service.gov.uk"
    assert client.api_key == FULL_API_KEY[-36:]
    assert client.service_id == FULL_API_KEY[-73:-27]
    assert client.timeout == 20


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
