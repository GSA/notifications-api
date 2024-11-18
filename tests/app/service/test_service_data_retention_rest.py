import json
import uuid

from sqlalchemy import select

from app import db
from app.enums import NotificationType
from app.models import ServiceDataRetention
from tests import create_admin_authorization_header
from tests.app.db import create_service_data_retention


def test_get_service_data_retention(client, sample_service):
    sms_data_retention = create_service_data_retention(service=sample_service)
    email_data_retention = create_service_data_retention(
        service=sample_service,
        notification_type=NotificationType.EMAIL,
        days_of_retention=10,
    )

    response = client.get(
        f"/service/{sample_service.id!s}/data-retention",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )

    assert response.status_code == 200
    json_response = json.loads(response.get_data(as_text=True))
    assert len(json_response) == 2
    assert json_response[0] == sms_data_retention.serialize()
    assert json_response[1] == email_data_retention.serialize()


def test_get_service_data_retention_returns_empty_list(client, sample_service):
    response = client.get(
        f"/service/{sample_service.id!s}/data-retention",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    assert len(json.loads(response.get_data(as_text=True))) == 0


def test_get_data_retention_for_service_notification_type(client, sample_service):
    data_retention = create_service_data_retention(service=sample_service)
    response = client.get(
        f"/service/{sample_service.id}/data-retention/"
        f"notification-type/{NotificationType.SMS}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == data_retention.serialize()


def test_get_service_data_retention_by_id(client, sample_service):
    sms_data_retention = create_service_data_retention(service=sample_service)
    create_service_data_retention(
        service=sample_service,
        notification_type=NotificationType.EMAIL,
        days_of_retention=10,
    )
    create_service_data_retention(
        service=sample_service,
        notification_type=NotificationType.LETTER,
        days_of_retention=30,
    )
    response = client.get(
        f"/service/{sample_service.id!s}/data-retention/{sms_data_retention.id}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == sms_data_retention.serialize()


def test_get_service_data_retention_by_id_returns_none_when_no_data_retention_exists(
    client, sample_service
):
    response = client.get(
        f"/service/{sample_service.id!s}/data-retention/{uuid.uuid4()}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {}


def test_create_service_data_retention(client, sample_service):
    data = {"notification_type": NotificationType.SMS, "days_of_retention": 3}
    response = client.post(
        f"/service/{sample_service.id!s}/data-retention",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps(data),
    )

    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))["result"]
    results = db.session.execute(select(ServiceDataRetention)).scalars().all()
    assert len(results) == 1
    data_retention = results[0]
    assert json_resp == data_retention.serialize()


def test_create_service_data_retention_returns_400_when_notification_type_is_invalid(
    client,
):
    data = {"notification_type": "unknown", "days_of_retention": 3}
    response = client.post(
        f"/service/{uuid.uuid4()!s}/data-retention",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps(data),
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp["errors"][0]["error"] == "ValidationError"
    type_str = ", ".join(
        [
            f"<{type(e).__name__}.{e.name}: {e.value}>"
            for e in (NotificationType.SMS, NotificationType.EMAIL)
        ]
    )
    assert (
        json_resp["errors"][0]["message"]
        == f"notification_type unknown is not one of [{type_str}]"
    )


def test_create_service_data_retention_returns_400_when_data_retention_for_notification_type_already_exists(
    client, sample_service
):
    create_service_data_retention(service=sample_service)
    data = {"notification_type": NotificationType.SMS, "days_of_retention": 3}
    response = client.post(
        f"/service/{uuid.uuid4()!s}/data-retention",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps(data),
    )

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert (
        json_resp["message"]
        == "Service already has data retention for sms notification type"
    )


def test_modify_service_data_retention(client, sample_service):
    data_retention = create_service_data_retention(service=sample_service)
    data = {"days_of_retention": 3}
    response = client.post(
        f"/service/{sample_service.id}/data-retention/{data_retention.id}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps(data),
    )
    assert response.status_code == 204
    assert response.get_data(as_text=True) == ""


def test_modify_service_data_retention_returns_400_when_data_retention_does_not_exist(
    client, sample_service
):
    data = {"days_of_retention": 3}
    response = client.post(
        f"/service/{sample_service.id}/data-retention/{uuid.uuid4()}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps(data),
    )

    assert response.status_code == 404


def test_modify_service_data_retention_returns_400_when_data_is_invalid(client):
    data = {"bad_key": 3}
    response = client.post(
        f"/service/{uuid.uuid4()}/data-retention/{uuid.uuid4()}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps(data),
    )
    assert response.status_code == 400
