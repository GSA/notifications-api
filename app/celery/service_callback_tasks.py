import json
from functools import wraps
from inspect import signature

from flask import current_app
from requests import HTTPError, RequestException, request

from app import encryption, notify_celery
from app.utils import DATETIME_FORMAT


def _send_to_service_task_handler(func):
    @wraps(func)
    def send_to_service_task_wrapper(*args, **kwargs):
        sig = signature(func)
        bargs = sig.bind(*args, **kwargs)
        bargs.apply_defaults()

        function_name = func.__name__

        if function_name == "send_delivery_status_to_service":
            encrypted_status_update = bargs.arguments["encrypted_status_update"]

            status_update = encryption.decrypt(encrypted_status_update)
            service_callback_url = status_update["service_callback_api_url"]

            notification_id = bargs.arguments["notification_id"]

        elif function_name == "send_complaint_to_service":
            complaint_data = bargs.arguments["complaint_data"]

            notification_id = complaint_data["notification_id"]
            service_callback_url = complaint_data["service_callback_api_url"]

        else:
            raise ValueError(
                f"Incorrect send to service function name found: {function_name}"
            )

        self_ = bargs.arguments["self"]

        try:
            return func(*args, **kwargs)
        except self_.MaxRetriesExceededError:
            current_app.logger.warning(
                f"Retry: {function_name} has retried the max num of times for callback url "
                f"{service_callback_url} and notification_id: {notification_id}"
            )
            raise

    return send_to_service_task_wrapper


@_send_to_service_task_handler
@notify_celery.task(
    bind=True,
    name="send-delivery-status",
    max_retries=5,
    default_retry_delay=300,
    autoretry_for=HTTPError,
)
def send_delivery_status_to_service(self, notification_id, encrypted_status_update):
    status_update = encryption.decrypt(encrypted_status_update)

    data = {
        "id": str(notification_id),
        "reference": status_update["notification_client_reference"],
        "to": status_update["notification_to"],
        "status": status_update["notification_status"],
        "created_at": status_update["notification_created_at"],
        "completed_at": status_update["notification_updated_at"],
        "sent_at": status_update["notification_sent_at"],
        "notification_type": status_update["notification_type"],
        "template_id": status_update["template_id"],
        "template_version": status_update["template_version"],
    }

    _send_data_to_service_callback_api(
        self,
        data,
        status_update["service_callback_api_url"],
        status_update["service_callback_api_bearer_token"],
        "send_delivery_status_to_service",
    )


@_send_to_service_task_handler
@notify_celery.task(
    bind=True,
    name="send-complaint",
    max_retries=5,
    default_retry_delay=300,
    autoretry_for=HTTPError,
)
def send_complaint_to_service(self, complaint_data):
    complaint = encryption.decrypt(complaint_data)

    data = {
        "notification_id": complaint["notification_id"],
        "complaint_id": complaint["complaint_id"],
        "reference": complaint["reference"],
        "to": complaint["to"],
        "complaint_date": complaint["complaint_date"],
    }

    _send_data_to_service_callback_api(
        self,
        data,
        complaint["service_callback_api_url"],
        complaint["service_callback_api_bearer_token"],
        "send_complaint_to_service",
    )


def _send_data_to_service_callback_api(
    self, data, service_callback_url, token, function_name
):
    notification_id = (
        data["notification_id"] if "notification_id" in data else data["id"]
    )
    try:
        response = request(
            method="POST",
            url=service_callback_url,
            data=json.dumps(data),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=5,
        )
        current_app.logger.info(
            f"{function_name} sending {notification_id} to {service_callback_url}, response {response.status_code}"
        )
        response.raise_for_status()
    except RequestException as e:
        current_app.logger.warning(
            f"{function_name} request failed for notification_id: {notification_id} and "
            f"url: {service_callback_url}. exception: {e}"
        )
        if (
            not isinstance(e, HTTPError)
            or e.response.status_code >= 500
            or e.response.status_code == 429
        ):
            raise
        else:
            current_app.logger.warning(
                f"{function_name} callback is not being retried for notification_id: "
                f"{notification_id} and url: {service_callback_url}. exception: {e}"
            )


def create_delivery_status_callback_data(notification, service_callback_api):
    data = {
        "notification_id": str(notification.id),
        "notification_client_reference": notification.client_reference,
        "notification_to": notification.to,
        "notification_status": notification.status,
        "notification_provider_response": notification.provider_response,  # TODO do we test for provider_response?
        "notification_created_at": notification.created_at.strftime(DATETIME_FORMAT),
        "notification_updated_at": (
            notification.updated_at.strftime(DATETIME_FORMAT)
            if notification.updated_at
            else None
        ),
        "notification_sent_at": (
            notification.sent_at.strftime(DATETIME_FORMAT)
            if notification.sent_at
            else None
        ),
        "notification_type": notification.notification_type,
        "service_callback_api_url": service_callback_api.url,
        "service_callback_api_bearer_token": service_callback_api.bearer_token,
        "template_id": str(notification.template_id),
        "template_version": notification.template_version,
    }
    return encryption.encrypt(data)


def create_complaint_callback_data(
    complaint, notification, service_callback_api, recipient
):
    data = {
        "complaint_id": str(complaint.id),
        "notification_id": str(notification.id),
        "reference": notification.client_reference,
        "to": recipient,
        "complaint_date": complaint.complaint_date.strftime(DATETIME_FORMAT),
        "service_callback_api_url": service_callback_api.url,
        "service_callback_api_bearer_token": service_callback_api.bearer_token,
    }
    return encryption.encrypt(data)
