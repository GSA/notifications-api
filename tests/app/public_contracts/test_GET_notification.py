from app.dao.api_key_dao import save_model_api_key
from app.enums import KeyType
from app.models import ApiKey
from tests import create_service_authorization_header

from . import return_json_from_response, validate_v0


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


def test_get_job_sms_contract(client, sample_notification):
    response_json = return_json_from_response(
        _get_notification(
            client,
            sample_notification,
            "/notifications/{}".format(sample_notification.id),
        )
    )
    validate_v0(response_json, "GET_notification_return_sms.json")


def test_get_notifications_contract(
    client, sample_notification, sample_email_notification
):
    response_json = return_json_from_response(
        _get_notification(client, sample_notification, "/notifications")
    )
    notifications = response_json["notifications"]
    assert notifications, "No notifications returned"
    assert notifications[0]["template"]["template_type"] == "sms"
    validate_v0(response_json, "GET_notifications_return.json")
