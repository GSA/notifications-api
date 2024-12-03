import uuid

from flask import current_app

from app import redis_store
from app.celery import provider_tasks
from app.config import QueueNames
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_delete_notifications_by_id,
    get_notification_by_id,
)
from app.enums import KeyType, NotificationStatus, NotificationType
from app.errors import BadRequestError
from app.models import Notification
from app.utils import hilite, utc_now
from notifications_utils.recipients import (
    format_email_address,
    get_international_phone_info,
    validate_and_format_phone_number,
)
from notifications_utils.template import PlainTextEmailTemplate, SMSMessageTemplate


def create_content_for_notification(template, personalisation):
    if template.template_type == NotificationType.EMAIL:
        template_object = PlainTextEmailTemplate(
            {
                "content": template.content,
                "subject": template.subject,
                "template_type": template.template_type,
            },
            personalisation,
        )
    if template.template_type == NotificationType.SMS:
        template_object = SMSMessageTemplate(
            {
                "content": template.content,
                "template_type": template.template_type,
            },
            personalisation,
        )

    check_placeholders(template_object)

    return template_object


def check_placeholders(template_object):
    if template_object.missing_data:
        message = "Missing personalisation: {}".format(
            ", ".join(template_object.missing_data)
        )
        raise BadRequestError(fields=[{"template": message}], message=message)


def get_notification(notification_id):
    return get_notification_by_id(notification_id)


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
    status=NotificationStatus.CREATED,
    reply_to_text=None,
    billable_units=None,
    document_download_count=None,
    updated_at=None,
):
    notification_created_at = created_at or utc_now()
    if not notification_id:
        notification_id = uuid.uuid4()

    current_app.logger.info(f"Persisting notification with id {notification_id}")

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
        updated_at=updated_at,
    )

    if notification_type == NotificationType.SMS:
        formatted_recipient = validate_and_format_phone_number(
            recipient, international=True
        )
        current_app.logger.info(
            hilite(
                f"Persisting notification with job_id: {job_id} row_number: {job_row_number}"
            )
        )
        recipient_info = get_international_phone_info(formatted_recipient)
        notification.normalised_to = formatted_recipient
        notification.international = recipient_info.international
        notification.phone_prefix = recipient_info.country_prefix
        notification.rate_multiplier = recipient_info.billable_units

    elif notification_type == NotificationType.EMAIL:
        current_app.logger.info(
            f"Persisting notification with type: {NotificationType.EMAIL}"
        )
        redis_store.set(
            f"email-address-{notification.id}",
            format_email_address(notification.to),
            ex=1800,
        )

    # if simulated create a Notification model to return but do not persist the Notification to the dB
    if not simulated:
        current_app.logger.info("Firing dao_create_notification")
        dao_create_notification(notification)
        if key_type != KeyType.TEST and current_app.config["REDIS_ENABLED"]:
            current_app.logger.info(
                "Redis enabled, querying cache key for service id: {}".format(
                    service.id
                )
            )

        current_app.logger.info(
            f"{notification_type} {notification_id} created at {notification_created_at}"
        )
    return notification


def send_notification_to_queue_detached(
    key_type, notification_type, notification_id, queue=None
):

    if notification_type == NotificationType.SMS:
        if not queue:
            queue = QueueNames.SEND_SMS
        deliver_task = provider_tasks.deliver_sms
    if notification_type == NotificationType.EMAIL:
        if not queue:
            queue = QueueNames.SEND_EMAIL
        deliver_task = provider_tasks.deliver_email

    try:
        deliver_task.apply_async([str(notification_id)], queue=queue)
    except Exception:
        dao_delete_notifications_by_id(notification_id)
        raise

    current_app.logger.debug(
        f"{notification_type} {notification_id} sent to the {queue} queue for delivery"
    )


def send_notification_to_queue(notification, queue=None):
    send_notification_to_queue_detached(
        notification.key_type,
        notification.notification_type,
        notification.id,
        queue,
    )


def simulated_recipient(to_address, notification_type):
    if notification_type == NotificationType.SMS:
        formatted_simulated_numbers = [
            validate_and_format_phone_number(number)
            for number in current_app.config["SIMULATED_SMS_NUMBERS"]
        ]
        return to_address in formatted_simulated_numbers
    else:
        return to_address in current_app.config["SIMULATED_EMAIL_ADDRESSES"]
