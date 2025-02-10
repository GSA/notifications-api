import datetime
import uuid
from collections import namedtuple

import pytest
from boto3.exceptions import Boto3Error
from freezegun import freeze_time
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.enums import KeyType, NotificationType, ServicePermissionType, TemplateType
from app.errors import BadRequestError
from app.models import Notification, NotificationHistory
from app.notifications.process_notifications import (
    create_content_for_notification,
    persist_notification,
    send_notification_to_queue,
    simulated_recipient,
)
from app.serialised_models import SerialisedTemplate
from notifications_utils.recipients import (
    validate_and_format_email_address,
    validate_and_format_phone_number,
)
from tests.app.db import create_service, create_template


def test_create_content_for_notification_passes(sample_email_template):
    template = SerialisedTemplate.from_id_and_service_id(
        sample_email_template.id, sample_email_template.service_id
    )
    content = create_content_for_notification(template, None)
    assert str(content) == template.content + "\n"


def test_create_content_for_notification_with_placeholders_passes(
    sample_template_with_placeholders,
):
    template = SerialisedTemplate.from_id_and_service_id(
        sample_template_with_placeholders.id,
        sample_template_with_placeholders.service_id,
    )
    content = create_content_for_notification(template, {"name": "Bobby"})
    assert content.content == template.content
    assert "Bobby" in str(content)


def test_create_content_for_notification_fails_with_missing_personalisation(
    sample_template_with_placeholders,
):
    template = SerialisedTemplate.from_id_and_service_id(
        sample_template_with_placeholders.id,
        sample_template_with_placeholders.service_id,
    )
    with pytest.raises(BadRequestError):
        create_content_for_notification(template, None)


def test_create_content_for_notification_allows_additional_personalisation(
    sample_template_with_placeholders,
):
    template = SerialisedTemplate.from_id_and_service_id(
        sample_template_with_placeholders.id,
        sample_template_with_placeholders.service_id,
    )
    create_content_for_notification(
        template, {"name": "Bobby", "Additional placeholder": "Data"}
    )


def _get_notification_query_count():
    stmt = select(func.count()).select_from(Notification)
    return db.session.execute(stmt).scalar() or 0


def _get_notification_history_query_count():
    stmt = select(func.count()).select_from(NotificationHistory)
    return db.session.execute(stmt).scalar() or 0


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_creates_and_save_to_db(
    sample_template, sample_api_key, sample_job
):
    assert _get_notification_query_count() == 0
    assert _get_notification_history_query_count() == 0
    notification = persist_notification(
        template_id=sample_template.id,
        template_version=sample_template.version,
        recipient="+14254147755",
        service=sample_template.service,
        personalisation={},
        notification_type=NotificationType.SMS,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        job_id=sample_job.id,
        job_row_number=100,
        reference="ref",
        reply_to_text=sample_template.service.get_default_sms_sender(),
    )

    assert db.session.get(Notification, notification.id) is not None

    notification_from_db = db.session.execute(select(Notification)).scalars().one()

    assert notification_from_db.id == notification.id
    assert notification_from_db.template_id == notification.template_id
    assert notification_from_db.template_version == notification.template_version
    assert notification_from_db.api_key_id == notification.api_key_id
    assert notification_from_db.key_type == notification.key_type
    assert notification_from_db.key_type == notification.key_type
    assert notification_from_db.billable_units == notification.billable_units
    assert notification_from_db.notification_type == notification.notification_type
    assert notification_from_db.created_at == notification.created_at
    assert not notification_from_db.sent_at
    assert notification_from_db.updated_at == notification.updated_at
    assert notification_from_db.status == notification.status
    assert notification_from_db.reference == notification.reference
    assert notification_from_db.client_reference == notification.client_reference
    assert notification_from_db.created_by_id == notification.created_by_id
    assert (
        notification_from_db.reply_to_text
        == sample_template.service.get_default_sms_sender()
    )


