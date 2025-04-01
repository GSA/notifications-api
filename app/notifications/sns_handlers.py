import enum
from json import decoder

import requests
from flask import current_app, json

from app.errors import InvalidRequest
from app.notifications.sns_cert_validator import validate_sns_cert


class SNSMessageType(enum.Enum):
    SubscriptionConfirmation = "SubscriptionConfirmation"
    Notification = "Notification"
    UnsubscribeConfirmation = "UnsubscribeConfirmation"


class InvalidMessageTypeException(Exception):
    pass


def verify_message_type(message_type: str):
    try:
        SNSMessageType(message_type)
    except ValueError:
        raise InvalidRequest("SES-SNS callback failed: invalid message type", 400)


def sns_notification_handler(data, headers):
    message_type = headers.get("x-amz-sns-message-type")
    try:
        verify_message_type(message_type)
    except InvalidMessageTypeException:
        current_app.logger.exception(
            f"Response headers: {headers}\nResponse data: {data}"
        )
        raise InvalidRequest("SES-SNS callback failed: invalid message type", 400)

    try:
        message = json.loads(data.decode("utf-8"))
    except decoder.JSONDecodeError:
        current_app.logger.exception(
            f"Response headers: {headers}\nResponse data: {data}"
        )
        raise InvalidRequest("SES-SNS callback failed: invalid JSON given", 400)

    try:
        validate_sns_cert(message)
    except Exception:
        current_app.logger.error(
            "SES-SNS callback failed: validation failed with error: Signature validation failed"
        )
        raise InvalidRequest("SES-SNS callback failed: validation failed", 400)

    if message.get("Type") == "SubscriptionConfirmation":
        # NOTE once a request is sent to SubscribeURL, AWS considers Notify a confirmed subscriber to this topic
        url = (
            message.get("SubscribeUrl")
            if "SubscribeUrl" in message
            else message.get("SubscribeURL")
        )
        response = requests.get(url, timeout=30)
        try:
            response.raise_for_status()
        except Exception as e:
            current_app.logger.warning(
                f"Attempt to raise_for_status()SubscriptionConfirmation Type "
                f"message files for response: {response.text} with error {e}"
            )
            raise InvalidRequest(
                "SES-SNS callback failed: attempt to raise_for_status()SubscriptionConfirmation "
                "Type message failed",
                400,
            )
        current_app.logger.info("SES-SNS auto-confirm subscription callback succeeded")
        return message

    # TODO remove after smoke testing on prod is implemented
    current_app.logger.info(
        f"SNS message: {message} is a valid message. Attempting to process it now."
    )

    return message
