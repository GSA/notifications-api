import urllib

import pytest
from itsdangerous import BadSignature, SignatureExpired

from notifications_utils.url_safe_token import check_token, generate_token


def test_should_return_payload_from_signed_token():
    payload = "email@something.com"
    token = generate_token(payload, "secret-key", "dangerous-salt")
    token = urllib.parse.unquote(token)
    assert payload == check_token(token, "secret-key", "dangerous-salt", 30)


def test_should_throw_exception_when_token_is_tampered_with():
    import uuid

    token = generate_token(str(uuid.uuid4()), "secret-key", "dangerous-salt")
    try:
        check_token(token + "qerqwer", "secret-key", "dangerous-salt", 30)
        pytest.fail("Expected a BadSignature")
    except BadSignature:
        pass


def test_return_none_when_token_is_expired():
    max_age = -1000
    payload = "some_payload"
    token = generate_token(payload, "secret-key", "dangerous-salt")
    token = urllib.parse.unquote(token)
    try:
        assert check_token(token, "secret-key", "dangerous-salt", max_age) is None
        pytest.fail("Expected a SignatureExpired exception")
    except SignatureExpired:
        pass
