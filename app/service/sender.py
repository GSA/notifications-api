import json

from flask import current_app

from app import redis_store
from app.config import QueueNames
from app.dao.services_dao import (
    dao_fetch_active_users_for_service,
    dao_fetch_service_by_id,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.enums import KeyType, TemplateType
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.utils import hilite


def send_notification_to_service_users(
    service_id, template_id, personalisation=None, include_user_fields=None
):
    personalisation = personalisation or {}
    include_user_fields = include_user_fields or []
    template = dao_get_template_by_id(template_id)
    service = dao_fetch_service_by_id(service_id)
    active_users = dao_fetch_active_users_for_service(service.id)
    print(hilite(f"ACTIVE USERS ARE {active_users}"))
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    for user in active_users:
        personalisation = _add_user_fields(user, personalisation, include_user_fields)
        print(hilite(f"PERSONALISATION IS {personalisation}"))
        notification = persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient=(
                user.email_address
                if template.template_type == TemplateType.EMAIL
                else user.mobile_number
            ),
            service=notify_service,
            personalisation=personalisation,
            notification_type=template.template_type,
            api_key_id=None,
            key_type=KeyType.NORMAL,
            reply_to_text=notify_service.get_default_reply_to_email_address(),
        )
        print(hilite(f"NOTIFICATION IS {notification.serialize_for_csv()}"))
        redis_store.set(
            f"email-personalisation-{notification.id}",
            json.dumps(personalisation),
            ex=24 * 60 * 60,
        )
        redis_store.set(
            f"email-recipient-{notification.id}", notification.to, ex=24 * 60 * 60
        )

        send_notification_to_queue(notification, queue=QueueNames.NOTIFY)
        return notification


def _add_user_fields(user, personalisation, fields):
    for field in fields:
        personalisation[field] = getattr(user, field)
    return personalisation
