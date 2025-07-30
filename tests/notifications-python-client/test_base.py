import json
from unittest.mock import MagicMock, patch

import pytest

from notifications_python_client.base import BaseAPIClient
from notifications_python_client.errors import HTTPError


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
    assert client.base_url == "http://localhost:6011"

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


@patch("notifications_python_client.base.create_jwt_token")
@patch("notifications_python_client.base.requests.Session.request")
def test_post_request_with_data(mock_request, mock_jwt, client):
    mock_jwt.return_value = "jwt-token"
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "123"}
    mock_request.return_value = mock_response

    result = client.post("/send", data={"message": "hello"})
    assert result == {"id": "123"}
    args, kwargs = mock_request.call_args
    assert kwargs["data"] == json.dumps({"message": "hello"})
    assert "Authorization" in kwargs["headers"]


@patch("notifications_python_client.base.create_jwt_token")
@patch("notifications_python_client.base.requests.Session.request")
def test_request_raises_http_error(mock_request, mock_jwt, client):
    from requests.exceptions import HTTPError as RequestsHTTPError

    mock_jwt.return_value = "jwt-token"
    error_response = MagicMock
    error_response.status_code = 400
    mock_exception = RequestsHTTPError("bad", response=error_response)
    mock_request.side_effect = mock_exception
    with pytest.raises(HTTPError):
        client.get("/fail")
