import random
import string

import pytest
from flask import current_app, json
from freezegun import freeze_time
from sqlalchemy import func, select

import app
from app import db
from app.dao import notifications_dao
from app.dao.api_key_dao import save_model_api_key
from app.dao.services_dao import dao_update_service
from app.dao.templates_dao import dao_get_all_templates_for_service, dao_update_template
from app.enums import KeyType, NotificationType, TemplateType
from app.errors import InvalidRequest
from app.models import ApiKey, Notification, NotificationHistory, Template
from notifications_python_client.authentication import create_jwt_token
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from tests import create_service_authorization_header
from tests.app.db import (
    create_api_key,
    create_notification,
    create_reply_to_email,
    create_service,
    create_service_guest_list,
    create_template,
)


@pytest.mark.parametrize("template_type", [TemplateType.SMS, TemplateType.EMAIL])
def test_create_notification_should_reject_if_missing_required_fields(
    notify_api, sample_api_key, mocker, template_type
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch(
                f"app.celery.provider_tasks.deliver_{template_type}.apply_async"
            )
            data = {}
            auth_header = create_service_authorization_header(
                service_id=sample_api_key.service_id
            )

            response = client.post(
                path=f"/notifications/{template_type}",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()
            assert json_resp["result"] == "error"
            assert "Missing data for required field." in json_resp["message"]["to"][0]
            assert (
                "Missing data for required field."
                in json_resp["message"]["template"][0]
            )
            assert response.status_code == 400


def test_should_reject_bad_phone_numbers(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

            data = {"to": "invalid", "template": sample_template.id}
            auth_header = create_service_authorization_header(
                service_id=sample_template.service_id
            )

            response = client.post(
                path="/notifications/sms",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()
            assert json_resp["result"] == "error"
            assert len(json_resp["message"].keys()) == 1
            assert (
                "Invalid phone number: Invalid phone number looks like invalid The string supplied did not seem to be a phone number."  # noqa
                in json_resp["message"]["to"]
            )
            assert response.status_code == 400


@pytest.mark.parametrize(
    "template_type, to",
    [
        (TemplateType.SMS, "+14254147755"),
        (TemplateType.EMAIL, "ok@ok.com"),
    ],
)
def test_send_notification_invalid_template_id(
    notify_api, sample_template, mocker, fake_uuid, template_type, to
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch(
                f"app.celery.provider_tasks.deliver_{template_type}.apply_async"
            )

            data = {"to": to, "template": fake_uuid}
            auth_header = create_service_authorization_header(
                service_id=sample_template.service_id
            )

            response = client.post(
                path=f"/notifications/{template_type}",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()
            assert response.status_code == 400
            test_string = "Template not found"
            assert test_string in json_resp["message"]


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_notification_with_placeholders_replaced(
    notify_api, sample_email_template_with_placeholders, mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

            data = {
                "to": "ok@ok.com",
                "template": str(sample_email_template_with_placeholders.id),
                "personalisation": {"name": "Jo"},
            }
            auth_header = create_service_authorization_header(
                service_id=sample_email_template_with_placeholders.service.id
            )

            response = client.post(
                path="/notifications/email",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            response_data = json.loads(response.data)["data"]
            notification_id = response_data["notification"]["id"]
            data.update(
                {"template_version": sample_email_template_with_placeholders.version}
            )

            mocked.assert_called_once_with(
                [notification_id], queue="send-email-tasks", countdown=60
            )
            assert response.status_code == 201
            assert response_data["body"] == "Hello Jo\nThis is an email from GOV.UK"
            assert response_data["subject"] == "Jo"


@pytest.mark.parametrize(
    "personalisation, expected_body, expected_subject",
    [
        (
            ["Jo", "John", "Josephine"],
            (
                "Hello \n\n"
                "* Jo\n"
                "* John\n"
                "* Josephine\n"
                "This is an email from GOV.UK"
            ),
            "Jo, John and Josephine",
        ),
        (
            6,
            ("Hello 6\n" "This is an email from GOV.UK"),
            "6",
        ),
    ],
)
def test_send_notification_with_placeholders_replaced_with_unusual_types(
    client,
    sample_email_template_with_placeholders,
    mocker,
    personalisation,
    expected_body,
    expected_subject,
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    response = client.post(
        path="/notifications/email",
        data=json.dumps(
            {
                "to": "ok@ok.com",
                "template": str(sample_email_template_with_placeholders.id),
                "personalisation": {"name": personalisation},
            }
        ),
        headers=[
            ("Content-Type", "application/json"),
            create_service_authorization_header(
                service_id=sample_email_template_with_placeholders.service.id
            ),
        ],
    )

    assert response.status_code == 201
    response_data = json.loads(response.data)["data"]
    assert response_data["body"] == expected_body
    assert response_data["subject"] == expected_subject


@pytest.mark.parametrize(
    "personalisation, expected_body, expected_subject",
    [
        (
            None,
            ("we consider None equivalent to missing personalisation"),
            "",
        ),
    ],
)
def test_send_notification_with_placeholders_replaced_with_unusual_types_no_personalization(
    client,
    sample_email_template_with_placeholders,
    mocker,
    personalisation,
    expected_body,
    expected_subject,
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    response = client.post(
        path="/notifications/email",
        data=json.dumps(
            {
                "to": "ok@ok.com",
                "template": str(sample_email_template_with_placeholders.id),
                "personalisation": {"name": personalisation},
            }
        ),
        headers=[
            ("Content-Type", "application/json"),
            create_service_authorization_header(
                service_id=sample_email_template_with_placeholders.service.id
            ),
        ],
    )

    assert response.status_code == 400


def test_should_not_send_notification_for_archived_template(
    notify_api, sample_template
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            sample_template.archived = True
            dao_update_template(sample_template)
            json_data = json.dumps(
                {"to": "+14254147755", "template": sample_template.id}
            )
            auth_header = create_service_authorization_header(
                service_id=sample_template.service_id
            )

            resp = client.post(
                path="/notifications/sms",
                data=json_data,
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert "Template has been deleted" in json_resp["message"]


@pytest.mark.parametrize(
    "template_type, to",
    [
        (TemplateType.SMS, "+16618675309"),
        (TemplateType.EMAIL, "not-someone-we-trust@email-address.com"),
    ],
)
def test_should_not_send_notification_if_restricted_and_not_a_service_user(
    notify_api, sample_template, sample_email_template, mocker, template_type, to
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch(
                f"app.celery.provider_tasks.deliver_{template_type}.apply_async"
            )
            template = (
                sample_template
                if template_type == TemplateType.SMS
                else sample_email_template
            )
            template.service.restricted = True
            dao_update_service(template.service)
            data = {"to": to, "template": template.id}

            auth_header = create_service_authorization_header(
                service_id=template.service_id
            )

            response = client.post(
                path=f"/notifications/{template_type}",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()

            assert response.status_code == 400
            assert [
                (
                    "Can’t send to this recipient when service is in trial mode "
                    "– see https://www.notifications.service.gov.uk/trial-mode"
                )
            ] == json_resp["message"]["to"]


@pytest.mark.parametrize("template_type", [TemplateType.SMS, TemplateType.EMAIL])
def test_should_send_notification_if_restricted_and_a_service_user(
    notify_api, sample_template, sample_email_template, template_type, mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch(
                f"app.celery.provider_tasks.deliver_{template_type}.apply_async"
            )

            template = (
                sample_template
                if template_type == TemplateType.SMS
                else sample_email_template
            )
            to = (
                template.service.created_by.mobile_number
                if template_type == TemplateType.SMS
                else template.service.created_by.email_address
            )
            template.service.restricted = True
            dao_update_service(template.service)
            data = {"to": to, "template": template.id}

            auth_header = create_service_authorization_header(
                service_id=template.service_id
            )

            response = client.post(
                path=f"/notifications/{template_type}",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert mocked.called == 1
            assert response.status_code == 201


@pytest.mark.parametrize("template_type", [TemplateType.SMS, TemplateType.EMAIL])
def test_should_not_allow_template_from_another_service(
    notify_api, service_factory, sample_user, mocker, template_type
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch(
                f"app.celery.provider_tasks.deliver_{template_type}.apply_async"
            )
            service_1 = service_factory.get(
                "service 1", user=sample_user, email_from="service.1"
            )
            service_2 = service_factory.get(
                "service 2", user=sample_user, email_from="service.2"
            )

            service_2_templates = dao_get_all_templates_for_service(
                service_id=service_2.id
            )
            to = (
                sample_user.mobile_number
                if template_type == TemplateType.SMS
                else sample_user.email_address
            )
            data = {"to": to, "template": service_2_templates[0].id}

            auth_header = create_service_authorization_header(service_id=service_1.id)

            response = client.post(
                path=f"/notifications/{template_type}",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            json_resp = json.loads(response.get_data(as_text=True))
            mocked.assert_not_called()
            assert response.status_code == 400
            test_string = "Template not found"
            assert test_string in json_resp["message"]


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_allow_valid_sms_notification(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

            data = {"to": "202 867 5309", "template": str(sample_template.id)}

            auth_header = create_service_authorization_header(
                service_id=sample_template.service_id
            )

            response = client.post(
                path="/notifications/sms",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            response_data = json.loads(response.data)["data"]
            notification_id = response_data["notification"]["id"]

            mocked.assert_called_once_with(
                [notification_id], queue="send-sms-tasks", countdown=60
            )
            assert response.status_code == 201
            assert notification_id
            assert "subject" not in response_data
            assert response_data["body"] == sample_template.content
            assert response_data["template_version"] == sample_template.version


def test_should_reject_email_notification_with_bad_email(
    notify_api, sample_email_template, mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
            to_address = "bad-email"
            data = {"to": to_address, "template": str(sample_email_template.service_id)}
            auth_header = create_service_authorization_header(
                service_id=sample_email_template.service_id
            )

            response = client.post(
                path="/notifications/email",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            data = json.loads(response.get_data(as_text=True))
            mocked.apply_async.assert_not_called()
            assert response.status_code == 400
            assert data["result"] == "error"
            assert data["message"]["to"][0] == "Not a valid email address"


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_allow_valid_email_notification(
    notify_api, sample_email_template, mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

            data = {"to": "ok@ok.com", "template": str(sample_email_template.id)}

            auth_header = create_service_authorization_header(
                service_id=sample_email_template.service_id
            )

            response = client.post(
                path="/notifications/email",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert response.status_code == 201
            response_data = json.loads(response.get_data(as_text=True))["data"]
            notification_id = response_data["notification"]["id"]
            app.celery.provider_tasks.deliver_email.apply_async.assert_called_once_with(
                [notification_id], queue="send-email-tasks", countdown=60
            )

            assert response.status_code == 201
            assert notification_id
            assert response_data["subject"] == "Email Subject"
            assert response_data["body"] == sample_email_template.content
            assert response_data["template_version"] == sample_email_template.version


@pytest.mark.parametrize("restricted", [True, False])
@freeze_time("2016-01-01 12:00:00.061258")
def test_should_allow_api_call_if_under_day_limit_regardless_of_type(
    notify_api, sample_user, mocker, restricted
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

            service = create_service(restricted=restricted, message_limit=2)
            email_template = create_template(service, template_type=TemplateType.EMAIL)
            sms_template = create_template(service, template_type=TemplateType.SMS)
            create_notification(template=email_template)

            data = {"to": sample_user.mobile_number, "template": str(sms_template.id)}

            auth_header = create_service_authorization_header(service_id=service.id)

            response = client.post(
                path="/notifications/sms",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert response.status_code == 201


def test_should_not_return_html_in_body(notify_api, sample_service, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
            email_template = create_template(
                sample_service, template_type=TemplateType.EMAIL, content="hello\nthere"
            )

            data = {"to": "ok@ok.com", "template": str(email_template.id)}

            auth_header = create_service_authorization_header(
                service_id=email_template.service_id
            )
            response = client.post(
                path="/notifications/email",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert response.status_code == 201
            assert (
                json.loads(response.get_data(as_text=True))["data"]["body"]
                == "hello\nthere"
            )


def test_should_not_send_email_if_team_api_key_and_not_a_service_user(
    client, sample_email_template, mocker
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    data = {
        "to": "not-someone-we-trust@email-address.com",
        "template": str(sample_email_template.id),
    }

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id, key_type=KeyType.TEAM
    )

    response = client.post(
        path="/notifications/email",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_resp = json.loads(response.get_data(as_text=True))

    app.celery.provider_tasks.deliver_email.apply_async.assert_not_called()

    assert response.status_code == 400
    assert ["Can’t send to this recipient using a team-only API key"] == json_resp[
        "message"
    ]["to"]


def test_should_not_send_sms_if_team_api_key_and_not_a_service_user(
    client, sample_template, mocker
):
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    data = {
        "to": "2028675300",
        "template": str(sample_template.id),
    }

    auth_header = create_service_authorization_header(
        service_id=sample_template.service_id, key_type=KeyType.TEAM
    )

    response = client.post(
        path="/notifications/sms",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_resp = json.loads(response.get_data(as_text=True))
    app.celery.provider_tasks.deliver_sms.apply_async.assert_not_called()

    assert response.status_code == 400
    assert ["Can’t send to this recipient using a team-only API key"] == json_resp[
        "message"
    ]["to"]


def test_should_send_email_if_team_api_key_and_a_service_user(
    client, sample_email_template, fake_uuid, mocker
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    mocker.patch(
        "app.notifications.process_notifications.uuid.uuid4", return_value=fake_uuid
    )

    data = {
        "to": sample_email_template.service.created_by.email_address,
        "template": sample_email_template.id,
    }
    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id, key_type=KeyType.TEAM
    )

    response = client.post(
        path="/notifications/email",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    app.celery.provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [fake_uuid], queue="send-email-tasks", countdown=60
    )
    assert response.status_code == 201


@pytest.mark.parametrize("restricted", [True, False])
@pytest.mark.parametrize("limit", [0, 1])
def test_should_send_sms_to_anyone_with_test_key(
    client, sample_template, mocker, restricted, limit, fake_uuid
):
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
    mocker.patch(
        "app.notifications.process_notifications.uuid.uuid4", return_value=fake_uuid
    )

    data = {"to": "2028675300", "template": sample_template.id}
    sample_template.service.restricted = restricted
    sample_template.service.message_limit = limit
    api_key = ApiKey(
        service=sample_template.service,
        name="test_key",
        created_by=sample_template.created_by,
        key_type=KeyType.TEST,
    )
    save_model_api_key(api_key)
    auth_header = create_jwt_token(
        secret=api_key.secret, client_id=str(api_key.service_id)
    )

    response = client.post(
        path="/notifications/sms",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            ("Authorization", f"Bearer {auth_header}"),
        ],
    )
    app.celery.provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [fake_uuid], queue="send-sms-tasks", countdown=60
    )
    assert response.status_code == 201


@pytest.mark.parametrize("restricted", [True, False])
@pytest.mark.parametrize("limit", [0, 1])
def test_should_send_email_to_anyone_with_test_key(
    client, sample_email_template, mocker, restricted, limit, fake_uuid
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    mocker.patch(
        "app.notifications.process_notifications.uuid.uuid4", return_value=fake_uuid
    )

    data = {"to": "anyone123@example.com", "template": sample_email_template.id}
    sample_email_template.service.restricted = restricted
    sample_email_template.service.message_limit = limit
    api_key = ApiKey(
        service=sample_email_template.service,
        name="test_key",
        created_by=sample_email_template.created_by,
        key_type=KeyType.TEST,
    )
    save_model_api_key(api_key)
    auth_header = create_jwt_token(
        secret=api_key.secret, client_id=str(api_key.service_id)
    )

    response = client.post(
        path="/notifications/email",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            ("Authorization", f"Bearer {auth_header}"),
        ],
    )

    app.celery.provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [fake_uuid], queue="send-email-tasks", countdown=60
    )
    assert response.status_code == 201


def test_should_send_sms_if_team_api_key_and_a_service_user(
    client, sample_template, fake_uuid, mocker
):
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
    mocker.patch(
        "app.notifications.process_notifications.uuid.uuid4", return_value=fake_uuid
    )

    data = {
        "to": sample_template.service.created_by.mobile_number,
        "template": sample_template.id,
    }
    api_key = ApiKey(
        service=sample_template.service,
        name="team_key",
        created_by=sample_template.created_by,
        key_type=KeyType.TEAM,
    )
    save_model_api_key(api_key)
    auth_header = create_jwt_token(
        secret=api_key.secret, client_id=str(api_key.service_id)
    )

    response = client.post(
        path="/notifications/sms",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            ("Authorization", f"Bearer {auth_header}"),
        ],
    )

    app.celery.provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [fake_uuid], queue="send-sms-tasks", countdown=60
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    "template_type,queue_name",
    [
        (TemplateType.SMS, "send-sms-tasks"),
        (TemplateType.EMAIL, "send-email-tasks"),
    ],
)
def test_should_persist_notification(
    client,
    sample_template,
    sample_email_template,
    fake_uuid,
    mocker,
    template_type,
    queue_name,
):
    mocked = mocker.patch(
        f"app.celery.provider_tasks.deliver_{template_type}.apply_async"
    )
    mocker.patch(
        "app.notifications.process_notifications.uuid.uuid4", return_value=fake_uuid
    )

    template = (
        sample_template if template_type == TemplateType.SMS else sample_email_template
    )
    to = (
        sample_template.service.created_by.mobile_number
        if template_type == TemplateType.SMS
        else sample_email_template.service.created_by.email_address
    )
    data = {"to": to, "template": template.id}
    api_key = ApiKey(
        service=template.service,
        name="team_key",
        created_by=template.created_by,
        key_type=KeyType.TEAM,
    )
    save_model_api_key(api_key)
    auth_header = create_jwt_token(
        secret=api_key.secret, client_id=str(api_key.service_id)
    )

    response = client.post(
        path=f"/notifications/{template_type}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            ("Authorization", f"Bearer {auth_header}"),
        ],
    )

    mocked.assert_called_once_with([fake_uuid], queue=queue_name, countdown=60)
    assert response.status_code == 201

    notification = notifications_dao.get_notification_by_id(fake_uuid)
    assert notification.to == "1"
    assert notification.template_id == template.id
    assert notification.notification_type == template_type


@pytest.mark.parametrize(
    "template_type,queue_name",
    [(TemplateType.SMS, "send-sms-tasks"), (TemplateType.EMAIL, "send-email-tasks")],
)
def test_should_delete_notification_and_return_error_if_redis_fails(
    client,
    sample_email_template,
    sample_template,
    fake_uuid,
    mocker,
    template_type,
    queue_name,
):
    mocked = mocker.patch(
        f"app.celery.provider_tasks.deliver_{template_type}.apply_async",
        side_effect=Exception("failed to talk to redis"),
    )
    mocker.patch(
        "app.notifications.process_notifications.uuid.uuid4", return_value=fake_uuid
    )

    template = (
        sample_template if template_type == TemplateType.SMS else sample_email_template
    )
    to = (
        sample_template.service.created_by.mobile_number
        if template_type == TemplateType.SMS
        else sample_email_template.service.created_by.email_address
    )
    data = {"to": to, "template": template.id}
    api_key = ApiKey(
        service=template.service,
        name="team_key",
        created_by=template.created_by,
        key_type=KeyType.TEAM,
    )
    save_model_api_key(api_key)
    auth_header = create_jwt_token(
        secret=api_key.secret, client_id=str(api_key.service_id)
    )

    with pytest.raises(expected_exception=Exception) as e:
        client.post(
            path=f"/notifications/{template_type}",
            data=json.dumps(data),
            headers=[
                ("Content-Type", "application/json"),
                ("Authorization", f"Bearer {auth_header}"),
            ],
        )
    assert str(e.value) == "failed to talk to redis"

    mocked.assert_called_once_with([fake_uuid], queue=queue_name, countdown=60)
    assert not notifications_dao.get_notification_by_id(fake_uuid)
    assert not db.session.get(NotificationHistory, fake_uuid)


@pytest.mark.parametrize(
    "to_email",
    [
        "simulate-delivered@notifications.service.gov.uk",
        "simulate-delivered-2@notifications.service.gov.uk",
        "simulate-delivered-3@notifications.service.gov.uk",
    ],
)
def test_should_not_persist_notification_or_send_email_if_simulated_email(
    client, to_email, sample_email_template, mocker
):
    apply_async = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    data = {"to": to_email, "template": sample_email_template.id}

    auth_header = create_service_authorization_header(
        service_id=sample_email_template.service_id
    )

    response = client.post(
        path="/notifications/email",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 201
    apply_async.assert_not_called()
    stmt = select(func.count()).select_from(Notification)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 0


@pytest.mark.parametrize("to_sms", ["+14254147755", "+14254147167"])
def test_should_not_persist_notification_or_send_sms_if_simulated_number(
    client, to_sms, sample_template, mocker
):
    apply_async = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    data = {"to": to_sms, "template": sample_template.id}

    auth_header = create_service_authorization_header(
        service_id=sample_template.service_id
    )

    response = client.post(
        path="/notifications/sms",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 201
    apply_async.assert_not_called()

    stmt = select(func.count()).select_from(Notification)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 0


@pytest.mark.parametrize("key_type", [KeyType.NORMAL, KeyType.TEAM])
@pytest.mark.parametrize(
    "notification_type, to",
    [
        (TemplateType.SMS, "2028675300"),
        (TemplateType.EMAIL, "non_guest_list_recipient@mail.com"),
    ],
)
def test_should_not_send_notification_to_non_guest_list_recipient_in_trial_mode(
    client, sample_service_guest_list, notification_type, to, key_type, mocker
):
    service = sample_service_guest_list.service
    service.restricted = True
    service.message_limit = 2

    apply_async = mocker.patch(
        f"app.celery.provider_tasks.deliver_{notification_type}.apply_async"
    )
    template = create_template(service, template_type=notification_type)
    assert sample_service_guest_list.service_id == service.id
    assert to not in [member.recipient for member in service.guest_list]

    create_notification(template=template)

    data = {"to": to, "template": str(template.id)}

    api_key = create_api_key(service, key_type=key_type)
    auth_header = create_jwt_token(
        secret=api_key.secret, client_id=str(api_key.service_id)
    )

    response = client.post(
        path=f"/notifications/{notification_type}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            ("Authorization", f"Bearer {auth_header}"),
        ],
    )

    expected_response_message = (
        (
            "Can’t send to this recipient when service is in trial mode "
            "– see https://www.notifications.service.gov.uk/trial-mode"
        )
        if key_type == KeyType.NORMAL
        else ("Can’t send to this recipient using a team-only API key")
    )

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp["result"] == "error"
    assert expected_response_message in json_resp["message"]["to"]
    apply_async.assert_not_called()


@pytest.mark.parametrize("service_restricted", [True, False])
@pytest.mark.parametrize("key_type", [KeyType.NORMAL, KeyType.TEAM])
@pytest.mark.parametrize(
    "notification_type, to, normalized_to",
    [
        (NotificationType.SMS, "2028675300", "+12028675300"),
        (NotificationType.EMAIL, "guest_list_recipient@mail.com", None),
    ],
)
def test_should_send_notification_to_guest_list_recipient(
    client,
    sample_service,
    notification_type,
    to,
    normalized_to,
    key_type,
    service_restricted,
    mocker,
):
    sample_service.message_limit = 2
    sample_service.restricted = service_restricted

    apply_async = mocker.patch(
        f"app.celery.provider_tasks.deliver_{notification_type}.apply_async"
    )
    template = create_template(sample_service, template_type=notification_type)
    if notification_type == NotificationType.SMS:
        service_guest_list = create_service_guest_list(sample_service, mobile_number=to)
    elif notification_type == NotificationType.EMAIL:
        service_guest_list = create_service_guest_list(sample_service, email_address=to)

    assert service_guest_list.service_id == sample_service.id
    assert (normalized_to or to) in [
        member.recipient for member in sample_service.guest_list
    ]

    create_notification(template=template)

    data = {"to": to, "template": str(template.id)}

    sample_key = create_api_key(sample_service, key_type=key_type)
    auth_header = create_jwt_token(
        secret=sample_key.secret, client_id=str(sample_key.service_id)
    )

    response = client.post(
        path=f"/notifications/{notification_type}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            ("Authorization", f"Bearer {auth_header}"),
        ],
    )

    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 201
    assert json_resp["data"]["notification"]["id"]
    assert json_resp["data"]["body"] == template.content
    assert json_resp["data"]["template_version"] == template.version
    assert apply_async.called


@pytest.mark.parametrize(
    "notification_type, template_type, to",
    [
        (NotificationType.EMAIL, TemplateType.SMS, "notify@digital.fake.gov"),
        (NotificationType.SMS, TemplateType.EMAIL, "+12028675309"),
    ],
)
def test_should_error_if_notification_type_does_not_match_template_type(
    client, sample_service, template_type, notification_type, to
):
    template = create_template(sample_service, template_type=template_type)
    data = {"to": to, "template": template.id}
    auth_header = create_service_authorization_header(service_id=template.service_id)
    response = client.post(
        f"/notifications/{notification_type}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert (
        f"{template_type} template is not suitable for {notification_type} notification"
        in json_resp["message"]
    )


def test_create_template_raises_invalid_request_exception_with_missing_personalisation(
    sample_template_with_placeholders,
):
    template = db.session.get(Template, sample_template_with_placeholders.id)
    from app.notifications.rest import create_template_object_for_notification

    with pytest.raises(InvalidRequest) as e:
        create_template_object_for_notification(template, {})
    assert {"template": ["Missing personalisation:  Name"]} == e.value.message


def test_create_template_doesnt_raise_with_too_much_personalisation(
    sample_template_with_placeholders,
):
    from app.notifications.rest import create_template_object_for_notification

    template = db.session.get(Template, sample_template_with_placeholders.id)
    create_template_object_for_notification(template, {"name": "Jo", "extra": "stuff"})


@pytest.mark.parametrize(
    "template_type, should_error",
    [
        (TemplateType.SMS, True),
        (TemplateType.EMAIL, False),
    ],
)
def test_create_template_raises_invalid_request_when_content_too_large(
    sample_service, template_type, should_error
):
    sample = create_template(
        sample_service, template_type=template_type, content="((long_text))"
    )
    template = db.session.get(Template, sample.id)
    from app.notifications.rest import create_template_object_for_notification

    try:
        create_template_object_for_notification(
            template,
            {
                "long_text": "".join(
                    random.choice(string.ascii_uppercase + string.digits)
                    for _ in range(SMS_CHAR_COUNT_LIMIT + 1)
                )
            },
        )
        if should_error:
            pytest.fail("expected an InvalidRequest")
    except InvalidRequest as e:
        if not should_error:
            pytest.fail("do not expect an InvalidRequest")
        assert e.message == {
            "content": [
                f"Content has a character count greater than the limit of {SMS_CHAR_COUNT_LIMIT}"
            ]
        }


def test_should_allow_store_original_number_on_sms_notification(
    client, sample_template, mocker
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    data = {"to": "(202) 867-5309", "template": str(sample_template.id)}

    auth_header = create_service_authorization_header(
        service_id=sample_template.service_id
    )

    response = client.post(
        path="/notifications/sms",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    response_data = json.loads(response.data)["data"]
    notification_id = response_data["notification"]["id"]

    mocked.assert_called_once_with(
        [notification_id], queue="send-sms-tasks", countdown=60
    )
    assert response.status_code == 201
    assert notification_id
    notifications = db.session.execute(select(Notification)).scalars().all()
    assert len(notifications) == 1
    assert "1" == notifications[0].to


def test_should_not_allow_sending_to_international_number_without_international_permission(
    client, sample_template, mocker
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    data = {"to": "+(44) 7700-900 855", "template": str(sample_template.id)}

    auth_header = create_service_authorization_header(
        service_id=sample_template.service_id
    )

    response = client.post(
        path="/notifications/sms",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert not mocked.called
    assert response.status_code == 400
    error_json = json.loads(response.get_data(as_text=True))
    assert error_json["result"] == "error"
    assert error_json["message"] == "Cannot send to international mobile numbers"


def test_should_allow_sending_to_international_number_with_international_permission(
    client, sample_service_full_permissions, mocker
):
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
    template = create_template(sample_service_full_permissions)

    data = {"to": "+(44) 7700-900 855", "template": str(template.id)}

    auth_header = create_service_authorization_header(
        service_id=sample_service_full_permissions.id
    )

    response = client.post(
        path="/notifications/sms",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 201


def test_should_not_allow_sms_notifications_if_service_permission_not_set(
    client,
    mocker,
    sample_template_without_sms_permission,
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    data = {
        "to": "+12028675309",
        "template": str(sample_template_without_sms_permission.id),
    }

    auth_header = create_service_authorization_header(
        service_id=sample_template_without_sms_permission.service_id
    )

    response = client.post(
        path="/notifications/sms",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert not mocked.called
    assert response.status_code == 400
    error_json = json.loads(response.get_data(as_text=True))

    assert error_json["result"] == "error"
    assert error_json["message"]["service"][0] == "Cannot send text messages"


def test_should_not_allow_email_notifications_if_service_permission_not_set(
    client,
    mocker,
    sample_template_without_email_permission,
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    data = {
        "to": "notify@digital.fake.gov",
        "template": str(sample_template_without_email_permission.id),
    }

    auth_header = create_service_authorization_header(
        service_id=sample_template_without_email_permission.service_id
    )

    response = client.post(
        path="/notifications/email",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert not mocked.called
    assert response.status_code == 400
    error_json = json.loads(response.get_data(as_text=True))

    assert error_json["result"] == "error"
    assert error_json["message"]["service"][0] == "Cannot send emails"


@pytest.mark.parametrize(
    "notification_type, err_msg",
    [("apple", "apple notification type is not supported")],
)
def test_should_throw_exception_if_notification_type_is_invalid(
    client, sample_service, notification_type, err_msg
):
    auth_header = create_service_authorization_header(service_id=sample_service.id)
    response = client.post(
        path=f"/notifications/{notification_type}",
        data={},
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True))["message"] == err_msg


@pytest.mark.parametrize(
    "notification_type, recipient",
    [
        (NotificationType.SMS, "2028675309"),
        (
            NotificationType.EMAIL,
            "test@gov.uk",
        ),
    ],
)
def test_post_notification_should_set_reply_to_text(
    client, sample_service, mocker, notification_type, recipient
):
    mocker.patch(f"app.celery.provider_tasks.deliver_{notification_type}.apply_async")
    template = create_template(sample_service, template_type=notification_type)
    expected_reply_to = current_app.config["FROM_NUMBER"]
    if notification_type == NotificationType.EMAIL:
        expected_reply_to = "reply_to@gov.uk"
        create_reply_to_email(
            service=sample_service, email_address=expected_reply_to, is_default=True
        )

    data = {"to": recipient, "template": str(template.id)}
    response = client.post(
        f"/notifications/{notification_type}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_service_authorization_header(service_id=sample_service.id),
        ],
    )
    assert response.status_code == 201
    notifications = db.session.execute(select(Notification)).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == expected_reply_to
