import pytest

from app.dao.api_key_dao import save_model_api_key
from app.enums import KeyType
from app.models import ApiKey
from app.v2.notifications.notification_schemas import (
    get_notification_response,
    get_notifications_response,
)
from tests import create_service_authorization_header

from . import return_json_from_response, validate, validate_v0


def _get_notification(client, notification, url):
    save_model_api_key(
        ApiKey(
            service=notification.service,
            name="api_key",
            created_by=notification.service.created_by,
            key_type=KeyType.NORMAL,
        )
    )
    auth_header = create_service_authorization_header(
        service_id=notification.service_id
    )
    return client.get(url, headers=[auth_header])


# v2


def test_get_v2_sms_contract(client, sample_notification, mocker):
    mock_s3_personalisation = mocker.patch(
        "app.v2.notifications.get_notifications.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {}
    response_json = return_json_from_response(
        _get_notification(
            client,
            sample_notification,
            "/v2/notifications/{}".format(sample_notification.id),
        )
    )
    validate(response_json, get_notification_response)


def test_get_v2_email_contract(client, sample_email_notification, mocker):
    mock_s3_personalisation = mocker.patch(
        "app.v2.notifications.get_notifications.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {}
    response_json = return_json_from_response(
        _get_notification(
            client,
            sample_email_notification,
            "/v2/notifications/{}".format(sample_email_notification.id),
        )
    )
    validate(response_json, get_notification_response)


def test_get_v2_notifications_contract(client, sample_notification):
    response_json = return_json_from_response(
        _get_notification(client, sample_notification, "/v2/notifications")
    )
    validate(response_json, get_notifications_response)


# v0


def test_get_api_sms_contract(client, sample_notification):
    response_json = return_json_from_response(
        _get_notification(
            client,
            sample_notification,
            "/notifications/{}".format(sample_notification.id),
        )
    )
    validate_v0(response_json, "GET_notification_return_sms.json")


@pytest.mark.skip(reason="Update to fetch email from s3")
def test_get_api_email_contract(client, sample_email_notification):
    response_json = return_json_from_response(
        _get_notification(
            client,
            sample_email_notification,
            "/notifications/{}".format(sample_email_notification.id),
        )
    )
    validate_v0(response_json, "GET_notification_return_email.json")


def test_get_job_sms_contract(client, sample_notification):
    response_json = return_json_from_response(
        _get_notification(
            client,
            sample_notification,
            "/notifications/{}".format(sample_notification.id),
        )
    )
    validate_v0(response_json, "GET_notification_return_sms.json")


@pytest.mark.skip(reason="Update to fetch email from s3")
def test_get_job_email_contract(client, sample_email_notification):
    response_json = return_json_from_response(
        _get_notification(
            client,
            sample_email_notification,
            "/notifications/{}".format(sample_email_notification.id),
        )
    )
    validate_v0(response_json, "GET_notification_return_email.json")


def test_get_notifications_contract(
    client, sample_notification, sample_email_notification
):
    response_json = return_json_from_response(
        _get_notification(client, sample_notification, "/notifications")
    )
    validate_v0(response_json, "GET_notifications_return.json")
