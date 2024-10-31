from base64 import b64encode
from datetime import datetime
from unittest import mock

import pytest
from flask import json
from sqlalchemy import func, select

from app import db
from app.enums import ServicePermissionType
from app.models import InboundSms
from app.notifications.receive_notifications import (
    create_inbound_sms_object,
    fetch_potential_service,
    has_inbound_sms_permissions,
    unescape_string,
)
from tests.app.db import (
    create_inbound_number,
    create_service,
    create_service_with_inbound_number,
)
from tests.conftest import set_config


def sns_post(client, data, auth=True, password="testkey"):
    headers = [
        ("Content-Type", "application/json"),
    ]

    if auth:
        auth_value = b64encode(f"notify:{password}".encode())
        headers.append(("Authorization", f"Basic {auth_value}"))

    return client.post(
        path="/notifications/sms/receive/sns", data={"Message": data}, headers=headers
    )


@pytest.mark.skip(reason="Need to implement SNS tests. Body here mostly from MMG")
def test_receive_notification_returns_received_to_sns(
    client, mocker, sample_service_full_permissions
):
    mocked = mocker.patch(
        "app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async"
    )
    prom_counter_labels_mock = mocker.patch(
        "app.notifications.receive_notifications.INBOUND_SMS_COUNTER.labels"
    )
    data = {
        "originationNumber": "+12028675309",
        "destinationNumber": sample_service_full_permissions.get_inbound_number(),
        "messageKeyword": "JOIN",
        "messageBody": "EXAMPLE",
        "inboundMessageId": "cae173d2-66b9-564c-8309-21f858e9fb84",
        "previousPublishedMessageId": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    }
    response = sns_post(client, data)

    assert response.status_code == 200
    result = json.loads(response.get_data(as_text=True))
    assert result["result"] == "success"

    prom_counter_labels_mock.assert_called_once_with("sns")
    prom_counter_labels_mock.return_value.inc.assert_called_once_with()

    inbound_sms_id = InboundSms.query.all()[0].id
    mocked.assert_called_once_with(
        [str(inbound_sms_id), str(sample_service_full_permissions.id)],
        queue="notify-internal-tasks",
    )


# TODO: figure out why creating a service first causes a db error
@pytest.mark.parametrize(
    "permissions",
    [
        [ServicePermissionType.SMS],
        [ServicePermissionType.INBOUND_SMS],
    ],
)
def test_receive_notification_from_sns_without_permissions_does_not_persist(
    client, mocker, notify_db_session, permissions
):
    mocked = mocker.patch(
        "app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async"
    )
    # create_service_with_inbound_number(inbound_number='12025550104', service_permissions=permissions)
    data = {
        "ID": "1234",
        "MSISDN": "12025550104",
        "Message": "Some message to notify",
        "Trigger": "Trigger?",
        "Number": "testing",
        "Channel": "SMS",
        "DateRecieved": "2012-06-27 12:33:00",
    }
    response = sns_post(client, data)
    assert response.status_code == 200

    parsed_response = json.loads(response.get_data(as_text=True))
    assert parsed_response["result"] == "success"

    stmt = select(func.count()).select_from(InboundSms)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 0
    assert mocked.called is False


@pytest.mark.skip(reason="Need to implement inbound SNS tests. Body here from MMG")
def test_receive_notification_without_permissions_does_not_create_inbound_even_with_inbound_number_set(
    client, mocker, sample_service
):
    inbound_number = create_inbound_number(
        "1", service_id=sample_service.id, active=True
    )

    mocked_send_inbound_sms = mocker.patch(
        "app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async"
    )
    mocked_has_permissions = mocker.patch(
        "app.notifications.receive_notifications.has_inbound_sms_permissions",
        return_value=False,
    )

    data = {
        "ID": "1234",
        "MSISDN": "447700900855",
        "Message": "Some message to notify",
        "Trigger": "Trigger?",
        "Number": inbound_number.number,
        "Channel": "SMS",
        "DateRecieved": "2012-06-27 12:33:00",
    }

    response = sns_post(client, data)

    assert response.status_code == 200
    assert len(InboundSms.query.all()) == 0
    assert mocked_has_permissions.called
    mocked_send_inbound_sms.assert_not_called()


@pytest.mark.parametrize(
    "permissions,expected_response",
    [
        ([ServicePermissionType.SMS, ServicePermissionType.INBOUND_SMS], True),
        ([ServicePermissionType.INBOUND_SMS], False),
        ([ServicePermissionType.SMS], False),
    ],
)
def test_check_permissions_for_inbound_sms(
    notify_db_session, permissions, expected_response
):
    service = create_service(service_permissions=permissions)
    assert has_inbound_sms_permissions(service.permissions) is expected_response


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "😬",
            "😬",
        ),
        (
            "1\\n2",
            "1\n2",
        ),
        (
            "\\'\"\\'",
            "'\"'",
        ),
        (
            """

        """,
            """

        """,
        ),
        (
            "\x79 \\x79 \\\\x79",  # we should never see the middle one
            "y y \\x79",
        ),
    ],
)
def test_unescape_string(raw, expected):
    assert unescape_string(raw) == expected


