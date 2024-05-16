import pytest
from werkzeug.test import EnvironBuilder

from notifications_utils.request_helper import NotifyRequest, _check_proxy_header_secret


@pytest.mark.parametrize(
    "header,secrets,expected",
    [
        (
            {"X-Custom-Forwarder": "right_key"},
            ["right_key", "old_key"],
            (True, "Key used: 1"),
        ),
        ({"X-Custom-Forwarder": "right_key"}, ["right_key"], (True, "Key used: 1")),
        ({"X-Custom-Forwarder": "right_key"}, ["right_key", ""], (True, "Key used: 1")),
        ({"My-New-Header": "right_key"}, ["right_key", ""], (True, "Key used: 1")),
        ({"X-Custom-Forwarder": "right_key"}, ["", "right_key"], (True, "Key used: 2")),
        (
            {"X-Custom-Forwarder": "right_key"},
            ["", "old_key", "right_key"],
            (True, "Key used: 3"),
        ),
        (
            {"X-Custom-Forwarder": ""},
            ["right_key", "old_key"],
            (False, "Header exists but is empty"),
        ),
        (
            {"X-Custom-Forwarder": "right_key"},
            ["", None],
            (False, "Secrets are not configured"),
        ),
        (
            {"X-Custom-Forwarder": "wrong_key"},
            ["right_key", "old_key"],
            (False, "Header didn't match any keys"),
        ),
    ],
)
def test_request_header_authorization(header, secrets, expected):
    builder = EnvironBuilder()
    builder.headers.extend(header)
    request = NotifyRequest(builder.get_environ())

    res = _check_proxy_header_secret(request, secrets, list(header.keys())[0])
    assert res == expected


@pytest.mark.parametrize(
    "secrets,expected",
    [
        (["old_key", "right_key"], (False, "Header missing")),
    ],
)
def test_request_header_authorization_missing_header(secrets, expected):
    builder = EnvironBuilder()
    request = NotifyRequest(builder.get_environ())

    res = _check_proxy_header_secret(request, secrets)
    assert res == expected
