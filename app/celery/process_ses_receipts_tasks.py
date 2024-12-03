from datetime import timedelta

import iso8601
from flask import current_app, json
from sqlalchemy.orm.exc import NoResultFound

from app import notify_celery
from app.celery.service_callback_tasks import (
    create_complaint_callback_data,
    create_delivery_status_callback_data,
    send_complaint_to_service,
    send_delivery_status_to_service,
)
from app.config import QueueNames
from app.dao import notifications_dao
from app.dao.complaint_dao import save_complaint
from app.dao.notifications_dao import dao_get_notification_history_by_reference
from app.dao.service_callback_api_dao import (
    get_service_complaint_callback_api_for_service,
    get_service_delivery_status_callback_api_for_service,
)
from app.enums import CallbackType, NotificationStatus
from app.models import Complaint
from app.utils import utc_now


@notify_celery.task(
    bind=True,
    name="process-ses-result",
    max_retries=5,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def process_ses_results(self, response):
    try:
        ses_message = json.loads(response["Message"])
        notification_type = ses_message["notificationType"]
        # TODO remove after smoke testing on prod is implemented
        current_app.logger.info(
            f"Attempting to process SES delivery status message "
            f"from SNS with type: {notification_type} and body: {ses_message}"
        )
        bounce_message = None

        if notification_type == "Bounce":
            bounce_message = determine_notification_bounce_type(ses_message)
        elif notification_type == "Complaint":
            _check_and_queue_complaint_callback_task(*handle_complaint(ses_message))
            return True

        aws_response_dict = get_aws_responses(ses_message)

        notification_status = aws_response_dict["notification_status"]
        reference = ses_message["mail"]["messageId"]

        try:
            notification = notifications_dao.dao_get_notification_by_reference(
                reference
            )
        except NoResultFound:
            message_time = iso8601.parse_date(ses_message["mail"]["timestamp"]).replace(
                tzinfo=None
            )
            if utc_now() - message_time < timedelta(minutes=5):
                current_app.logger.info(
                    f"Notification not found for reference: {reference}"
                    f"(while attempting update to {notification_status}). "
                    f"Callback may have arrived before notification was"
                    f"persisted to the DB. Adding task to retry queue"
                )
                raise
            else:
                current_app.logger.warning(
                    f"Notification not found for reference: {reference} "
                    f"(while attempting update to {notification_status})"
                )
            return

        if bounce_message:
            current_app.logger.info(
                f"SES bounce for notification ID {notification.id}: {bounce_message}"
            )

        if notification.status not in {
            NotificationStatus.SENDING,
            NotificationStatus.PENDING,
        }:
            notifications_dao._duplicate_update_warning(
                notification, notification_status
            )
            return

        notifications_dao._update_notification_status(
            notification=notification,
            status=notification_status,
            provider_response=aws_response_dict["provider_response"],
        )

        if not aws_response_dict["success"]:
            current_app.logger.info(
                "SES delivery failed: notification id {} and reference {} has error found. Status {}".format(
                    notification.id, reference, aws_response_dict["message"]
                )
            )
        else:
            current_app.logger.info(
                "SES callback return status of {} for notification: {}".format(
                    notification_status, notification.id
                )
            )

        check_and_queue_callback_task(notification)

        return True

    except Exception:
        current_app.logger.exception("Error processing SES results")
        raise


def determine_notification_bounce_type(ses_message):
    notification_type = ses_message["notificationType"]
    if notification_type in ["Delivery", "Complaint"]:
        return notification_type

    if notification_type != "Bounce":
        raise KeyError(f"Unhandled sns notification type {notification_type}")

    remove_emails_from_bounce(ses_message)
    current_app.logger.info(
        "SES bounce dict: {}".format(
            json.dumps(ses_message).replace("{", "(").replace("}", ")")
        )
    )
    if ses_message["bounce"]["bounceType"] == "Permanent":
        return "Permanent"
    return "Temporary"


def determine_notification_type(ses_message):
    notification_type = ses_message["notificationType"]
    if notification_type not in ["Bounce", "Complaint", "Delivery"]:
        raise KeyError(f"Unhandled sns notification type {notification_type}")
    if notification_type == "Bounce":
        return determine_notification_bounce_type(ses_message)
    return notification_type


def _determine_provider_response(ses_message):
    if ses_message["notificationType"] != "Bounce":
        return None

    bounce_type = ses_message["bounce"]["bounceType"]
    bounce_subtype = ses_message["bounce"]["bounceSubType"]

    # See https://docs.aws.amazon.com/ses/latest/DeveloperGuide/event-publishing-retrieving-sns-contents.html
    if bounce_type == "Permanent" and bounce_subtype == "Suppressed":
        return "The email address is on our email provider suppression list"
    elif bounce_type == "Permanent" and bounce_subtype == "OnAccountSuppressionList":
        return "The email address is on the GC Notify suppression list"
    elif bounce_type == "Transient" and bounce_subtype == "AttachmentRejected":
        return "The email was rejected because of its attachments"

    return None


def get_aws_responses(ses_message):
    status = determine_notification_type(ses_message)

    base = {
        "Permanent": {
            "message": "Hard bounced",
            "success": False,
            "notification_status": NotificationStatus.PERMANENT_FAILURE,
        },
        "Temporary": {
            "message": "Soft bounced",
            "success": False,
            "notification_status": NotificationStatus.TEMPORARY_FAILURE,
        },
        "Delivery": {
            "message": "Delivered",
            "success": True,
            "notification_status": NotificationStatus.DELIVERED,
        },
        "Complaint": {
            "message": "Complaint",
            "success": True,
            "notification_status": NotificationStatus.DELIVERED,
        },
    }[status]

    base["provider_response"] = _determine_provider_response(ses_message)

    return base


def handle_complaint(ses_message):
    recipient_email = remove_emails_from_complaint(ses_message)[0]
    current_app.logger.info(
        "Complaint from SES: \n{}".format(
            json.dumps(ses_message).replace("{", "(").replace("}", ")")
        )
    )
    try:
        reference = ses_message["mail"]["messageId"]
    except KeyError:
        current_app.logger.exception(
            "Complaint from SES failed to get reference from message"
        )
        return
    notification = dao_get_notification_history_by_reference(reference)
    ses_complaint = ses_message.get(CallbackType.COMPLAINT, None)

    complaint = Complaint(
        notification_id=notification.id,
        service_id=notification.service_id,
        ses_feedback_id=(
            ses_complaint.get("feedbackId", None) if ses_complaint else None
        ),
        complaint_type=(
            ses_complaint.get("complaintFeedbackType", None) if ses_complaint else None
        ),
        complaint_date=ses_complaint.get("timestamp", None) if ses_complaint else None,
    )
    save_complaint(complaint)
    return complaint, notification, recipient_email


def remove_mail_headers(dict_to_edit):
    if dict_to_edit["mail"].get("headers"):
        dict_to_edit["mail"].pop("headers")
    if dict_to_edit["mail"].get("commonHeaders"):
        dict_to_edit["mail"].pop("commonHeaders")


def remove_emails_from_bounce(bounce_dict):
    remove_mail_headers(bounce_dict)
    bounce_dict["mail"].pop("destination", None)
    bounce_dict["bounce"].pop("bouncedRecipients", None)


def remove_emails_from_complaint(complaint_dict):
    remove_mail_headers(complaint_dict)
    complaint_dict[CallbackType.COMPLAINT].pop("complainedRecipients")
    return complaint_dict["mail"].pop("destination")


def check_and_queue_callback_task(notification):
    # queue callback task only if the service_callback_api exists
    service_callback_api = get_service_delivery_status_callback_api_for_service(
        service_id=notification.service_id
    )
    if service_callback_api:
        notification_data = create_delivery_status_callback_data(
            notification, service_callback_api
        )
        send_delivery_status_to_service.apply_async(
            [str(notification.id), notification_data], queue=QueueNames.CALLBACKS
        )


def _check_and_queue_complaint_callback_task(complaint, notification, recipient):
    # queue callback task only if the service_callback_api exists
    service_callback_api = get_service_complaint_callback_api_for_service(
        service_id=notification.service_id
    )
    if service_callback_api:
        complaint_data = create_complaint_callback_data(
            complaint, notification, service_callback_api, recipient
        )
        send_complaint_to_service.apply_async(
            [complaint_data], queue=QueueNames.CALLBACKS
        )
