import json
import os
from datetime import timedelta

from botocore.exceptions import ClientError
from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from app import aws_cloudwatch_client, notify_celery, redis_store
from app.clients.email import EmailClientNonRetryableException
from app.clients.email.aws_ses import AwsSesClientThrottlingSendRateException
from app.clients.sms import SmsClientResponseException
from app.config import Config, QueueNames
from app.dao import notifications_dao
from app.dao.notifications_dao import (
    sanitize_successful_notification_by_id,
    update_notification_message_id,
    update_notification_status_by_id,
)
from app.delivery import send_to_providers
from app.enums import NotificationStatus
from app.exceptions import NotificationTechnicalFailureException
from app.utils import utc_now

# This is the amount of time to wait after sending an sms message before we check the aws logs and look for delivery
# receipts
DELIVERY_RECEIPT_DELAY_IN_SECONDS = 30


@notify_celery.task(
    bind=True,
    name="check_sms_delivery_receipt",
    max_retries=48,
    default_retry_delay=300,
)
def check_sms_delivery_receipt(self, message_id, notification_id, sent_at):
    """
    This is called after deliver_sms to check the status of the message. This uses the same number of
    retries and the same delay period as deliver_sms.  In addition, this fires five minutes after
    deliver_sms initially. So the idea is that most messages will succeed and show up in the logs quickly.
    Other message will resolve successfully after a retry or to.  A few will fail but it will take up to
    4 hours to know for sure.  The call to check_sms will raise an exception if neither a success nor a
    failure appears in the cloudwatch logs, so this should keep retrying until the log appears, or until
    we run out of retries.
    """
    # TODO the localstack cloudwatch doesn't currently have our log groups.  Possibly create them with awslocal?
    if aws_cloudwatch_client.is_localstack():
        status = "success"
        provider_response = "this is a fake successful localstack sms message"
        carrier = "unknown"
    else:
        try:
            status, provider_response, carrier = aws_cloudwatch_client.check_sms(
                message_id, notification_id, sent_at
            )
        except NotificationTechnicalFailureException as ntfe:
            provider_response = "Unable to find carrier response -- still looking"
            status = "pending"
            carrier = ""
            update_notification_status_by_id(
                notification_id,
                status,
                carrier=carrier,
                provider_response=provider_response,
            )
            raise self.retry(exc=ntfe)
        except ClientError as err:
            # Probably a ThrottlingException but could be something else
            error_code = err.response["Error"]["Code"]
            provider_response = (
                f"{error_code} while checking sms receipt -- still looking"
            )
            status = "pending"
            carrier = ""
            update_notification_status_by_id(
                notification_id,
                status,
                carrier=carrier,
                provider_response=provider_response,
            )
            raise self.retry(exc=err)

    if status == "success":
        status = NotificationStatus.DELIVERED
    elif status == "failure":
        status = NotificationStatus.FAILED
    # if status is not success or failure the client raised an exception and this method will retry

    if status == NotificationStatus.DELIVERED:
        sanitize_successful_notification_by_id(
            notification_id, carrier=carrier, provider_response=provider_response
        )
        current_app.logger.info(
            f"Sanitized notification {notification_id} that was successfully delivered"
        )
    else:
        update_notification_status_by_id(
            notification_id,
            status,
            carrier=carrier,
            provider_response=provider_response,
        )
        current_app.logger.info(
            f"Updated notification {notification_id} with response '{provider_response}'"
        )


