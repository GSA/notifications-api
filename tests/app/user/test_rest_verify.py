import json
import uuid
from datetime import datetime, timedelta

import pytest
from flask import current_app, url_for
from freezegun import freeze_time
from sqlalchemy import func, select

import app.celery.tasks
from app import db
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.users_dao import create_user_code
from app.enums import AuthType, CodeType
from app.models import Notification, User, VerifyCode
from app.utils import utc_now
from tests import create_admin_authorization_header


@freeze_time("2016-01-01T12:00:00")
def test_user_verify_sms_code(client, sample_sms_code):
    sample_sms_code.user.logged_in_at = utc_now() - timedelta(days=1)
    assert not db.session.execute(select(VerifyCode)).scalars().first().code_used
    assert sample_sms_code.user.current_session_id is None
    data = json.dumps(
        {"code_type": sample_sms_code.code_type, "code": sample_sms_code.txt_code}
    )
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204
    assert db.session.execute(select(VerifyCode)).scalars().first().code_used
    assert sample_sms_code.user.logged_in_at == utc_now()
    assert sample_sms_code.user.email_access_validated_at != utc_now()
    assert sample_sms_code.user.current_session_id is not None


def test_user_verify_code_missing_code(client, sample_sms_code):
    assert not db.session.execute(select(VerifyCode)).scalars().first().code_used
    data = json.dumps({"code_type": sample_sms_code.code_type})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 400
    assert not db.session.execute(select(VerifyCode)).scalars().first().code_used
    assert db.session.get(User, sample_sms_code.user.id).failed_login_count == 0


def test_user_verify_code_bad_code_and_increments_failed_login_count(
    client, sample_sms_code
):
    assert not db.session.execute(select(VerifyCode)).scalars().first().code_used
    data = json.dumps({"code_type": sample_sms_code.code_type, "code": "blah"})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 404
    assert not db.session.execute(select(VerifyCode)).scalars().first().code_used
    assert db.session.get(User, sample_sms_code.user.id).failed_login_count == 1


@pytest.mark.parametrize(
    "failed_login_count, expected_status",
    (
        (9, 204),
        (10, 404),
    ),
)
def test_user_verify_code_rejects_good_code_if_too_many_failed_logins(
    client,
    sample_sms_code,
    failed_login_count,
    expected_status,
):
    sample_sms_code.user.failed_login_count = failed_login_count
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=json.dumps(
            {
                "code_type": sample_sms_code.code_type,
                "code": sample_sms_code.txt_code,
            }
        ),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert resp.status_code == expected_status


@freeze_time("2020-04-01 12:00")
@pytest.mark.parametrize("code_type", [CodeType.EMAIL, CodeType.SMS])
def test_user_verify_code_expired_code_and_increments_failed_login_count(
    code_type, admin_request, sample_user
):
    magic_code = str(uuid.uuid4())
    verify_code = create_user_code(sample_user, magic_code, code_type)
    verify_code.expiry_datetime = datetime(2020, 4, 1, 11, 59)

    data = {"code_type": code_type, "code": magic_code}

    admin_request.post(
        "user.verify_user_code",
        user_id=sample_user.id,
        _data=data,
        _expected_status=400,
    )

    assert verify_code.code_used is False
    assert sample_user.logged_in_at is None
    assert sample_user.current_session_id is None
    assert sample_user.failed_login_count == 1


@freeze_time("2016-01-01 10:00:00.000000")
def test_user_verify_password(client, sample_user):
    yesterday = utc_now() - timedelta(days=1)
    sample_user.logged_in_at = yesterday
    data = json.dumps({"password": "password"})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_password", user_id=sample_user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204
    assert db.session.get(User, sample_user.id).logged_in_at == yesterday