@pytest.mark.skip(reason="Need to implement inbound SNS tests. Body here from MMG")
def test_create_inbound_sns_sms_object(sample_service_full_permissions):
    data = {
        "Message": "hello+there+%F0%9F%93%A9",
        "Number": sample_service_full_permissions.get_inbound_number(),
        "MSISDN": "07700 900 001",
        "DateRecieved": "2017-01-02+03%3A04%3A05",
        "ID": "bar",
    }

    inbound_sms = create_inbound_sms_object(
        sample_service_full_permissions,
        data["Message"],
        data["MSISDN"],
        data["ID"],
        data["DateRecieved"],
        "sns",
    )

    assert inbound_sms.service_id == sample_service_full_permissions.id
    assert (
        inbound_sms.notify_number
        == sample_service_full_permissions.get_inbound_number()
    )
    assert inbound_sms.user_number == "447700900001"
    assert inbound_sms.provider_date == datetime(2017, 1, 2, 3, 4, 5)
    assert inbound_sms.provider_reference == "bar"
    assert inbound_sms._content != "hello there 📩"
    assert inbound_sms.content == "hello there 📩"
    assert inbound_sms.provider == "sns"


@pytest.mark.skip(reason="Need to implement inbound SNS tests. Body here from MMG")
def test_create_inbound_sns_sms_object_uses_inbound_number_if_set(
    sample_service_full_permissions,
):
    sample_service_full_permissions.sms_sender = "foo"
    inbound_number = sample_service_full_permissions.get_inbound_number()

    data = {
        "Message": "hello+there+%F0%9F%93%A9",
        "Number": sample_service_full_permissions.get_inbound_number(),
        "MSISDN": "07700 900 001",
        "DateRecieved": "2017-01-02+03%3A04%3A05",
        "ID": "bar",
    }

    inbound_sms = create_inbound_sms_object(
        sample_service_full_permissions,
        data["Message"],
        data["MSISDN"],
        data["ID"],
        data["DateRecieved"],
        "sns",
    )

    assert inbound_sms.service_id == sample_service_full_permissions.id
    assert inbound_sms.notify_number == inbound_number


@pytest.mark.skip(reason="Need to implement inbound SNS tests. Body here from MMG")
@pytest.mark.parametrize(
    "notify_number",
    ["foo", "baz"],
    ids=["two_matching_services", "no_matching_services"],
)
def test_receive_notification_error_if_not_single_matching_service(
    client, notify_db_session, notify_number
):
    create_service_with_inbound_number(
        inbound_number="dog",
        service_name="a",
        service_permissions=[
            ServicePermissionType.EMAIL,
            ServicePermissionType.SMS,
            ServicePermissionType.INBOUND_SMS,
        ],
    )
    create_service_with_inbound_number(
        inbound_number="bar",
        service_name="b",
        service_permissions=[
            ServicePermissionType.EMAIL,
            ServicePermissionType.SMS,
            ServicePermissionType.INBOUND_SMS,
        ],
    )

    data = {
        "Message": "hello",
        "Number": notify_number,
        "MSISDN": "7700900001",
        "DateRecieved": "2017-01-02 03:04:05",
        "ID": "bar",
    }
    response = sns_post(client, data)

    # we still return 'RECEIVED' to MMG
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "RECEIVED"

    stmt = select(func.count()).select_from(InboundSms)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 0


@pytest.mark.skip(reason="Need to implement inbound SNS tests. Body here from MMG")
@pytest.mark.parametrize(
    "auth, keys, status_code",
    [
        ["testkey", ["testkey"], 200],
        ["", ["testkey"], 401],
        ["wrong", ["testkey"], 403],
        ["testkey1", ["testkey1", "testkey2"], 200],
        ["testkey2", ["testkey1", "testkey2"], 200],
        ["wrong", ["testkey1", "testkey2"], 403],
        ["", [], 401],
        ["testkey", [], 403],
    ],
)
def test_sns_inbound_sms_auth(
    notify_db_session, notify_api, client, mocker, auth, keys, status_code
):
    mocker.patch(
        "app.notifications.receive_notifications.tasks.send_inbound_sms_to_service.apply_async"
    )

    create_service_with_inbound_number(
        service_name="b",
        inbound_number="07111111111",
        service_permissions=[
            ServicePermissionType.EMAIL,
            ServicePermissionType.SMS,
            ServicePermissionType.INBOUND_SMS,
        ],
    )

    data = {
        "ID": "1234",
        "MSISDN": "07111111111",
        "Message": "Some message to notify",
        "Trigger": "Trigger?",
        "Number": "testing",
        "Channel": "SMS",
        "DateRecieved": "2012-06-27 12:33:00",
    }

    with set_config(notify_api, "MMG_INBOUND_SMS_AUTH", keys):
        response = sns_post(client, data, auth=bool(auth), password=auth)
        assert response.status_code == status_code


def test_create_inbound_sms_object_works_with_alphanumeric_sender(
    sample_service_full_permissions,
):
    data = {
        "Message": "hello",
        "Number": sample_service_full_permissions.get_inbound_number(),
        "MSISDN": "ALPHANUM3R1C",
        "DateRecieved": "2017-01-02+03%3A04%3A05",
        "ID": "bar",
    }

    inbound_sms = create_inbound_sms_object(
        service=sample_service_full_permissions,
        content=data["Message"],
        from_number="ALPHANUM3R1C",
        provider_ref="foo",
        date_received=None,
        provider_name="mmg",
    )

    assert inbound_sms.user_number == "ALPHANUM3R1C"


@mock.patch(
    "app.notifications.receive_notifications.dao_fetch_service_by_inbound_number"
)
def test_fetch_potential_service_cant_find_it(mock_dao):
    mock_dao.return_value = None
    found_service = fetch_potential_service(234, "sns")
    assert found_service is False

    # Permissions will not be set so it will still return false
    mock_dao.return_value = create_service()
    found_service = fetch_potential_service(234, "sns")
    assert found_service is False
