import uuid
from datetime import datetime

from flask import current_app
from gds_metrics import Histogram
from notifications_utils.clients import redis
from notifications_utils.recipients import (
    format_email_address,
    get_international_phone_info,
    validate_and_format_phone_number,
)
from notifications_utils.template import (
    PlainTextEmailTemplate,
    SMSMessageTemplate,
)

from app import redis_store
from app.celery import provider_tasks
from app.config import QueueNames
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_delete_notifications_by_id,
)
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    SMS_TYPE,
    Notification,
)
from app.v2.errors import BadRequestError

REDIS_GET_AND_INCR_DAILY_LIMIT_DURATION_SECONDS = Histogram(
    'redis_get_and_incr_daily_limit_duration_seconds',
    'Time taken to get and possibly incremement the daily limit cache key',
)


def create_content_for_notification(template, personalisation):
    if template.template_type == EMAIL_TYPE:
        template_object = PlainTextEmailTemplate(
            {
                'content': template.content,
                'subject': template.subject,
                'template_type': template.template_type,
            },
            personalisation,
        )
    if template.template_type == SMS_TYPE:
        template_object = SMSMessageTemplate(
            {
                'content': template.content,
                'template_type': template.template_type,
            },
            personalisation,
        )

    check_placeholders(template_object)

    return template_object


def check_placeholders(template_object):
    if template_object.missing_data:
        message = 'Missing personalisation: {}'.format(", ".join(template_object.missing_data))
        raise BadRequestError(fields=[{'template': message}], message=message)


def persist_notification(
    *,
    template_id,
    template_version,
    recipient,
    service,
    personalisation,
    notification_type,
    api_key_id,
    key_type,
    created_at=None,
    job_id=None,
    job_row_number=None,
    reference=None,
    client_reference=None,
    notification_id=None,
    simulated=False,
    created_by_id=None,
    status=NOTIFICATION_CREATED,
    reply_to_text=None,
    billable_units=None,
    document_download_count=None,
    updated_at=None
):
    current_app.logger.info('Persisting notification')

    notification_created_at = created_at or datetime.utcnow()
    if not notification_id:
        notification_id = uuid.uuid4()

    current_app.logger.info('Persisting notification with id {}'.format(notification_id))

    notification = Notification(
        id=notification_id,
        template_id=template_id,
        template_version=template_version,
        to=recipient,
        service_id=service.id,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=api_key_id,
        key_type=key_type,
        created_at=notification_created_at,
        job_id=job_id,
        job_row_number=job_row_number,
        client_reference=client_reference,
        reference=reference,
        created_by_id=created_by_id,
        status=status,
        reply_to_text=reply_to_text,
        billable_units=billable_units,
        document_download_count=document_download_count,
        updated_at=updated_at
    )

    current_app.logger.info('Persisting notification with to address: {}'.format(notification.to))

    if notification_type == SMS_TYPE:
        formatted_recipient = validate_and_format_phone_number(recipient, international=True)
        recipient_info = get_international_phone_info(formatted_recipient)
        notification.normalised_to = formatted_recipient
        notification.international = recipient_info.international
        notification.phone_prefix = recipient_info.country_prefix
        notification.rate_multiplier = recipient_info.billable_units
    elif notification_type == EMAIL_TYPE:
        current_app.logger.info('Persisting notification with type: {}'.format(EMAIL_TYPE))
        notification.normalised_to = format_email_address(notification.to)
        current_app.logger.info('Persisting notification to formatted email: {}'.format(notification.normalised_to))

    # if simulated create a Notification model to return but do not persist the Notification to the dB
    if not simulated:
        current_app.logger.info('Firing dao_create_notification')
        dao_create_notification(notification)
        if key_type != KEY_TYPE_TEST and current_app.config['REDIS_ENABLED']:
            current_app.logger.info('Redis enabled, querying cache key for service id: {}'.format(service.id))
            cache_key = redis.daily_limit_cache_key(service.id)
            total_key = "{}-{}".format(datetime.utcnow().strftime("%Y-%m-%d"), "total")
            current_app.logger.info('Redis daily limit cache key: {}'.format(cache_key))
            if redis_store.get(cache_key) is None:
                current_app.logger.info('Redis daily limit cache key does not exist')
                # if cache does not exist set the cache to 1 with an expiry of 24 hours,
                # The cache should be set by the time we create the notification
                # but in case it is this will make sure the expiry is set to 24 hours,
                # where if we let the incr method create the cache it will be set a ttl.
                redis_store.set(cache_key, 1, ex=86400)
                current_app.logger.info('Set redis daily limit cache key to 1')
            else:
                current_app.logger.info('Redis daily limit cache key does exist')
                redis_store.incr(cache_key)
                current_app.logger.info('Redis daily limit cache key has been incremented')
            if redis_store.get(total_key) is None:
                current_app.logger.info('Redis daily total cache key does not exist')
                redis_store.set(total_key, 1, ex=86400)
                current_app.logger.info('Set redis daily total cache key to 1')
            else:
                current_app.logger.info('Redis total limit cache key does exist')
                redis_store.incr(total_key)
                current_app.logger.info('Redis total limit cache key has been incremented')
        current_app.logger.info(
            "{} {} created at {}".format(notification_type, notification_id, notification_created_at)
        )
    return notification


def send_notification_to_queue_detached(
    key_type, notification_type, notification_id, research_mode, queue=None
):
    if research_mode or key_type == KEY_TYPE_TEST:
        queue = QueueNames.RESEARCH_MODE

    if notification_type == SMS_TYPE:
        if not queue:
            queue = QueueNames.SEND_SMS
        deliver_task = provider_tasks.deliver_sms
    if notification_type == EMAIL_TYPE:
        if not queue:
            queue = QueueNames.SEND_EMAIL
        deliver_task = provider_tasks.deliver_email

    try:
        deliver_task.apply_async([str(notification_id)], queue=queue)
    except Exception:
        dao_delete_notifications_by_id(notification_id)
        raise

    current_app.logger.debug(
        "{} {} sent to the {} queue for delivery".format(notification_type,
                                                         notification_id,
                                                         queue))


def send_notification_to_queue(notification, research_mode, queue=None):
    send_notification_to_queue_detached(
        notification.key_type, notification.notification_type, notification.id, research_mode, queue
    )


def simulated_recipient(to_address, notification_type):
    if notification_type == SMS_TYPE:
        formatted_simulated_numbers = [
            validate_and_format_phone_number(number) for number in current_app.config['SIMULATED_SMS_NUMBERS']
        ]
        return to_address in formatted_simulated_numbers
    else:
        return to_address in current_app.config['SIMULATED_EMAIL_ADDRESSES']