def test_user_verify_password_invalid_password(client, sample_user):
    data = json.dumps({"password": "bad password"})
    auth_header = create_admin_authorization_header()

    assert sample_user.failed_login_count == 0

    resp = client.post(
        url_for("user.verify_user_password", user_id=sample_user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert "Incorrect password" in json_resp["message"]["password"]
    assert sample_user.failed_login_count == 1


def test_user_verify_password_valid_password_resets_failed_logins(client, sample_user):
    data = json.dumps({"password": "bad password"})
    auth_header = create_admin_authorization_header()

    assert sample_user.failed_login_count == 0

    resp = client.post(
        url_for("user.verify_user_password", user_id=sample_user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert "Incorrect password" in json_resp["message"]["password"]

    assert sample_user.failed_login_count == 1

    data = json.dumps({"password": "password"})
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_password", user_id=sample_user.id),
        data=data,
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert resp.status_code == 204
    assert sample_user.failed_login_count == 0


def test_user_verify_password_missing_password(client, sample_user):
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.verify_user_password", user_id=sample_user.id),
        data=json.dumps({"bingo": "bongo"}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert "Required field missing data" in json_resp["message"]["password"]


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_sms_code(client, sample_user, sms_code_template, mocker):
    """
    Tests POST endpoint /user/<user_id>/sms-code
    """
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    mock_redis_get = mocker.patch("app.user.rest.redis_store.get")
    mock_redis_get.return_value = "foo"

    mocker.patch("app.user.rest.redis_store.set")
    auth_header = create_admin_authorization_header()
    mocked = mocker.patch("app.user.rest.create_secret_code", return_value="11111")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    resp = client.post(
        url_for(
            "user.send_user_2fa_code",
            code_type=CodeType.SMS,
            user_id=sample_user.id,
        ),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204

    assert mocked.call_count == 1
    assert db.session.execute(select(VerifyCode)).scalars().one().check_code("11111")

    notification = db.session.execute(select(Notification)).scalars().one()
    assert notification.personalisation == {"verify_code": "11111"}
    assert notification.to == "1"
    assert str(notification.service_id) == current_app.config["NOTIFY_SERVICE_ID"]
    assert notification.reply_to_text == notify_service.get_default_sms_sender()

    app.celery.provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        ([str(notification.id)]), queue="notify-internal-tasks", countdown=60
    )


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_code_for_sms_with_optional_to_field(
    client, sample_user, sms_code_template, mocker
):
    """
    Tests POST endpoint /user/<user_id>/sms-code with optional to field
    """

    mock_redis_get = mocker.patch("app.user.rest.redis_store.get")
    mock_redis_get.return_value = "foo"

    mocker.patch("app.user.rest.redis_store.set")
    to_number = "+14254147755"
    mocked = mocker.patch("app.user.rest.create_secret_code", return_value="11111")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
    auth_header = create_admin_authorization_header()

    resp = client.post(
        url_for(
            "user.send_user_2fa_code",
            code_type=CodeType.SMS,
            user_id=sample_user.id,
        ),
        data=json.dumps({"to": to_number}),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert resp.status_code == 204
    assert mocked.call_count == 1
    notification = db.session.execute(select(Notification)).scalars().first()
    assert notification.to == "1"
    app.celery.provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        ([str(notification.id)]), queue="notify-internal-tasks", countdown=60
    )


def test_send_sms_code_returns_404_for_bad_input_data(client):
    uuid_ = uuid.uuid4()
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.send_user_2fa_code", code_type=CodeType.SMS, user_id=uuid_),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))["message"] == "No result found"


def test_send_sms_code_returns_204_when_too_many_codes_already_created(
    client, sample_user
):
    for _ in range(5):
        verify_code = VerifyCode(
            code_type=CodeType.SMS,
            _code=12345,
            created_at=utc_now() - timedelta(minutes=10),
            expiry_datetime=utc_now() + timedelta(minutes=40),
            user=sample_user,
        )
        db.session.add(verify_code)
        db.session.commit()
    assert _get_verify_code_count() == 5
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for(
            "user.send_user_2fa_code",
            code_type=CodeType.SMS,
            user_id=sample_user.id,
        ),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204
    assert _get_verify_code_count() == 5


def _get_verify_code_count():
    stmt = select(func.count()).select_from(VerifyCode)
    return db.session.execute(stmt).scalar() or 0


@pytest.mark.parametrize(
    "post_data, expected_url_starts_with",
    (
        (
            {},
            "http://localhost",
        ),
        (
            {"admin_base_url": "https://example.com"},
            "https://example.com",
        ),
    ),
)
def test_send_new_user_email_verification(
    client,
    sample_user,
    mocker,
    email_verification_template,
    post_data,
    expected_url_starts_with,
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.send_new_user_email_verification", user_id=str(sample_user.id)),
        data=json.dumps(post_data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    notify_service = email_verification_template.service
    assert resp.status_code == 204
    notification = db.session.execute(select(Notification)).scalars().first()
    assert _get_verify_code_count() == 0
    mocked.assert_called_once_with(
        ([str(notification.id)]), queue="notify-internal-tasks", countdown=60
    )
    assert (
        notification.reply_to_text
        == notify_service.get_default_reply_to_email_address()
    )
    assert notification.personalisation["name"] == "Test User"
    assert notification.personalisation["url"].startswith(expected_url_starts_with)


def test_send_email_verification_returns_404_for_bad_input_data(
    client, notify_db_session, mocker
):
    """
    Tests POST endpoint /user/<user_id>/sms-code return 404 for bad input data
    """
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    uuid_ = uuid.uuid4()
    auth_header = create_admin_authorization_header()
    resp = client.post(
        url_for("user.send_new_user_email_verification", user_id=uuid_),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))["message"] == "No result found"
    assert mocked.call_count == 0


def test_user_verify_user_code_returns_404_when_code_is_right_but_user_account_is_locked(
    client, sample_sms_code
):
    sample_sms_code.user.failed_login_count = 10
    data = json.dumps(
        {"code_type": sample_sms_code.code_type, "code": sample_sms_code.txt_code}
    )
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert resp.status_code == 404
    assert sample_sms_code.user.failed_login_count == 10
    assert not sample_sms_code.code_used


def test_user_verify_user_code_valid_code_resets_failed_login_count(
    client, sample_sms_code
):
    sample_sms_code.user.failed_login_count = 1
    data = json.dumps(
        {"code_type": sample_sms_code.code_type, "code": sample_sms_code.txt_code}
    )
    resp = client.post(
        url_for("user.verify_user_code", user_id=sample_sms_code.user.id),
        data=data,
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert resp.status_code == 204
    assert sample_sms_code.user.failed_login_count == 0
    assert sample_sms_code.code_used


def test_user_reset_failed_login_count_returns_200(client, sample_user):
    sample_user.failed_login_count = 1
    resp = client.post(
        url_for("user.user_reset_failed_login_count", user_id=sample_user.id),
        data={},
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert resp.status_code == 200
    assert sample_user.failed_login_count == 0


def test_reset_failed_login_count_returns_404_when_user_does_not_exist(client):
    resp = client.post(
        url_for("user.user_reset_failed_login_count", user_id=uuid.uuid4()),
        data={},
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert resp.status_code == 404


# we send AuthType.SMS users and AuthType.WEBAUTHN users email code to validate their email access
@pytest.mark.parametrize("auth_type", AuthType)
@pytest.mark.parametrize(
    "data, expected_auth_url",
    (
        (
            {},
            "http://localhost:6012/email-auth/%2E",
        ),
        (
            {"to": None},
            "http://localhost:6012/email-auth/%2E",
        ),
        (
            {"to": None, "email_auth_link_host": "https://example.com"},
            "https://example.com/email-auth/%2E",
        ),
    ),
)
def test_send_user_email_code(
    admin_request,
    mocker,
    sample_user,
    email_2fa_code_template,
    data,
    expected_auth_url,
    auth_type,
):
    deliver_email = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    sample_user.auth_type = auth_type

    mock_redis_get = mocker.patch("app.user.rest.redis_store.get")
    mock_redis_get.return_value = "foo"

    mocker.patch("app.user.rest.redis_store.set")

    admin_request.post(
        "user.send_user_2fa_code",
        code_type=CodeType.EMAIL,
        user_id=sample_user.id,
        _data=data,
        _expected_status=204,
    )
    noti = db.session.execute(select(Notification)).scalars().one()
    assert (
        noti.reply_to_text
        == email_2fa_code_template.service.get_default_reply_to_email_address()
    )
    assert noti.to == "1"
    assert str(noti.template_id) == current_app.config["EMAIL_2FA_TEMPLATE_ID"]
    deliver_email.assert_called_once_with(
        [str(noti.id)], queue="notify-internal-tasks", countdown=60
    )


def test_send_user_email_code_with_urlencoded_next_param(
    admin_request, mocker, sample_user, email_2fa_code_template
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    mock_redis_get = mocker.patch("app.celery.scheduled_tasks.redis_store.get")
    mock_redis_get.return_value = "foo"

    mocker.patch("app.celery.scheduled_tasks.redis_store.set")

    data = {"to": None, "next": "/services"}
    admin_request.post(
        "user.send_user_2fa_code",
        code_type=CodeType.EMAIL,
        user_id=sample_user.id,
        _data=data,
        _expected_status=204,
    )


def test_send_email_code_returns_404_for_bad_input_data(admin_request):
    resp = admin_request.post(
        "user.send_user_2fa_code",
        code_type=CodeType.EMAIL,
        user_id=uuid.uuid4(),
        _data={},
        _expected_status=404,
    )
    assert resp["message"] == "No result found"


@freeze_time("2016-01-01T12:00:00")
# we send iAuthType.SMS and AuthType.WEBAUTHN users email code to validate their email access
@pytest.mark.parametrize("auth_type", AuthType)
def test_user_verify_email_code(admin_request, sample_user, auth_type):
    sample_user.logged_in_at = utc_now() - timedelta(days=1)
    sample_user.email_access_validated_at = utc_now() - timedelta(days=1)
    sample_user.auth_type = auth_type
    magic_code = str(uuid.uuid4())
    verify_code = create_user_code(sample_user, magic_code, CodeType.EMAIL)

    data = {"code_type": CodeType.EMAIL, "code": magic_code}

    admin_request.post(
        "user.verify_user_code",
        user_id=sample_user.id,
        _data=data,
        _expected_status=204,
    )

    assert verify_code.code_used
    assert sample_user.logged_in_at == utc_now()
    assert sample_user.email_access_validated_at == utc_now()
    assert sample_user.current_session_id is not None


@pytest.mark.parametrize("code_type", [CodeType.EMAIL, CodeType.SMS])
@freeze_time("2016-01-01T12:00:00")
def test_user_verify_email_code_fails_if_code_already_used(
    admin_request, sample_user, code_type
):
    magic_code = str(uuid.uuid4())
    verify_code = create_user_code(sample_user, magic_code, code_type)
    verify_code.code_used = True

    data = {"code_type": code_type, "code": magic_code}

    admin_request.post(
        "user.verify_user_code",
        user_id=sample_user.id,
        _data=data,
        _expected_status=400,
    )

    assert verify_code.code_used
    assert sample_user.logged_in_at is None
    assert sample_user.current_session_id is None


def test_send_user_2fa_code_sends_from_number_for_international_numbers(
    client, sample_user, mocker, sms_code_template
):
    mock_redis_get = mocker.patch("app.user.rest.redis_store.get")
    mock_redis_get.return_value = "foo"

    mocker.patch("app.user.rest.redis_store.set")

    sample_user.mobile_number = "+601117224412"
    auth_header = create_admin_authorization_header()
    mocker.patch("app.user.rest.create_secret_code", return_value="11111")
    mocker.patch("app.user.rest.send_notification_to_queue")

    resp = client.post(
        url_for(
            "user.send_user_2fa_code",
            code_type=CodeType.SMS,
            user_id=sample_user.id,
        ),
        data=json.dumps({}),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 204

    notification = db.session.execute(select(Notification)).scalars().first()
    assert (
        notification.reply_to_text
        == current_app.config["NOTIFY_INTERNATIONAL_SMS_SENDER"]
    )
