import functools
import uuid

import botocore
from flask import abort, current_app, jsonify, request

from app import api_user, authenticated_service, document_download_client, encryption
from app.celery.tasks import save_api_email, save_api_sms
from app.clients.document_download import DocumentDownloadError
from app.config import QueueNames
from app.enums import KeyType, NotificationStatus, NotificationType
from app.models import Notification
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue_detached,
    simulated_recipient,
)
from app.notifications.validators import (
    check_if_service_can_send_files_by_email,
    check_is_message_too_long,
    check_service_email_reply_to_id,
    check_service_has_permission,
    check_service_sms_sender_id,
    validate_and_format_recipient,
    validate_template,
)
from app.schema_validation import validate
from app.utils import DATETIME_FORMAT, utc_now
from app.v2.errors import BadRequestError
from app.v2.notifications import v2_notification_blueprint
from app.v2.notifications.create_response import (
    create_post_email_response_from_notification,
    create_post_sms_response_from_notification,
)
from app.v2.notifications.notification_schemas import (
    post_email_request,
    post_sms_request,
)
from app.v2.utils import get_valid_json
from notifications_utils.recipients import try_validate_and_format_phone_number


@v2_notification_blueprint.route("/<notification_type>", methods=["POST"])
def post_notification(notification_type):
    request_json = get_valid_json()

    if notification_type == NotificationType.EMAIL:
        form = validate(request_json, post_email_request)
    elif notification_type == NotificationType.SMS:
        form = validate(request_json, post_sms_request)
    else:
        abort(404)

    check_service_has_permission(notification_type, authenticated_service.permissions)

    template, template_with_content = validate_template(
        form["template_id"],
        form.get("personalisation", {}),
        authenticated_service,
        notification_type,
        check_char_count=False,
    )

    reply_to = get_reply_to_text(notification_type, form, template)

    notification = process_sms_or_email_notification(
        form=form,
        notification_type=notification_type,
        template=template,
        template_with_content=template_with_content,
        template_process_type=template.process_type,
        service=authenticated_service,
        reply_to_text=reply_to,
    )

    return jsonify(notification), 201


def process_sms_or_email_notification(
    *,
    form,
    notification_type,
    template,
    template_with_content,
    service,
    reply_to_text=None,
):
    notification_id = uuid.uuid4()
    form_send_to = (
        form["email_address"]
        if notification_type == NotificationType.EMAIL
        else form["phone_number"]
    )

    send_to = validate_and_format_recipient(
        send_to=form_send_to,
        key_type=api_user.key_type,
        service=service,
        notification_type=notification_type,
    )

    # Do not persist or send notification to the queue if it is a simulated recipient
    simulated = simulated_recipient(send_to, notification_type)

    personalisation, document_download_count = process_document_uploads(
        form.get("personalisation"), service, simulated=simulated
    )
    if document_download_count:
        # We changed personalisation which means we need to update the content
        template_with_content.values = personalisation

    # validate content length after url is replaced in personalisation.
    check_is_message_too_long(template_with_content)

    resp = create_response_for_post_notification(
        notification_id=notification_id,
        client_reference=form.get("reference", None),
        template_id=template.id,
        template_version=template.version,
        service_id=service.id,
        notification_type=notification_type,
        reply_to=reply_to_text,
        template_with_content=template_with_content,
    )

    if (
        service.high_volume
        and api_user.key_type == KeyType.NORMAL
        and notification_type in {NotificationType.EMAIL, NotificationType.SMS}
    ):
        # Put service with high volumes of notifications onto a queue
        # To take the pressure off the db for API requests put the notification for our high volume service onto a queue
        # the task will then save the notification, then call send_notification_to_queue.
        # NOTE: The high volume service should be aware that the notification is not immediately
        # available by a GET request, it is recommend they use callbacks to keep track of status updates.
        try:
            save_email_or_sms_to_queue(
                form=form,
                notification_id=str(notification_id),
                notification_type=notification_type,
                api_key=api_user,
                template=template,
                service_id=service.id,
                personalisation=personalisation,
                document_download_count=document_download_count,
                reply_to_text=reply_to_text,
            )
            return resp
        except (botocore.exceptions.ClientError, botocore.parsers.ResponseParserError):
            # If SQS cannot put the task on the queue, it's probably because the notification body was too long and it
            # went over SQS's 256kb message limit. If the body is very large, it may exceed the HTTP max content length;
            # the exception we get here isn't handled correctly by botocore - we get a ResponseParserError instead.
            # Hopefully this is no longer an issue with Redis as celery's backing store
            current_app.logger.info(
                f"Notification {notification_id} failed to save to high volume queue. Using normal flow instead"
            )

    persist_notification(
        notification_id=notification_id,
        template_id=template.id,
        template_version=template.version,
        recipient=form_send_to,
        service=service,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=api_user.id,
        key_type=api_user.key_type,
        client_reference=form.get("reference", None),
        simulated=simulated,
        reply_to_text=reply_to_text,
        document_download_count=document_download_count,
    )

    if not simulated:
        queue_name = None
        send_notification_to_queue_detached(
            key_type=api_user.key_type,
            notification_type=notification_type,
            notification_id=notification_id,
            queue=queue_name,
        )
    else:
        current_app.logger.debug(
            "POST simulated notification for id: {}".format(notification_id)
        )

    return resp