def test_persist_notification_throws_exception_when_missing_template(sample_api_key):
    assert _get_notification_query_count() == 0
    assert _get_notification_history_query_count() == 0
    with pytest.raises(SQLAlchemyError):
        persist_notification(
            template_id=None,
            template_version=None,
            recipient="+14254147755",
            service=sample_api_key.service,
            personalisation=None,
            notification_type=NotificationType.SMS,
            api_key_id=sample_api_key.id,
            key_type=sample_api_key.key_type,
        )
    assert _get_notification_query_count() == 0
    assert _get_notification_history_query_count() == 0


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_with_optionals(sample_job, sample_api_key):
    assert _get_notification_query_count() == 0
    assert _get_notification_history_query_count() == 0
    n_id = uuid.uuid4()
    created_at = datetime.datetime(2016, 11, 11, 16, 8, 18)
    persist_notification(
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        recipient="+12028675309",
        service=sample_job.service,
        personalisation=None,
        notification_type=NotificationType.SMS,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        created_at=created_at,
        job_id=sample_job.id,
        job_row_number=10,
        client_reference="ref from client",
        notification_id=n_id,
        created_by_id=sample_job.created_by_id,
    )
    assert _get_notification_query_count() == 1
    assert _get_notification_history_query_count() == 0
    stmt = select(Notification)
    persisted_notification = db.session.execute(stmt).scalars().all()[0]
    assert persisted_notification.id == n_id
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.job_row_number == 10
    assert persisted_notification.created_at == created_at

    assert persisted_notification.client_reference == "ref from client"
    assert persisted_notification.reference is None
    assert persisted_notification.international is False
    assert persisted_notification.phone_prefix == "1"
    assert persisted_notification.rate_multiplier == 1
    assert persisted_notification.created_by_id == sample_job.created_by_id
    assert not persisted_notification.reply_to_text


def test_persist_notification_cache_is_not_incremented_on_failure_to_create_notification(
    notify_api, sample_api_key, mocker
):
    mocked_redis = mocker.patch("app.redis_store.incr")
    with pytest.raises(SQLAlchemyError):
        persist_notification(
            template_id=None,
            template_version=None,
            recipient="+14254147755",
            service=sample_api_key.service,
            personalisation=None,
            notification_type=NotificationType.SMS,
            api_key_id=sample_api_key.id,
            key_type=sample_api_key.key_type,
        )
    mocked_redis.assert_not_called()


@pytest.mark.parametrize(
    ("requested_queue, notification_type, key_type, expected_queue, expected_task"),
    [
        (
            None,
            NotificationType.SMS,
            KeyType.NORMAL,
            "send-sms-tasks",
            "provider_tasks.deliver_sms",
        ),
        (
            None,
            NotificationType.EMAIL,
            KeyType.NORMAL,
            "send-email-tasks",
            "provider_tasks.deliver_email",
        ),
        (
            None,
            NotificationType.SMS,
            KeyType.TEAM,
            "send-sms-tasks",
            "provider_tasks.deliver_sms",
        ),
        (
            "notify-internal-tasks",
            NotificationType.SMS,
            KeyType.NORMAL,
            "notify-internal-tasks",
            "provider_tasks.deliver_sms",
        ),
        (
            "notify-internal-tasks",
            NotificationType.EMAIL,
            KeyType.NORMAL,
            "notify-internal-tasks",
            "provider_tasks.deliver_email",
        ),
    ],
)
def test_send_notification_to_queue(
    notify_db_session,
    requested_queue,
    notification_type,
    key_type,
    expected_queue,
    expected_task,
    mocker,
):
    mocked = mocker.patch("app.celery.{}.apply_async".format(expected_task))
    Notification = namedtuple(
        "Notification", ["id", "key_type", "notification_type", "created_at"]
    )
    notification = Notification(
        id=uuid.uuid4(),
        key_type=key_type,
        notification_type=notification_type,
        created_at=datetime.datetime(2016, 11, 11, 16, 8, 18),
    )

    send_notification_to_queue(notification=notification, queue=requested_queue)

    mocked.assert_called_once_with(
        [str(notification.id)], queue=expected_queue, countdown=60
    )


def test_send_notification_to_queue_throws_exception_deletes_notification(
    sample_notification, mocker
):
    mocked = mocker.patch(
        "app.celery.provider_tasks.deliver_sms.apply_async",
        side_effect=Boto3Error("EXPECTED"),
    )
    with pytest.raises(Boto3Error):
        send_notification_to_queue(sample_notification, False)
    mocked.assert_called_once_with(
        [(str(sample_notification.id))], queue="send-sms-tasks", countdown=60
    )

    assert _get_notification_query_count() == 0
    assert _get_notification_history_query_count() == 0


