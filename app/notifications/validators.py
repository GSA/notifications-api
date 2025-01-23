from flask import current_app
from sqlalchemy.orm.exc import NoResultFound

from app import redis_store
from app.dao.notifications_dao import dao_get_notification_count_for_service
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.enums import KeyType, NotificationType, ServicePermissionType, TemplateType
from app.errors import BadRequestError, RateLimitError, TotalRequestsError
from app.models import ServicePermission
from app.notifications.process_notifications import create_content_for_notification
from app.serialised_models import SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.utils import get_public_notify_type_text
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.clients.redis import (
    rate_limit_cache_key,
    total_limit_cache_key,
)
from notifications_utils.recipients import (
    get_international_phone_info,
    validate_and_format_email_address,
    validate_and_format_phone_number,
)


def check_service_over_api_rate_limit(service, api_key):
    if (
        current_app.config["API_RATE_LIMIT_ENABLED"]
        and current_app.config["REDIS_ENABLED"]
    ):
        cache_key = rate_limit_cache_key(service.id, api_key.key_type)
        rate_limit = service.rate_limit
        interval = 60
        if redis_store.exceeded_rate_limit(cache_key, rate_limit, interval):
            current_app.logger.info(
                "service {} has been rate limited for throughput".format(service.id)
            )
            raise RateLimitError(rate_limit, interval, api_key.key_type)


def check_service_over_total_message_limit(key_type, service):
    if key_type == KeyType.TEST or not current_app.config["REDIS_ENABLED"]:
        return 0

    cache_key = total_limit_cache_key(service.id)
    service_stats = redis_store.get(cache_key)

    ## Originally this was a daily limit check.  It is now a free-tier limit check.
    ## TODO is this annual or forever for each service?
    ## TODO do we need a way to clear this out?  How do we determine if it is
    ## free-tier or paid?  What are the limits for paid?  Etc.
    ## TODO
    ## setting expiration to one year for now on the assume that the free tier
    ## limit resets annually.
    if service_stats is None:
        service_stats = 0
        redis_store.set(cache_key, service_stats, ex=365*24*60*60)
        return service_stats
    if int(service_stats) >= service.total_message_limit:
        current_app.logger.warning(
            "service {} has been rate limited for total use sent {} limit {}".format(
                service.id, int(service_stats), service.total_message_limit
            )
        )
        raise TotalRequestsError(service.total_message_limit)
    return int(service_stats)


def check_application_over_retention_limit(key_type, service):
    if key_type == KeyType.TEST or not current_app.config["REDIS_ENABLED"]:
        return 0
    total_stats = dao_get_notification_count_for_service(service_id=service.id)

    daily_message_limit = current_app.config["DAILY_MESSAGE_LIMIT"]

    if int(total_stats) >= daily_message_limit:
        current_app.logger.info(
            "while sending for service {}, daily message limit of {} reached".format(
                service.id, daily_message_limit
            )
        )
        raise TotalRequestsError(daily_message_limit)
    return int(total_stats)


def check_rate_limiting(service, api_key):
    check_service_over_api_rate_limit(service, api_key)
    check_application_over_retention_limit(api_key.key_type, service)


def check_template_is_for_notification_type(notification_type, template_type):
    if notification_type != template_type:
        message = "{0} template is not suitable for {1} notification".format(
            template_type, notification_type
        )
        raise BadRequestError(fields=[{"template": message}], message=message)


def check_template_is_active(template):
    if template.archived:
        raise BadRequestError(
            fields=[{"template": "Template has been deleted"}],
            message="Template has been deleted",
        )


def service_can_send_to_recipient(
    send_to, key_type, service, allow_guest_list_recipients=True
):
    if not service_allowed_to_send_to(
        send_to, service, key_type, allow_guest_list_recipients
    ):
        if key_type == KeyType.TEAM:
            message = "Can’t send to this recipient using a team-only API key"
        else:
            message = (
                "Can’t send to this recipient when service is in trial mode "
                "– see https://www.notifications.service.gov.uk/trial-mode"
            )
        raise BadRequestError(message=message)


def service_has_permission(notify_type, permissions):
    return notify_type in permissions