@notify_celery.task(
    bind=True, name="deliver_sms", max_retries=48, default_retry_delay=300
)
def deliver_sms(self, notification_id):
    """Branch off to the final step in delivering the notification to sns and get delivery receipts."""
    try:
        current_app.logger.info(
            "Start sending SMS for notification id: {}".format(notification_id)
        )
        notification = notifications_dao.get_notification_by_id(notification_id)
        ansi_green = "\033[32m"
        ansi_reset = "\033[0m"

        if not notification:
            raise NoResultFound()
        if (
            os.getenv("NOTIFY_ENVIRONMENT") == "development"
            and "authentication code" in notification.content
        ):
            current_app.logger.warning(
                ansi_green + f"AUTHENTICATION CODE: {notification.content}" + ansi_reset
            )
        # Code branches off to send_to_providers.py
        message_id = send_to_providers.send_sms_to_provider(notification)
        if message_id is not None:  # can be none if technical failure happens
            update_notification_message_id(notification_id, message_id)

        # DEPRECATED
        # We have to put it in UTC.  For other timezones, the delay
        # will be ignored and it will fire immediately (although this probably only affects developer testing)
        my_eta = utc_now() + timedelta(seconds=DELIVERY_RECEIPT_DELAY_IN_SECONDS)
        check_sms_delivery_receipt.apply_async(
            [message_id, notification_id, notification.created_at],
            eta=my_eta,
            queue=QueueNames.CHECK_SMS,
        )
    except Exception as e:
        update_notification_status_by_id(
            notification_id,
            NotificationStatus.TEMPORARY_FAILURE,
        )
        if isinstance(e, SmsClientResponseException):
            current_app.logger.warning(
                "SMS notification delivery for id: {} failed".format(notification_id),
            )
        else:
            current_app.logger.exception(
                "SMS notification delivery for id: {} failed".format(notification_id),
            )

        try:
            if self.request.retries == 0:
                self.retry(
                    queue=QueueNames.RETRY,
                    countdown=0,
                    expires=Config.DEFAULT_REDIS_EXPIRE_TIME,
                )
            else:
                self.retry(
                    queue=QueueNames.RETRY, expires=Config.DEFAULT_REDIS_EXPIRE_TIME
                )
        except self.MaxRetriesExceededError:
            message = (
                "RETRY FAILED: Max retries reached. The task send_sms_to_provider failed for notification {}. "
                "Notification has been updated to technical-failure".format(
                    notification_id
                )
            )
            update_notification_status_by_id(
                notification_id,
                NotificationStatus.TECHNICAL_FAILURE,
            )
            raise NotificationTechnicalFailureException(message)


@notify_celery.task(
    bind=True, name="deliver_email", max_retries=48, default_retry_delay=30
)
def deliver_email(self, notification_id):
    try:
        current_app.logger.info(
            "Start sending email for notification id: {}".format(notification_id)
        )
        notification = notifications_dao.get_notification_by_id(notification_id)

        if not notification:
            raise NoResultFound()
        personalisation = redis_store.get(f"email-personalisation-{notification_id}")
        recipient = redis_store.get(f"email-recipient-{notification_id}")
        if personalisation:
            notification.personalisation = json.loads(personalisation)
        if recipient:
            notification.recipient = json.loads(recipient)

        send_to_providers.send_email_to_provider(notification)
    except EmailClientNonRetryableException:
        current_app.logger.exception(f"Email notification {notification_id} failed")
        update_notification_status_by_id(notification_id, "technical-failure")
    except Exception as e:
        try:
            if isinstance(e, AwsSesClientThrottlingSendRateException):
                current_app.logger.warning(
                    f"RETRY: Email notification {notification_id} was rate limited by SES"
                )
            else:
                current_app.logger.exception(
                    f"RETRY: Email notification {notification_id} failed"
                )

            self.retry(queue=QueueNames.RETRY, expires=Config.DEFAULT_REDIS_EXPIRE_TIME)
        except self.MaxRetriesExceededError:
            message = (
                "RETRY FAILED: Max retries reached. "
                "The task send_email_to_provider failed for notification {}. "
                "Notification has been updated to technical-failure".format(
                    notification_id
                )
            )
            update_notification_status_by_id(
                notification_id,
                NotificationStatus.TECHNICAL_FAILURE,
            )
            raise NotificationTechnicalFailureException(message)