@pytest.mark.parametrize(
    "to_address, notification_type, expected",
    [
        ("+14254147755", NotificationType.SMS, True),
        ("+14254147167", NotificationType.SMS, True),
        (
            "simulate-delivered@notifications.service.gov.uk",
            NotificationType.EMAIL,
            True,
        ),
        (
            "simulate-delivered-2@notifications.service.gov.uk",
            NotificationType.EMAIL,
            True,
        ),
        (
            "simulate-delivered-3@notifications.service.gov.uk",
            NotificationType.EMAIL,
            True,
        ),
        ("2028675309", NotificationType.SMS, False),
        ("valid_email@test.com", NotificationType.EMAIL, False),
    ],
)
def test_simulated_recipient(notify_api, to_address, notification_type, expected):
    """
    The values where the expected = 'research-mode' are listed in the config['SIMULATED_EMAIL_ADDRESSES']
    and config['SIMULATED_SMS_NUMBERS']. These values should result in using the research mode queue.
    SIMULATED_EMAIL_ADDRESSES = (
        'simulate-delivered@notifications.service.gov.uk',
        'simulate-delivered-2@notifications.service.gov.uk',
        'simulate-delivered-2@notifications.service.gov.uk'
    )
    SIMULATED_SMS_NUMBERS = ("+14254147755", "+14254147167")
    """
    formatted_address = None

    if notification_type == NotificationType.EMAIL:
        formatted_address = validate_and_format_email_address(to_address)
    else:
        formatted_address = validate_and_format_phone_number(to_address)

    is_simulated_address = simulated_recipient(formatted_address, notification_type)

    assert is_simulated_address == expected


@pytest.mark.parametrize(
    "recipient, expected_international, expected_prefix, expected_units",
    [
        # ("+447900900123", True, "44", 1),  # UK
        # ("+73122345678", True, "7", 1),  # Russia
        # ("+360623400400", True, "36", 1),  # Hungary
        ("2028675309", False, "1", 1),
    ],  # USA
)
def test_persist_notification_with_international_info_stores_correct_info(
    sample_job,
    sample_api_key,
    mocker,
    recipient,
    expected_international,
    expected_prefix,
    expected_units,
):
    persist_notification(
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        recipient=recipient,
        service=sample_job.service,
        personalisation=None,
        notification_type=NotificationType.SMS,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        job_id=sample_job.id,
        job_row_number=10,
        client_reference="ref from client",
    )
    stmt = select(Notification)
    persisted_notification = db.session.execute(stmt).scalars().all()[0]

    assert persisted_notification.international is expected_international
    assert persisted_notification.phone_prefix == expected_prefix
    assert persisted_notification.rate_multiplier == expected_units


def test_persist_notification_with_international_info_does_not_store_for_email(
    sample_job, sample_api_key, mocker
):
    persist_notification(
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        recipient="foo@bar.com",
        service=sample_job.service,
        personalisation=None,
        notification_type=NotificationType.EMAIL,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        job_id=sample_job.id,
        job_row_number=10,
        client_reference="ref from client",
    )
    stmt = select(Notification)
    persisted_notification = db.session.execute(stmt).scalars().all()[0]

    assert persisted_notification.international is False
    assert persisted_notification.phone_prefix is None
    assert persisted_notification.rate_multiplier is None


@pytest.mark.parametrize(
    "recipient, expected_recipient_normalised",
    [
        # ("+4407900900123", "+447900900123"),
        ("202-867-5309", "+12028675309"),
        ("1 202-867-5309", "+12028675309"),
        ("+1 (202) 867-5309", "+12028675309"),
        ("(202) 867-5309", "+12028675309"),
        ("2028675309", "+12028675309"),
    ],
)
def test_persist_sms_notification_stores_normalised_number(
    sample_job, sample_api_key, mocker, recipient, expected_recipient_normalised
):
    persist_notification(
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        recipient=recipient,
        service=sample_job.service,
        personalisation=None,
        notification_type=NotificationType.SMS,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        job_id=sample_job.id,
    )
    stmt = select(Notification)
    persisted_notification = db.session.execute(stmt).scalars().all()[0]

    assert persisted_notification.to == "1"
    assert persisted_notification.normalised_to == "1"


@pytest.mark.parametrize(
    "recipient, expected_recipient_normalised",
    [("FOO@bar.com", "foo@bar.com"), ("BAR@foo.com", "bar@foo.com")],
)
def test_persist_email_notification_stores_normalised_email(
    sample_job, sample_api_key, mocker, recipient, expected_recipient_normalised
):
    persist_notification(
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        recipient=recipient,
        service=sample_job.service,
        personalisation=None,
        notification_type=NotificationType.EMAIL,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        job_id=sample_job.id,
    )
    stmt = select(Notification)
    persisted_notification = db.session.execute(stmt).scalars().all()[0]

    assert persisted_notification.to == "1"
    assert persisted_notification.normalised_to == "1"


def test_persist_notification_with_billable_units_stores_correct_info(mocker):
    service = create_service(service_permissions=[ServicePermissionType.SMS])
    template = create_template(service, template_type=TemplateType.SMS)
    mocker.patch("app.dao.templates_dao.dao_get_template_by_id", return_value=template)
    persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient="+12028675309",
        service=template.service,
        personalisation=None,
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KeyType.NORMAL,
        billable_units=3,
    )
    stmt = select(Notification)
    persisted_notification = db.session.execute(stmt).scalars().all()[0]

    assert persisted_notification.billable_units == 3
