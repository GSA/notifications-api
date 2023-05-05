from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from app import aws_cloudwatch_client, notify_celery
from app.clients.email import EmailClientNonRetryableException
from app.clients.email.aws_ses import AwsSesClientThrottlingSendRateException
from app.clients.sms import SmsClientResponseException
from app.config import QueueNames
from app.dao import notifications_dao
from app.dao.notifications_dao import update_notification_status_by_id
from app.delivery import send_to_providers
from app.exceptions import NotificationTechnicalFailureException
from app.models import (
    NOTIFICATION_FAILED,
    NOTIFICATION_SENT,
    NOTIFICATION_TECHNICAL_FAILURE,
)


@notify_celery.task(bind=True, name="check_sms_delivery_receipt", max_retries=48, default_retry_delay=300)
def check_sms_delivery_receipt(self, message_id, notification_id):
    """
    This is called after deliver_sms to check the status of the message. This uses the same number of
    retries and the same delay period as deliver_sms.  In addition, this fires five minutes after
    deliver_sms initially. So the idea is that most messages will succeed and show up in the logs quickly.
    Other message will resolve successfully after a retry or to.  A few will fail but it will take up to
    4 hours to know for sure.  The call to check_sms will raise an exception if neither a success nor a
    failure appears in the cloudwatch logs, so this should keep retrying until the log appears, or until
    we run out of retries.
    """
    status, provider_response = aws_cloudwatch_client.check_sms(message_id, notification_id)
    if status == 'success':
        status = NOTIFICATION_SENT
    else:
        status = NOTIFICATION_FAILED
    update_notification_status_by_id(notification_id, status, provider_response=provider_response)


@notify_celery.task(bind=True, name="deliver_sms", max_retries=48, default_retry_delay=300)
def deliver_sms(self, notification_id):
    try:
        current_app.logger.info("Start sending SMS for notification id: {}".format(notification_id))
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            raise NoResultFound()
        message_id = send_to_providers.send_sms_to_provider(notification)
        # We have to put it in the default US/Eastern timezone.  From zones west of there, the delay
        # will be ignored and it will fire immediately (although this probably only affects developer testing)
        my_eta = datetime.now(ZoneInfo('US/Eastern')) + timedelta(seconds=300)
        check_sms_delivery_receipt.apply_async(
            [message_id, notification_id],
            eta=my_eta,
            queue=QueueNames.CHECK_SMS
        )
    except Exception as e:
        if isinstance(e, SmsClientResponseException):
            current_app.logger.warning(
                "SMS notification delivery for id: {} failed".format(notification_id),
                exc_info=True
            )
        else:
            current_app.logger.exception(
                "SMS notification delivery for id: {} failed".format(notification_id)
            )

        try:
            if self.request.retries == 0:
                self.retry(queue=QueueNames.RETRY, countdown=0)
            else:
                self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            message = "RETRY FAILED: Max retries reached. The task send_sms_to_provider failed for notification {}. " \
                      "Notification has been updated to technical-failure".format(notification_id)
            update_notification_status_by_id(notification_id, NOTIFICATION_TECHNICAL_FAILURE)
            raise NotificationTechnicalFailureException(message)


@notify_celery.task(bind=True, name="deliver_email", max_retries=48, default_retry_delay=300)
def deliver_email(self, notification_id):
    try:
        current_app.logger.info("Start sending email for notification id: {}".format(notification_id))
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            raise NoResultFound()
        send_to_providers.send_email_to_provider(notification)
    except EmailClientNonRetryableException as e:
        current_app.logger.exception(
            f"Email notification {notification_id} failed: {e}"
        )
        update_notification_status_by_id(notification_id, 'technical-failure')
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

            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            message = "RETRY FAILED: Max retries reached. " \
                      "The task send_email_to_provider failed for notification {}. " \
                      "Notification has been updated to technical-failure".format(notification_id)
            update_notification_status_by_id(notification_id, NOTIFICATION_TECHNICAL_FAILURE)
            raise NotificationTechnicalFailureException(message)
