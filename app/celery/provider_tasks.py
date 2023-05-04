from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from app import notify_celery
from app.clients.cloudwatch.aws_cloudwatch import AwsCloudwatchClient
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


@notify_celery.task(bind=True, name="check_sms_delivery_receipt", max_retries=3, default_retry_delay=300)
def check_sms_delivery_receipt(self, message_id, notification_id):
    current_app.logger.warning(f"CHECKING DELIVERY RECEIPT for {message_id} {notification_id}")
    cloudwatch_client = AwsCloudwatchClient()
    cloudwatch_client.init_app(current_app)
    status, provider_response = cloudwatch_client.check_sms(message_id, notification_id)
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
