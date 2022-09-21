import base64
import re
from urllib.parse import urlparse

import requests
from M2Crypto import X509

from app import redis_store
from app.config import Config

USE_CACHE = True
VALIDATE_ARN = True


_signing_cert_cache = {}
_cert_url_re = re.compile(
    r'sns\.([a-z]{1,3}-[a-z]+-[0-9]{1,2})\.amazonaws\.com',
)


VALID_SNS_TOPICS = Config.VALID_SNS_TOPICS
# VALID_SNS_TOPICS = ['my_bounce_topic_name', 'my_success_topic_name', 'my_complaint_topic_name']


def get_certificate(url):
    if USE_CACHE:
        res = redis_store.get(url)
        if res is not None:
            return res
        res = requests.get(url).text
        redis_store.set(url, res, ex=60 * 60)  # 60 minutes
        return res
    else:
        return requests.get(url).text


def valid_sns_message(sns_payload):
    """
    Adapted from the solution posted at
    https://github.com/boto/boto3/issues/2508#issuecomment-992931814
    """
    if not isinstance(sns_payload, dict):
        return False

    # Amazon SNS currently supports signature version 1.
    if sns_payload.get('SignatureVersion') != '1':
        return False
    
    if VALIDATE_ARN:
        arn = sns_payload.get('TopicArn')
        topic_name = arn.split(':')[5]
        if topic_name not in VALID_SNS_TOPICS:
            return False

    payload_type = sns_payload.get('Type')
    if payload_type in ['SubscriptionConfirmation', 'UnsubscribeConfirmation']:
        fields = ['Message', 'MessageId', 'SubscribeURL', 'Timestamp', 'Token', 'TopicArn', 'Type']
    elif payload_type == 'Notification':
        fields = ['Message', 'MessageId', 'Subject', 'Timestamp', 'TopicArn', 'Type']
    else:
        return False

    # Build the string to be signed.
    string_to_sign = ''
    for field in fields:
        field_value = sns_payload.get(field)
        if not isinstance(field_value, str):
            return False
        string_to_sign += field + '\n' + field_value + '\n'

    # Get the signature
    try:
        decoded_signature = base64.b64decode(sns_payload.get('Signature'))
    except (TypeError, ValueError):
        return False

    # Key signing cert url via Lambda and via webhook are slightly different
    signing_cert_url = sns_payload.get('SigningCertUrl') if 'SigningCertUrl' in sns_payload else sns_payload.get('SigningCertURL')
    if not isinstance(signing_cert_url, str):
        return False
    cert_scheme, cert_netloc, *_ = urlparse(signing_cert_url)
    if cert_scheme != 'https' or not re.match(_cert_url_re, cert_netloc):
        # The cert doesn't seem to be from AWS
        return False
    certificate = _signing_cert_cache.get(signing_cert_url)
    if certificate is None:
        certificate = X509.load_cert_string(get_certificate(signing_cert_url))
        _signing_cert_cache[signing_cert_url] = certificate

    if certificate.get_subject().as_text() != 'CN=sns.amazonaws.com':
        return False

    # Extract the public key.
    public_key = certificate.get_pubkey()

    # Amazon SNS uses SHA1withRSA.
    # http://sns-public-resources.s3.amazonaws.com/SNS_Message_Signing_Release_Note_Jan_25_2011.pdf
    public_key.reset_context(md='sha1')
    public_key.verify_init()

    # Sign the string.
    public_key.verify_update(string_to_sign.encode())

    # Verify the signature matches.
    verification_result = public_key.verify_final(decoded_signature)

    # M2Crypto uses EVP_VerifyFinal() from openssl as the underlying
    # verification function. 1 indicates success, anything else is either
    # a failure or an error.
    if verification_result != 1:
        return False

    return True