import base64
import re
from urllib.parse import urlparse

import requests
import six
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from app import redis_store
from app.config import Config

VALIDATE_SNS_TOPICS = Config.VALIDATE_SNS_TOPICS
VALID_SNS_TOPICS = Config.VALID_SNS_TOPICS


_signing_cert_cache = {}
_cert_url_re = re.compile(
    r"sns\.([a-z]{1,3}(?:-gov)?-[a-z]+-[0-9]{1,2})\.amazonaws\.com",
)


class ValidationError(Exception):
    """
    ValidationError. Raised when a message fails integrity checks.
    """


def get_certificate(url):
    res = redis_store.get(url)
    if res is not None:
        return res
    res = requests.get(url, timeout=30).text
    redis_store.set(url, res, ex=60 * 60)  # 60 minutes
    _signing_cert_cache[url] = res
    return res


def validate_arn(sns_payload):
    if VALIDATE_SNS_TOPICS:
        arn = sns_payload.get("TopicArn")
        if arn not in VALID_SNS_TOPICS:
            raise ValidationError("Invalid Topic Name")


def get_string_to_sign(sns_payload):
    payload_type = sns_payload.get("Type")
    if payload_type in ["SubscriptionConfirmation", "UnsubscribeConfirmation"]:
        fields = [
            "Message",
            "MessageId",
            "SubscribeURL",
            "Timestamp",
            "Token",
            "TopicArn",
            "Type",
        ]
    elif payload_type == "Notification":
        fields = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
    else:
        raise ValidationError("Unexpected Message Type")

    string_to_sign = ""
    for field in fields:
        field_value = sns_payload.get(field)
        if not isinstance(field_value, str):
            if field == "Subject" and field_value is None:
                continue
            raise ValidationError(f"In {field}, found non-string value: {field_value}")
        string_to_sign += field + "\n" + field_value + "\n"
    if isinstance(string_to_sign, six.text_type):
        string_to_sign = string_to_sign.encode()
    return string_to_sign


def validate_sns_cert(sns_payload):
    """
    Adapted from the solution posted at
    https://github.com/boto/boto3/issues/2508#issuecomment-992931814
    Modified to swap m2crypto for oscrypto
    """
    if not isinstance(sns_payload, dict):
        raise ValidationError(
            "Unexpected message type {!r}".format(type(sns_payload).__name__)
        )

    # Amazon SNS currently supports signature version 1.
    if sns_payload.get("SignatureVersion") != "1":
        raise ValidationError("Wrong Signature Version (expected 1)")

    validate_arn(sns_payload)

    string_to_sign = get_string_to_sign(sns_payload)

    # Key signing cert url via Lambda and via webhook are slightly different
    signing_cert_url = (
        sns_payload.get("SigningCertUrl")
        if "SigningCertUrl" in sns_payload
        else sns_payload.get("SigningCertURL")
    )
    if not isinstance(signing_cert_url, str):
        raise ValidationError("Signing cert url must be a string")
    cert_scheme, cert_netloc, *_ = urlparse(signing_cert_url)
    if cert_scheme != "https" or not re.match(_cert_url_re, cert_netloc):
        raise ValidationError("Cert does not appear to be from AWS")

    certificate = _signing_cert_cache.get(signing_cert_url)
    if certificate is None:
        certificate = get_certificate(signing_cert_url)
    if isinstance(certificate, six.text_type):
        certificate = certificate.encode()

    # load the certificate
    certificate = x509.load_pem_x509_certificate(certificate)

    signature = base64.b64decode(sns_payload["Signature"])

    try:
        public_key = certificate.public_key()
        public_key.verify(
            signature, string_to_sign, padding.PKCS1v15(), hashes.SHA256()  # or SHA1?
        )
        return True
    except InvalidSignature:
        raise ValidationError("Invalid signature")