def check_service_has_permission(notify_type, permissions):
    if not service_has_permission(notify_type, permissions):
        raise BadRequestError(
            message="Service is not allowed to send {}".format(
                get_public_notify_type_text(notify_type, plural=True)
            )
        )


def check_if_service_can_send_files_by_email(service_contact_link, service_id):
    if not service_contact_link:
        raise BadRequestError(
            message=f"Send files by email has not been set up - add contact details for your service at "
            f"{current_app.config['ADMIN_BASE_URL']}/services/{service_id}/service-settings/send-files-by-email"
        )


def validate_and_format_recipient(
    send_to, key_type, service, notification_type, allow_guest_list_recipients=True
):
    if send_to is None:
        raise BadRequestError(message="Recipient can't be empty")

    service_can_send_to_recipient(
        send_to, key_type, service, allow_guest_list_recipients
    )

    if notification_type == NotificationType.SMS:
        international_phone_info = check_if_service_can_send_to_number(service, send_to)

        return validate_and_format_phone_number(
            number=send_to, international=international_phone_info.international
        )
    elif notification_type == NotificationType.EMAIL:
        return validate_and_format_email_address(email_address=send_to)


def check_if_service_can_send_to_number(service, number):
    international_phone_info = get_international_phone_info(number)

    if service.permissions and isinstance(service.permissions[0], ServicePermission):
        permissions = [p.permission for p in service.permissions]
    else:
        permissions = service.permissions

    if (
        international_phone_info.international
        and ServicePermissionType.INTERNATIONAL_SMS not in permissions
    ):
        raise BadRequestError(message="Cannot send to international mobile numbers")
    else:
        return international_phone_info


def check_is_message_too_long(template_with_content):
    if template_with_content.is_message_too_long():
        message = "Your message is too long. "
        if template_with_content.template_type == TemplateType.SMS:
            message += (
                f"Text messages cannot be longer than {SMS_CHAR_COUNT_LIMIT} characters. "
                f"Your message is {template_with_content.content_count_without_prefix} characters long."
            )
        elif template_with_content.template_type == TemplateType.EMAIL:
            message += (
                f"Emails cannot be longer than 2000000 bytes. "
                f"Your message is {template_with_content.content_size_in_bytes} bytes."
            )
        raise BadRequestError(message=message)


def check_notification_content_is_not_empty(template_with_content):
    if template_with_content.is_message_empty():
        message = "Your message is empty."
        raise BadRequestError(message=message)


def validate_template(
    template_id, personalisation, service, notification_type, check_char_count=True
):
    try:
        template = SerialisedTemplate.from_id_and_service_id(template_id, service.id)
    except NoResultFound:
        message = "Template not found"
        raise BadRequestError(message=message, fields=[{"template": message}])

    check_template_is_for_notification_type(notification_type, template.template_type)
    check_template_is_active(template)

    template_with_content = create_content_for_notification(template, personalisation)

    check_notification_content_is_not_empty(template_with_content)

    # validating the template in post_notifications happens before the file is uploaded for doc download,
    # which means the length of the message can be exceeded because it's including the file.
    # The document download feature is only available through the api.
    if check_char_count:
        check_is_message_too_long(template_with_content)

    return template, template_with_content


def check_reply_to(service_id, reply_to_id, type_):
    if type_ == NotificationType.EMAIL:
        return check_service_email_reply_to_id(service_id, reply_to_id, type_)
    elif type_ == NotificationType.SMS:
        return check_service_sms_sender_id(service_id, reply_to_id, type_)


def check_service_email_reply_to_id(service_id, reply_to_id, notification_type):
    if reply_to_id:
        try:
            return dao_get_reply_to_by_id(service_id, reply_to_id).email_address
        except NoResultFound:
            message = "email_reply_to_id {} does not exist in database for service id {}".format(
                reply_to_id, service_id
            )
            raise BadRequestError(message=message)


def check_service_sms_sender_id(service_id, sms_sender_id, notification_type):
    if sms_sender_id:
        try:
            return dao_get_service_sms_senders_by_id(
                service_id, sms_sender_id
            ).sms_sender
        except NoResultFound:
            message = (
                "sms_sender_id {} does not exist in database for service id {}".format(
                    sms_sender_id, service_id
                )
            )
            raise BadRequestError(message=message)
