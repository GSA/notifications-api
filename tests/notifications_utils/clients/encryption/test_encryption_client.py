import pytest

from notifications_utils.clients.encryption.encryption_client import (
    Encryption,
    EncryptionError,
)


@pytest.fixture()
def encryption_client(app):
    client = Encryption()

    app.config["SECRET_KEY"] = "test-notify-secret-key"
    app.config["DANGEROUS_SALT"] = "test-notify-salt"

    client.init_app(app)

    return client


def test_should_ensure_shared_salt_security(app):
    client = Encryption()
    app.config["SECRET_KEY"] = "test-notify-secret-key"
    app.config["DANGEROUS_SALT"] = "too-short"
    with pytest.raises(EncryptionError):
        client.init_app(app)


def test_should_ensure_custom_salt_security(encryption_client):
    with pytest.raises(EncryptionError):
        encryption_client.encrypt("this", salt="too-short")


def test_should_encrypt_strings(encryption_client):
    encrypted = encryption_client.encrypt("this")
    assert encrypted != "this"
    assert isinstance(encrypted, str)


def test_should_encrypt_dicts(encryption_client):
    to_encrypt = {"hello": "world"}
    encrypted = encryption_client.encrypt(to_encrypt)
    assert encrypted != to_encrypt
    assert encryption_client.decrypt(encrypted) == to_encrypt


def test_encryption_is_nondeterministic(encryption_client):
    first_run = encryption_client.encrypt("this")
    second_run = encryption_client.encrypt("this")
    assert first_run != second_run


def test_should_decrypt_content(encryption_client):
    encrypted = encryption_client.encrypt("this")
    assert encryption_client.decrypt(encrypted) == "this"


def test_should_decrypt_content_with_custom_salt(encryption_client):
    salt = "different-salt-value"
    encrypted = encryption_client.encrypt("this", salt=salt)
    assert encryption_client.decrypt(encrypted, salt=salt) == "this"


def test_should_verify_decryption(encryption_client):
    encrypted = encryption_client.encrypt("this")
    with pytest.raises(EncryptionError):
        encryption_client.decrypt(encrypted, salt="different-salt-value")


def test_should_sign_and_serialize_string(encryption_client):
    signed = encryption_client.sign("this")
    assert signed != "this"


def test_should_verify_signature_and_deserialize_string(encryption_client):
    signed = encryption_client.sign("this")
    assert encryption_client.verify_signature(signed) == "this"


def test_should_raise_encryption_error_on_bad_salt(encryption_client):
    signed = encryption_client.sign("this")
    with pytest.raises(EncryptionError):
        encryption_client.verify_signature(signed, salt="different-salt-value")


def test_should_sign_and_serialize_json(encryption_client):
    signed = encryption_client.sign({"this": "that"})
    assert encryption_client.verify_signature(signed) == {"this": "that"}
