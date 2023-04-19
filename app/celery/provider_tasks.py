import os

from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from app import notify_celery
from app.clients.email import EmailClientNonRetryableException
from app.clients.email.aws_ses import AwsSesClientThrottlingSendRateException
from app.clients.sms import SmsClientResponseException
from app.config import QueueNames
from app.dao import notifications_dao
from app.dao.notifications_dao import (
    check_service_rate_usage,
    increment_service_rate_usage,
    update_notification_status_by_id,
)
from app.delivery import send_to_providers
from app.exceptions import NotificationTechnicalFailureException
from app.models import NOTIFICATION_TECHNICAL_FAILURE


@notify_celery.task(bind=True, name="deliver_sms", max_retries=48, default_retry_delay=300)
def deliver_sms(self, notification_id):
    try:
        current_app.logger.info("Start sending SMS for notification id: {}".format(notification_id))
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            raise NoResultFound()
        total_used = check_service_rate_usage(notification.service_id)
        current_app.logger.warning(f"SERVICE_RATE_USAGE = {total_used}")
        # Hardcoded 250000 is there because I'm not sure how to propagate a new env variable to development
        # It is not picking it up from sample.env
        rate_limit = int(os.getenv("SERVICE_RATE_LIMIT", 250000))
        current_app.logger.info(f"SERVICE_RATE_LIMIT={rate_limit}")
        if total_used >= rate_limit:
            raise RateLimitExceededException()

        send_to_providers.send_sms_to_provider(notification)
        increment_service_rate_usage(notification.id, notification.service_id)
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


class RateLimitExceededException(Exception):
    def __init__(self, message="Rate Limit Exceeded"):
        super().__init__(message)
