from base64 import urlsafe_b64decode, urlsafe_b64encode
from uuid import UUID


def base64_to_bytes(key):
    return urlsafe_b64decode(key + "==")


def bytes_to_base64(bytes):
    # remove trailing = to save precious bytes
    return urlsafe_b64encode(bytes).decode("ascii").rstrip("=")


def base64_to_uuid(value):
    # uuids are 16 bytes, and will always have two ==s of padding
    return UUID(bytes=urlsafe_b64decode(value.encode("ascii") + b"=="))


def uuid_to_base64(value):
    if not isinstance(value, UUID):
        value = UUID(value)
    return bytes_to_base64(value.bytes)