def save_email_or_sms_to_queue(
    *,
    notification_id,
    form,
    notification_type,
    api_key,
    template,
    service_id,
    personalisation,
    document_download_count,
    reply_to_text=None,
):
    data = {
        "id": notification_id,
        "template_id": str(template.id),
        "template_version": template.version,
        "to": (
            form["email_address"]
            if notification_type == NotificationType.EMAIL
            else form["phone_number"]
        ),
        "service_id": str(service_id),
        "personalisation": personalisation,
        "notification_type": notification_type,
        "api_key_id": str(api_key.id),
        "key_type": api_key.key_type,
        "client_reference": form.get("reference", None),
        "reply_to_text": reply_to_text,
        "document_download_count": document_download_count,
        "status": NotificationStatus.CREATED,
        "created_at": utc_now().strftime(DATETIME_FORMAT),
    }
    encrypted = encryption.encrypt(data)

    if notification_type == NotificationType.EMAIL:
        save_api_email.apply_async([encrypted], queue=QueueNames.SAVE_API_EMAIL)
    elif notification_type == NotificationType.SMS:
        save_api_sms.apply_async([encrypted], queue=QueueNames.SAVE_API_SMS)

    return Notification(**data)


def process_document_uploads(personalisation_data, service, simulated=False):
    """
    Returns modified personalisation dict and a count of document uploads. If there are no document uploads, returns
    a count of `None` rather than `0`.
    """
    file_keys = [
        k
        for k, v in (personalisation_data or {}).items()
        if isinstance(v, dict) and "file" in v
    ]
    if not file_keys:
        return personalisation_data, None

    personalisation_data = personalisation_data.copy()

    check_if_service_can_send_files_by_email(
        service_contact_link=authenticated_service.contact_link,
        service_id=authenticated_service.id,
    )

    for key in file_keys:
        if simulated:
            personalisation_data[key] = (
                document_download_client.get_upload_url(service.id) + "/test-document"
            )
        else:
            try:
                personalisation_data[key] = document_download_client.upload_document(
                    service.id,
                    personalisation_data[key]["file"],
                    personalisation_data[key].get("is_csv"),
                )
            except DocumentDownloadError as e:
                raise BadRequestError(message=e.message, status_code=e.status_code)

    return personalisation_data, len(file_keys)


def get_reply_to_text(notification_type, form, template):
    reply_to = None
    if notification_type == NotificationType.EMAIL:
        service_email_reply_to_id = form.get("email_reply_to_id", None)
        reply_to = (
            check_service_email_reply_to_id(
                str(authenticated_service.id),
                service_email_reply_to_id,
                notification_type,
            )
            or template.reply_to_text
        )

    elif notification_type == NotificationType.SMS:
        service_sms_sender_id = form.get("sms_sender_id", None)
        sms_sender_id = check_service_sms_sender_id(
            str(authenticated_service.id), service_sms_sender_id, notification_type
        )
        if sms_sender_id:
            reply_to = try_validate_and_format_phone_number(sms_sender_id)
        else:
            reply_to = template.reply_to_text

    return reply_to


def create_response_for_post_notification(
    notification_id,
    client_reference,
    template_id,
    template_version,
    service_id,
    notification_type,
    reply_to,
    template_with_content,
):
    if notification_type == NotificationType.SMS:
        create_resp_partial = functools.partial(
            create_post_sms_response_from_notification,
            from_number=reply_to,
        )
    elif notification_type == NotificationType.EMAIL:
        create_resp_partial = functools.partial(
            create_post_email_response_from_notification,
            subject=template_with_content.subject,
            email_from="{}@{}".format(
                authenticated_service.email_from,
                current_app.config["NOTIFY_EMAIL_DOMAIN"],
            ),
        )
    resp = create_resp_partial(
        notification_id,
        client_reference,
        template_id,
        template_version,
        service_id,
        url_root=request.url_root,
        content=template_with_content.content_with_placeholders_filled_in,
    )
    return resp
