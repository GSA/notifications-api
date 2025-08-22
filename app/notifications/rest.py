import gevent
from flask import Blueprint, current_app, jsonify, request

from app import api_user, authenticated_service
from app.aws.s3 import get_personalisation_from_s3, get_phone_number_from_s3
from app.dao import notifications_dao
from app.enums import KeyType, NotificationType
from app.errors import InvalidRequest, register_errors
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
    simulated_recipient,
)
from app.notifications.validators import (
    check_if_service_can_send_to_number,
    service_has_permission,
    validate_template,
)
from app.public_schemas.public import PublicNotificationResponseSchema
from app.schemas import (
    email_notification_schema,
    notifications_filter_schema,
    sms_template_notification_schema,
)
from app.service.utils import service_allowed_to_send_to
from app.utils import (
    check_suspicious_id,
    get_public_notify_type_text,
    get_template_instance,
    pagination_links,
    template_model_to_dict,
)
from notifications_utils import SMS_CHAR_COUNT_LIMIT

notifications = Blueprint("notifications", __name__)
register_errors(notifications)


@notifications.route("/notifications/<uuid:notification_id>", methods=["GET"])
def get_notification_by_id(notification_id):
    check_suspicious_id(notification_id)
    notification = notifications_dao.get_notification_with_personalisation(
        str(authenticated_service.id), notification_id, key_type=None
    )

    if notification.job_id is not None:
        notification.personalisation = get_personalisation_from_s3(
            notification.service_id,
            notification.job_id,
            notification.job_row_number,
        )
        recipient = get_phone_number_from_s3(
            notification.service_id,
            notification.job_id,
            notification.job_row_number,
        )
        notification.to = recipient
        notification.normalised_to = recipient

    if not hasattr(notification, "body") or not notification.body:
        template_dict = template_model_to_dict(notification.template)
        template = get_template_instance(
            template_dict, notification.personalisation or {}
        )
        notification.body = template.content_with_placeholders_filled_in

    schema = PublicNotificationResponseSchema()
    schema.context = {
        "notification_instance": notification,
        "template_subject": (
            getattr(template, "subject", None) if hasattr(template, "subject") else None
        ),
    }
    serialized = schema.dump(notification)

    return jsonify(data={"notification": serialized}), 200


@notifications.route("/notifications", methods=["GET"])
def get_all_notifications():
    current_app.logger.debug("enter get_all_notifications()")
    data = notifications_filter_schema.load(request.args)
    current_app.logger.debug(
        f"get_all_notifications() data {data} request.args {request.args}"
    )

    include_jobs = data.get("include_jobs", False)
    page = data.get("page", 1)
    page_size = data.get("page_size", current_app.config.get("API_PAGE_SIZE"))
    limit_days = data.get("limit_days")
    gevent.sleep(0)  # keep this connection alive
    pagination = notifications_dao.get_notifications_for_service(
        str(authenticated_service.id),
        personalisation=True,
        filter_dict=data,
        page=page,
        page_size=page_size,
        limit_days=limit_days,
        key_type=api_user.key_type,
        include_jobs=include_jobs,
    )
    gevent.sleep(0)  # keep this connection alive

    serialized = []
    for notification in pagination.items:
        personalisation = notification.personalisation

        if notification.job_id is not None:
            personalisation = get_personalisation_from_s3(
                notification.service_id,
                notification.job_id,
                notification.job_row_number,
            )
            recipient = get_phone_number_from_s3(
                notification.service_id,
                notification.job_id,
                notification.job_row_number,
            )
            # Safe to set dynamically for serialization purposes
            notification.to = recipient
            notification.normalised_to = recipient

        subject = None

        if not getattr(notification, "body", None):
            template_dict = template_model_to_dict(notification.template)
            template = get_template_instance(template_dict, personalisation or {})
            notification.body = template.content_with_placeholders_filled_in
            if hasattr(template, "subject"):
                subject = template.subject

        notification.personalisation = personalisation

        schema = PublicNotificationResponseSchema()
        schema.context = {"notification_instance": notification}
        notification_data = schema.dump(notification)

        if subject is not None:
            notification_data["subject"] = subject

        serialized.append(notification_data)
        gevent.sleep(0)  # keep this connection alive

    result = jsonify(
        notifications=serialized,
        page_size=page_size,
        total=pagination.total,
        links=pagination_links(
            pagination, ".get_all_notifications", **request.args.to_dict()
        ),
    )
    return result, 200


@notifications.route("/notifications/<string:notification_type>", methods=["POST"])
def send_notification(notification_type):
    if notification_type not in {NotificationType.SMS, NotificationType.EMAIL}:
        raise InvalidRequest(
            f"{notification_type} notification type is not supported", 400
        )

    notification_form = (
        sms_template_notification_schema
        if notification_type == NotificationType.SMS
        else email_notification_schema
    ).load(request.get_json())

    template, template_with_content = validate_template(
        template_id=notification_form["template"],
        personalisation=notification_form.get("personalisation", {}),
        service=authenticated_service,
        notification_type=notification_type,
    )

    _service_allowed_to_send_to(notification_form, authenticated_service)

    if not service_has_permission(notification_type, authenticated_service.permissions):
        raise InvalidRequest(
            {
                "service": [
                    f"Cannot send {get_public_notify_type_text(notification_type, plural=True)}"
                ]
            },
            400,
        )

    if notification_type == NotificationType.SMS:
        check_if_service_can_send_to_number(
            authenticated_service, notification_form["to"]
        )

    simulated = simulated_recipient(notification_form["to"], notification_type)

    notification_model = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=notification_form["to"],
        service=authenticated_service,
        personalisation=notification_form.get("personalisation"),
        notification_type=notification_type,
        api_key_id=api_user.id,
        key_type=api_user.key_type,
        simulated=simulated,
        reply_to_text=template.reply_to_text,
    )

    if not simulated:
        send_notification_to_queue(notification=notification_model, queue=None)
    else:
        current_app.logger.debug(
            f"POST simulated notification for id: {notification_model.id}"
        )

    notification_form.update({"template_version": template.version})

    return (
        jsonify(
            data=get_notification_return_data(
                notification_model.id, notification_form, template_with_content
            )
        ),
        201,
    )


def get_notification_return_data(notification_id, notification, template):
    output = {
        "template_version": notification["template_version"],
        "notification": {"id": notification_id},
        "body": template.content_with_placeholders_filled_in,
    }
    if hasattr(template, "subject"):
        output["subject"] = template.subject
    return output


def _service_allowed_to_send_to(notification, service):
    if not service_allowed_to_send_to(notification["to"], service, api_user.key_type):
        if api_user.key_type == KeyType.TEAM:
            message = "Can’t send to this recipient using a team-only API key"
        else:
            message = (
                "Can’t send to this recipient when service is in trial mode "
                "– see https://www.notifications.service.gov.uk/trial-mode"
            )
        raise InvalidRequest({"to": [message]}, 400)


def create_template_object_for_notification(template, personalisation):
    template_object = template._as_utils_template_with_personalisation(personalisation)

    if template_object.missing_data:
        message = "Missing personalisation: {}".format(
            ", ".join(template_object.missing_data)
        )
        raise InvalidRequest({"template": [message]}, 400)

    if (
        template_object.template_type == NotificationType.SMS
        and template_object.is_message_too_long()
    ):
        raise InvalidRequest(
            {
                "content": [
                    f"Content has a character count greater than the limit of {SMS_CHAR_COUNT_LIMIT}"
                ]
            },
            400,
        )
    return template_object
