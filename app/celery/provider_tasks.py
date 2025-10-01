import json
import os

from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from app import notify_celery, redis_store
from app.clients.email import EmailClientNonRetryableException
from app.clients.email.aws_ses import AwsSesClientThrottlingSendRateException
from app.clients.sms import SmsClientResponseException
from app.config import Config, QueueNames
from app.dao import notifications_dao
from app.dao.notifications_dao import update_notification_status_by_id
from app.delivery import send_to_providers
from app.enums import NotificationStatus
from app.exceptions import NotificationTechnicalFailureException
from notifications_utils.clients.redis import total_limit_cache_key


@notify_celery.task(
    bind=True, name="deliver_sms", max_retries=48, default_retry_delay=300
)
def deliver_sms(self, notification_id):
    """Branch off to the final step in delivering the notification to sns and get delivery receipts."""
    try:
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
        send_to_providers.send_sms_to_provider(notification)

        cache_key = total_limit_cache_key(notification.service_id)
        redis_store.incr(cache_key)

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
