import datetime
from unittest.mock import MagicMock, patch

import pytest
from marshmallow import ValidationError
from sqlalchemy import desc, select

from app import db
from app.dao.provider_details_dao import (
    dao_update_provider_details,
    get_provider_details_by_identifier,
)
from app.models import ProviderDetailsHistory, ServicePermission
from app.schema_validation import validate_schema_date_with_hour
from app.schemas import ServiceSchema, UserSchema
from tests.app.db import create_api_key


def test_job_schema_doesnt_return_notifications(sample_notification_with_job):
    from app.schemas import job_schema

    job = sample_notification_with_job.job
    assert job.notifications.count() == 1

    data = job_schema.dump(job)

    assert "notifications" not in data


def test_notification_schema_ignores_absent_api_key(sample_notification_with_job):
    from app.schemas import notification_with_template_schema

    data = notification_with_template_schema.dump(sample_notification_with_job)
    assert data["key_name"] is None


def test_notification_schema_adds_api_key_name(sample_notification):
    from app.schemas import notification_with_template_schema

    api_key = create_api_key(sample_notification.service, key_name="Test key")
    sample_notification.api_key = api_key

    data = notification_with_template_schema.dump(sample_notification)
    assert data["key_name"] == "Test key"


@pytest.mark.parametrize(
    "schema_name",
    [
        "notification_with_template_schema",
        "notification_schema",
        "notification_with_template_schema",
        "public_notification_response_schema",
    ],
)
def test_notification_schema_has_correct_status(sample_notification, schema_name):
    from app import schemas

    data = getattr(schemas, schema_name).dump(sample_notification)

    assert data["status"] == sample_notification.status


@pytest.mark.parametrize(
    "user_attribute, user_value",
    [
        ("name", "New User"),
        ("email_address", "newuser@mail.com"),
        ("mobile_number", "+14254147755"),
    ],
)
def test_user_update_schema_accepts_valid_attribute_pairs(
    notify_api, user_attribute, user_value
):
    update_dict = {user_attribute: user_value}
    from app.schemas import user_update_schema_load_json

    errors = user_update_schema_load_json.validate(update_dict)
    assert not errors


@pytest.mark.parametrize(
    "user_attribute, user_value",
    [
        ("name", None),
        ("name", ""),
        ("email_address", "bademail@...com"),
        ("mobile_number", "+44077009"),
    ],
)
def test_user_update_schema_rejects_invalid_attribute_pairs(
    notify_api, user_attribute, user_value
):
    from app.schemas import user_update_schema_load_json

    update_dict = {user_attribute: user_value}

    with pytest.raises(ValidationError):
        user_update_schema_load_json.load(update_dict)


@pytest.mark.parametrize(
    "user_attribute",
    [
        "id",
        "updated_at",
        "created_at",
        "user_to_service",
        "_password",
        "verify_codes",
        "logged_in_at",
        "password_changed_at",
        "failed_login_count",
        "state",
        "platform_admin",
    ],
)
def test_user_update_schema_rejects_disallowed_attribute_keys(
    notify_api, user_attribute
):
    update_dict = {user_attribute: "not important"}
    from app.schemas import user_update_schema_load_json

    with pytest.raises(ValidationError) as excinfo:
        user_update_schema_load_json.load(update_dict)

    assert excinfo.value.messages["_schema"][0] == "Unknown field name {}".format(
        user_attribute
    )


def test_provider_details_schema_returns_user_details(
    mocker, sample_user, restore_provider_details
):
    from app.schemas import provider_details_schema

    current_sms_provider = get_provider_details_by_identifier("sns")
    current_sms_provider.created_by = sample_user
    data = provider_details_schema.dump(current_sms_provider)

    assert sorted(data["created_by"].keys()) == sorted(["id", "email_address", "name"])


def test_provider_details_history_schema_returns_user_details(
    mocker,
    sample_user,
    restore_provider_details,
):
    from app.schemas import provider_details_schema

    current_sms_provider = get_provider_details_by_identifier("sns")
    current_sms_provider.created_by_id = sample_user.id
    data = provider_details_schema.dump(current_sms_provider)

    dao_update_provider_details(current_sms_provider)

    stmt = (
        select(ProviderDetailsHistory)
        .where(ProviderDetailsHistory.id == current_sms_provider.id)
        .order_by(desc(ProviderDetailsHistory.version))
    )
    current_sms_provider_in_history = db.session.execute(stmt).scalars().first()

    data = provider_details_schema.dump(current_sms_provider_in_history)

    assert sorted(data["created_by"].keys()) == sorted(["id", "email_address", "name"])


def test_valid_date_within_24_hours(mocker):
    mocker.patch(
        "app.schema_validation.utc_now",
        return_value=datetime.datetime(2024, 10, 27, 15, 0, 0),
    )
    valid_datetime = "2024-10-28T14:00:00Z"
    assert validate_schema_date_with_hour(valid_datetime)


def test_date_in_past(mocker):
    mocker.patch(
        "app.schema_validation.utc_now",
        return_value=datetime.datetime(2024, 10, 27, 15, 0, 0),
    )
    past_datetime = "2024-10-26T14:00:00Z"
    try:
        validate_schema_date_with_hour(past_datetime)
        assert 1 == 0
    except Exception as e:
        assert "datetime can not be in the past" in str(e)


def test_date_more_than_24_hours_in_future(mocker):
    mocker.patch(
        "app.schema_validation.utc_now",
        return_value=datetime.datetime(2024, 10, 27, 15, 0, 0),
    )
    past_datetime = "2024-10-31T14:00:00Z"
    try:
        validate_schema_date_with_hour(past_datetime)
        assert 1 == 0
    except Exception as e:
        assert "datetime can only be 24 hours in the future" in str(e)


def test_user_permissions_returns_correct_dict(sample_user):
    sample_user.id = 1
    mock_permissions = [
        MagicMock(service_id=111, permission="read"),
        MagicMock(service_id=111, permission="write"),
        MagicMock(service_id=222, permission="admin"),
    ]
    with patch(
        "app.schemas.permission_dao.get_permissions_by_user_id",
        return_value=mock_permissions,
    ):
        schema = UserSchema()

        result = schema.user_permissions(sample_user)

    expected = {
        "111": ["read", "write"],
        "222": ["admin"],
    }

    assert result == expected


def test_deserialize_with_permissions():
    input_data = {"id": "service-123", "permissions": ["read", "write"]}

    schema = ServiceSchema()
    result = schema.deserialize_service_permissions(input_data)

    assert isinstance(result["permissions"], list)
    assert all(isinstance(p, ServicePermission) for p in result["permissions"])
    assert result["permissions"][0].service_id == "service-123"
    assert result["permissions"][0].permission == "read"
    assert result["permissions"][1].permission == "write"


def test_deserialize_with_no_permissions_key():
    input_data = {"id": "service-123", "other_data": "value"}
    schema = ServiceSchema()
    result = schema.deserialize_service_permissions(input_data.copy())
    assert result == input_data


def test_deserialize_with_non_dict_input():
    input_data = ["not", "a", "dict"]
    schema = ServiceSchema()
    result = schema.deserialize_service_permissions(input_data)
    assert result == input_data
