import io
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import ANY, MagicMock, Mock, call, patch

import pytest
import requests_mock
from celery.exceptions import Retry
from freezegun import freeze_time
from psycopg2 import IntegrityError
from requests import RequestException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import db, get_encryption
from app.celery import provider_tasks, tasks
from app.celery.tasks import (
    __total_sending_limits_for_job_exceeded,
    _generate_notifications_report,
    get_recipient_csv_and_template_and_sender_id,
    process_incomplete_job,
    process_incomplete_jobs,
    process_job,
    process_row,
    s3,
    save_api_email,
    save_api_email_or_sms,
    save_api_sms,
    save_email,
    save_sms,
    send_inbound_sms_to_service,
)
from app.config import QueueNames
from app.dao import jobs_dao, service_email_reply_to_dao, service_sms_sender_dao
from app.enums import (
    JobStatus,
    KeyType,
    NotificationStatus,
    NotificationType,
    TemplateType,
)
from app.models import Job, Notification
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.utils import DATETIME_FORMAT, utc_now
from notifications_utils.recipients import Row
from notifications_utils.template import PlainTextEmailTemplate, SMSMessageTemplate
from tests.app import load_example_csv
from tests.app.db import (
    create_api_key,
    create_inbound_sms,
    create_job,
    create_notification,
    create_reply_to_email,
    create_service,
    create_service_inbound_api,
    create_service_with_defined_sms_sender,
    create_template,
    create_user,
)

encryption = get_encryption()


class AnyStringWith(str):
    def __eq__(self, other):
        return self in other


def _notification_json(template, to, personalisation=None, job_id=None, row_number=0):
    return {
        "template": str(template.id),
        "template_version": template.version,
        "to": to,
        "notification_type": template.template_type,
        "personalisation": personalisation or {},
        "job": job_id and str(job_id),
        "row_number": row_number,
    }


def test_should_have_decorated_tasks_functions():
    assert process_job.__wrapped__.__name__ == "process_job"
    assert save_sms.__wrapped__.__name__ == "save_sms"
    assert save_email.__wrapped__.__name__ == "save_email"


@pytest.fixture
def email_job_with_placeholders(
    notify_db_session, sample_email_template_with_placeholders
):
    return create_job(template=sample_email_template_with_placeholders)


# -------------- process_job tests -------------- #


def test_should_process_sms_job(sample_job, mocker):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("sms"), {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.save_sms.apply_async")
    mock_encrypt = mocker.patch("app.celery.tasks.encryption.encrypt")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(sample_job.id)
    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job.service.id), job_id=str(sample_job.id)
    )
    assert mock_encrypt.call_args[0][0]["to"] == "+14254147755"
    assert mock_encrypt.call_args[0][0]["template"] == str(sample_job.template.id)
    assert (
        mock_encrypt.call_args[0][0]["template_version"] == sample_job.template.version
    )
    assert mock_encrypt.call_args[0][0]["personalisation"] == {
        "phonenumber": "+14254147755"
    }
    assert mock_encrypt.call_args[0][0]["row_number"] == 0
    tasks.save_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id), "uuid", ANY),
        {},
        queue="database-tasks",
        expires=ANY,
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == JobStatus.FINISHED


def test_should_process_sms_job_with_sender_id(sample_job, mocker, fake_uuid):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("sms"), {"sender_id": fake_uuid}),
    )
    mocker.patch("app.celery.tasks.save_sms.apply_async")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(sample_job.id, sender_id=fake_uuid)

    tasks.save_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id), "uuid", ANY),
        {"sender_id": fake_uuid},
        queue="database-tasks",
        expires=ANY,
    )


def test_should_not_process_job_if_already_pending(sample_template, mocker):
    job = create_job(template=sample_template, job_status=JobStatus.SCHEDULED)

    mocker.patch("app.celery.tasks.s3.get_job_and_metadata_from_s3")
    mocker.patch("app.celery.tasks.process_row")

    process_job(job.id)

    assert s3.get_job_and_metadata_from_s3.called is False
    assert tasks.process_row.called is False


def test_should_process_job_if_send_limits_are_not_exceeded(
    notify_api, notify_db_session, mocker
):
    service = create_service(message_limit=10)
    template = create_template(service=service, template_type=TemplateType.EMAIL)
    job = create_job(template=template, notification_count=10)

    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.save_email.apply_async")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")
    process_job(job.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(job.service.id), job_id=str(job.id)
    )
    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == JobStatus.FINISHED
    tasks.save_email.apply_async.assert_called_with(
        (
            str(job.service_id),
            "uuid",
            ANY,
        ),
        {},
        queue="database-tasks",
        expires=ANY,
    )


def test_should_not_create_save_task_for_empty_file(sample_job, mocker):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("empty"), {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.save_sms.apply_async")

    process_job(sample_job.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job.service.id), job_id=str(sample_job.id)
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == JobStatus.FINISHED
    assert tasks.save_sms.apply_async.called is False


def test_should_process_email_job(email_job_with_placeholders, mocker):
    email_csv = """email_address,name
    test@test.com,foo
    """
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(email_csv, {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.save_email.apply_async")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    mock_encrypt = mocker.patch("app.celery.tasks.encryption.encrypt")

    process_job(email_job_with_placeholders.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(email_job_with_placeholders.service.id),
        job_id=str(email_job_with_placeholders.id),
    )
    assert mock_encrypt.call_args[0][0]["to"] == "test@test.com"
    assert mock_encrypt.call_args[0][0]["template"] == str(
        email_job_with_placeholders.template.id
    )
    assert (
        mock_encrypt.call_args[0][0]["template_version"]
        == email_job_with_placeholders.template.version
    )
    assert mock_encrypt.call_args[0][0]["personalisation"] == {
        "emailaddress": "test@test.com",
        "name": "foo",
    }
    tasks.save_email.apply_async.assert_called_once_with(
        (
            str(email_job_with_placeholders.service_id),
            "uuid",
            ANY,
        ),
        {},
        queue="database-tasks",
        expires=ANY,
    )
    job = jobs_dao.dao_get_job_by_id(email_job_with_placeholders.id)
    assert job.job_status == JobStatus.FINISHED


def test_should_process_email_job_with_sender_id(
    email_job_with_placeholders, mocker, fake_uuid
):
    email_csv = """email_address,name
    test@test.com,foo
    """
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(email_csv, {"sender_id": fake_uuid}),
    )
    mocker.patch("app.celery.tasks.save_email.apply_async")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(email_job_with_placeholders.id, sender_id=fake_uuid)

    tasks.save_email.apply_async.assert_called_once_with(
        (str(email_job_with_placeholders.service_id), "uuid", ANY),
        {"sender_id": fake_uuid},
        queue="database-tasks",
        expires=ANY,
    )


def test_should_process_all_sms_job(sample_job_with_placeholdered_template, mocker):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.save_sms.apply_async")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    mock_encrypt = mocker.patch("app.celery.tasks.encryption.encrypt")

    process_job(sample_job_with_placeholdered_template.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job_with_placeholdered_template.service.id),
        job_id=str(sample_job_with_placeholdered_template.id),
    )
    assert mock_encrypt.call_args[0][0]["to"] == "+14254147755"
    assert mock_encrypt.call_args[0][0]["template"] == str(
        sample_job_with_placeholdered_template.template.id
    )
    assert (
        mock_encrypt.call_args[0][0]["template_version"]
        == sample_job_with_placeholdered_template.template.version
    )  # noqa
    assert mock_encrypt.call_args[0][0]["personalisation"] == {
        "phonenumber": "+14254147755",
        "name": "chris",
    }
    assert tasks.save_sms.apply_async.call_count == 10
    job = jobs_dao.dao_get_job_by_id(sample_job_with_placeholdered_template.id)
    assert job.job_status == JobStatus.FINISHED


# -------------- process_row tests -------------- #


@pytest.mark.parametrize(
    "template_type, expected_function, expected_queue",
    [
        (TemplateType.SMS, "save_sms", "database-tasks"),
        (TemplateType.EMAIL, "save_email", "database-tasks"),
    ],
)
def test_process_row_sends_letter_task(
    template_type, expected_function, expected_queue, mocker
):
    mocker.patch("app.celery.tasks.create_uuid", return_value="noti_uuid")
    task_mock = mocker.patch(f"app.celery.tasks.{expected_function}.apply_async")
    encrypt_mock = mocker.patch("app.celery.tasks.encryption.encrypt")
    template = Mock(id="template_id", template_type=template_type)
    job = Mock(id="job_id", template_version="temp_vers")
    service = Mock(id="service_id")

    process_row(
        Row(
            {"foo": "bar", "to": "recip"},
            index="row_num",
            error_fn=lambda k, v: None,
            recipient_column_headers=["to"],
            placeholders={"foo"},
            template=template,
            allow_international_letters=True,
        ),
        template,
        job,
        service,
    )

    encrypt_mock.assert_called_once_with(
        {
            "template": "template_id",
            "template_version": "temp_vers",
            "job": "job_id",
            "to": "recip",
            "row_number": "row_num",
            "personalisation": {"foo": "bar"},
        }
    )
    task_mock.assert_called_once_with(
        (
            "service_id",
            "noti_uuid",
            # encrypted data
            encrypt_mock.return_value,
        ),
        {},
        queue=expected_queue,
        expires=ANY,
    )


def test_process_row_when_sender_id_is_provided(mocker, fake_uuid):
    mocker.patch("app.celery.tasks.create_uuid", return_value="noti_uuid")
    task_mock = mocker.patch("app.celery.tasks.save_sms.apply_async")
    encrypt_mock = mocker.patch("app.celery.tasks.encryption.encrypt")
    template = Mock(id="template_id", template_type=TemplateType.SMS)
    job = Mock(id="job_id", template_version="temp_vers")
    service = Mock(id="service_id", research_mode=False)

    process_row(
        Row(
            {"foo": "bar", "to": "recip"},
            index="row_num",
            error_fn=lambda k, v: None,
            recipient_column_headers=["to"],
            placeholders={"foo"},
            template=template,
            allow_international_letters=True,
        ),
        template,
        job,
        service,
        sender_id=fake_uuid,
    )

    task_mock.assert_called_once_with(
        (
            "service_id",
            "noti_uuid",
            # encrypted data
            encrypt_mock.return_value,
        ),
        {"sender_id": fake_uuid},
        queue="database-tasks",
        expires=ANY,
    )


# -------- save_sms and save_email tests -------- #


def test_should_send_template_to_correct_sms_task_and_persist(
    sample_template_with_placeholders, mocker
):
    notification = _notification_json(
        sample_template_with_placeholders,
        to="+14254147755",
        personalisation={"name": "Jo"},
    )

    mocked_deliver_sms = mocker.patch(
        "app.celery.provider_tasks.deliver_sms.apply_async"
    )

    save_sms(
        sample_template_with_placeholders.service_id,
        uuid.uuid4(),
        encryption.encrypt(notification),
    )

    persisted_notification = _get_notification_query_one()
    assert persisted_notification.to == "1"
    assert persisted_notification.template_id == sample_template_with_placeholders.id
    assert (
        persisted_notification.template_version
        == sample_template_with_placeholders.version
    )
    assert persisted_notification.status == NotificationStatus.CREATED
    assert persisted_notification.created_at <= utc_now()
    assert not persisted_notification.sent_at
    assert not persisted_notification.sent_by
    assert not persisted_notification.job_id
    assert persisted_notification.personalisation == {}
    assert persisted_notification.notification_type == NotificationType.SMS
    mocked_deliver_sms.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-sms-tasks", countdown=60
    )


def _get_notification_query_one():
    stmt = select(Notification)
    return db.session.execute(stmt).scalars().one()


def test_should_save_sms_if_restricted_service_and_valid_number(
    notify_db_session, mocker
):
    user = create_user(mobile_number="202-867-5309")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)
    notification = _notification_json(
        template, "+12028675309"
    )  # The user’s own number, but in a different format

    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    encrypt_notification = encryption.encrypt(notification)
    save_sms(
        service.id,
        notification_id,
        encrypt_notification,
    )

    persisted_notification = _get_notification_query_one()
    assert persisted_notification.to == "1"
    assert persisted_notification.template_id == template.id
    assert persisted_notification.template_version == template.version
    assert persisted_notification.status == NotificationStatus.CREATED
    assert persisted_notification.created_at <= utc_now()
    assert not persisted_notification.sent_at
    assert not persisted_notification.sent_by
    assert not persisted_notification.job_id
    assert not persisted_notification.personalisation
    assert persisted_notification.notification_type == NotificationType.SMS
    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-sms-tasks", countdown=60
    )


def test_save_email_should_save_default_email_reply_to_text_on_notification(
    notify_db_session, mocker
):
    service = create_service()
    create_reply_to_email(
        service=service, email_address="reply_to@digital.fake.gov", is_default=True
    )
    template = create_template(
        service=service,
        template_type=TemplateType.EMAIL,
        subject="Hello",
    )

    notification = _notification_json(template, to="test@example.com")
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    notification_id = uuid.uuid4()
    save_email(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )

    persisted_notification = _get_notification_query_one()
    assert persisted_notification.reply_to_text == "reply_to@digital.fake.gov"


def test_save_sms_should_save_default_sms_sender_notification_reply_to_text_on(
    notify_db_session, mocker
):
    service = create_service_with_defined_sms_sender(sms_sender_value="12345")
    template = create_template(service=service)

    notification = _notification_json(template, to="2028675309")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )

    persisted_notification = _get_notification_query_one()
    assert persisted_notification.reply_to_text == "12345"


def test_should_not_save_sms_if_restricted_service_and_invalid_number(
    notify_db_session, mocker
):
    user = create_user(mobile_number="2028675309")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)

    notification = _notification_json(template, "2028675400")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )
    assert provider_tasks.deliver_sms.apply_async.called is False
    assert _get_notification_query_count() == 0


def _get_notification_query_all():
    stmt = select(Notification)
    return db.session.execute(stmt).scalars().all()


def _get_notification_query_count():
    stmt = select(func.count()).select_from(Notification)
    return db.session.execute(stmt).scalar() or 0


def test_should_not_save_email_if_restricted_service_and_invalid_email_address(
    notify_db_session, mocker
):
    user = create_user()
    service = create_service(user=user, restricted=True)
    template = create_template(
        service=service,
        template_type=TemplateType.EMAIL,
        subject="Hello",
    )
    notification = _notification_json(template, to="test@example.com")

    notification_id = uuid.uuid4()
    save_email(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )

    assert _get_notification_query_count() == 0


def test_should_save_sms_template_to_and_persist_with_job_id(sample_job, mocker):
    notification = _notification_json(
        sample_job.template,
        to="+14254147755",
        job_id=sample_job.id,
        row_number=2,
    )
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    now = utc_now()
    save_sms(
        sample_job.service.id,
        notification_id,
        encryption.encrypt(notification),
    )
    persisted_notification = _get_notification_query_one()
    assert persisted_notification.to == "1"
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.template_id == sample_job.template.id
    assert persisted_notification.status == NotificationStatus.CREATED
    assert not persisted_notification.sent_at
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_by
    assert persisted_notification.job_row_number == 2
    assert persisted_notification.api_key_id is None
    assert persisted_notification.key_type == KeyType.NORMAL
    assert persisted_notification.notification_type == NotificationType.SMS

    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-sms-tasks", countdown=60
    )


def test_should_not_save_sms_if_team_key_and_recipient_not_in_team(
    notify_db_session, mocker
):
    assert _get_notification_query_count() == 0
    user = create_user(mobile_number="2028675309")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)

    team_members = [user.mobile_number for user in service.users]
    assert "07890 300000" not in team_members

    notification = _notification_json(template, "2028675400")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )
    assert provider_tasks.deliver_sms.apply_async.called is False
    assert _get_notification_query_count() == 0


def test_should_use_email_template_and_persist(
    sample_email_template_with_placeholders, sample_api_key, mocker
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    now = datetime(2016, 1, 1, 11, 9, 0)
    notification_id = uuid.uuid4()

    with freeze_time("2016-01-01 12:00:00.000000"):
        notification = _notification_json(
            sample_email_template_with_placeholders,
            "my_email@my_email.com",
            {"name": "Jo"},
            row_number=1,
        )

    with freeze_time("2016-01-01 11:10:00.00000"):
        save_email(
            sample_email_template_with_placeholders.service_id,
            notification_id,
            encryption.encrypt(notification),
        )

    persisted_notification = _get_notification_query_one()
    assert persisted_notification.to == "1"
    assert (
        persisted_notification.template_id == sample_email_template_with_placeholders.id
    )
    assert (
        persisted_notification.template_version
        == sample_email_template_with_placeholders.version
    )
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == NotificationStatus.CREATED
    assert not persisted_notification.sent_by
    assert persisted_notification.job_row_number == 1
    assert persisted_notification.personalisation == {}
    assert persisted_notification.api_key_id is None
    assert persisted_notification.key_type == KeyType.NORMAL
    assert persisted_notification.notification_type == NotificationType.EMAIL

    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-email-tasks"
    )


def test_save_email_should_use_template_version_from_job_not_latest(
    sample_email_template, mocker
):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    version_on_notification = sample_email_template.version
    # Change the template
    from app.dao.templates_dao import dao_get_template_by_id, dao_update_template

    sample_email_template.content = (
        sample_email_template.content + " another version of the template"
    )

    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    dao_update_template(sample_email_template)
    t = dao_get_template_by_id(sample_email_template.id)
    assert t.version > version_on_notification
    now = utc_now()
    save_email(
        sample_email_template.service_id,
        uuid.uuid4(),
        encryption.encrypt(notification),
    )

    persisted_notification = _get_notification_query_one()
    assert persisted_notification.to == "1"
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == NotificationStatus.CREATED
    assert not persisted_notification.sent_by
    assert persisted_notification.notification_type == NotificationType.EMAIL
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-email-tasks"
    )


def test_should_use_email_template_subject_placeholders(
    sample_email_template_with_placeholders, mocker
):
    notification = _notification_json(
        sample_email_template_with_placeholders, "my_email@my_email.com", {"name": "Jo"}
    )
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    notification_id = uuid.uuid4()
    now = utc_now()
    save_email(
        sample_email_template_with_placeholders.service_id,
        notification_id,
        encryption.encrypt(notification),
    )
    persisted_notification = _get_notification_query_one()
    assert persisted_notification.to == "1"
    assert (
        persisted_notification.template_id == sample_email_template_with_placeholders.id
    )
    assert persisted_notification.status == NotificationStatus.CREATED
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_by
    assert persisted_notification.personalisation == {}
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == NotificationType.EMAIL
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-email-tasks"
    )


def test_save_email_uses_the_reply_to_text_when_provided(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    service = sample_email_template.service
    notification_id = uuid.uuid4()
    service_email_reply_to_dao.add_reply_to_email_address_for_service(
        service.id,
        "default@example.com",
        True,
    )
    other_email_reply_to = (
        service_email_reply_to_dao.add_reply_to_email_address_for_service(
            service.id,
            "other@example.com",
            False,
        )
    )

    save_email(
        sample_email_template.service_id,
        notification_id,
        encryption.encrypt(notification),
        sender_id=other_email_reply_to.id,
    )
    persisted_notification = _get_notification_query_one()
    assert persisted_notification.notification_type == NotificationType.EMAIL
    assert persisted_notification.reply_to_text == "other@example.com"


def test_save_email_uses_the_default_reply_to_text_if_sender_id_is_none(
    sample_email_template, mocker
):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    service = sample_email_template.service
    notification_id = uuid.uuid4()
    service_email_reply_to_dao.add_reply_to_email_address_for_service(
        service.id,
        "default@example.com",
        True,
    )

    save_email(
        sample_email_template.service_id,
        notification_id,
        encryption.encrypt(notification),
        sender_id=None,
    )
    persisted_notification = _get_notification_query_one()
    assert persisted_notification.notification_type == NotificationType.EMAIL
    assert persisted_notification.reply_to_text == "default@example.com"


def test_should_use_email_template_and_persist_without_personalisation(
    sample_email_template, mocker
):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    notification_id = uuid.uuid4()

    now = utc_now()
    save_email(
        sample_email_template.service_id,
        notification_id,
        encryption.encrypt(notification),
    )
    persisted_notification = _get_notification_query_one()
    assert persisted_notification.to == "1"
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == NotificationStatus.CREATED
    assert not persisted_notification.sent_by
    assert not persisted_notification.personalisation
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == NotificationType.EMAIL
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-email-tasks"
    )


def test_save_sms_should_go_to_retry_queue_if_database_errors(sample_template, mocker):
    notification = _notification_json(sample_template, "+14254147755")

    expected_exception = SQLAlchemyError()

    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
    mocker.patch("app.celery.tasks.save_sms.retry", side_effect=Retry)
    mocker.patch(
        "app.notifications.process_notifications.dao_create_notification",
        side_effect=expected_exception,
    )

    notification_id = uuid.uuid4()

    with pytest.raises(Retry):
        save_sms(
            sample_template.service_id,
            notification_id,
            encryption.encrypt(notification),
        )
    assert provider_tasks.deliver_sms.apply_async.called is False
    tasks.save_sms.retry.assert_called_with(
        exc=expected_exception, queue="retry-tasks", expires=ANY
    )

    assert _get_notification_query_count() == 0


def test_save_email_should_go_to_retry_queue_if_database_errors(
    sample_email_template, mocker
):
    notification = _notification_json(sample_email_template, "test@example.gov.uk")

    expected_exception = SQLAlchemyError()

    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    mocker.patch("app.celery.tasks.save_email.retry", side_effect=Retry)
    mocker.patch(
        "app.notifications.process_notifications.dao_create_notification",
        side_effect=expected_exception,
    )

    notification_id = uuid.uuid4()

    with pytest.raises(Retry):
        save_email(
            sample_email_template.service_id,
            notification_id,
            encryption.encrypt(notification),
        )
    assert not provider_tasks.deliver_email.apply_async.called
    tasks.save_email.retry.assert_called_with(
        exc=expected_exception, queue="retry-tasks", expires=ANY
    )

    assert _get_notification_query_count() == 0


def test_save_email_does_not_send_duplicate_and_does_not_put_in_retry_queue(
    sample_notification, mocker
):
    json = _notification_json(
        sample_notification.template,
        sample_notification.to,
        job_id=uuid.uuid4(),
        row_number=1,
    )
    deliver_email = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    retry = mocker.patch("app.celery.tasks.save_email.retry", side_effect=Exception())

    notification_id = sample_notification.id

    save_email(
        sample_notification.service_id,
        notification_id,
        encryption.encrypt(json),
    )
    assert _get_notification_query_count() == 1
    assert not deliver_email.called
    assert not retry.called


def test_save_sms_does_not_send_duplicate_and_does_not_put_in_retry_queue(
    sample_notification, mocker
):
    json = _notification_json(
        sample_notification.template,
        sample_notification.to,
        job_id=uuid.uuid4(),
        row_number=1,
    )
    deliver_sms = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
    retry = mocker.patch("app.celery.tasks.save_sms.retry", side_effect=Exception())

    notification_id = sample_notification.id

    save_sms(
        sample_notification.service_id,
        notification_id,
        encryption.encrypt(json),
    )
    assert _get_notification_query_count() == 1
    assert not deliver_sms.called
    assert not retry.called


def test_save_sms_uses_sms_sender_reply_to_text(mocker, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value="2028675309")
    template = create_template(service=service)

    notification = _notification_json(template, to="2028675301")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = str(uuid.uuid4())
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )

    persisted_notification = _get_notification_query_one()
    assert persisted_notification.reply_to_text == "+12028675309"


def test_save_sms_uses_non_default_sms_sender_reply_to_text_if_provided(
    mocker, notify_db_session
):
    service = create_service_with_defined_sms_sender(sms_sender_value="2028675309")
    template = create_template(service=service)
    new_sender = service_sms_sender_dao.dao_add_sms_sender_for_service(
        service.id,
        "new-sender",
        False,
    )

    notification = _notification_json(template, to="202-867-5301")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        sender_id=new_sender.id,
    )

    persisted_notification = _get_notification_query_one()
    assert persisted_notification.reply_to_text == "new-sender"


def test_should_cancel_job_if_service_is_inactive(sample_service, sample_job, mocker):
    sample_service.active = False

    mocker.patch("app.celery.tasks.s3.get_job_from_s3")
    mocker.patch("app.celery.tasks.process_row")

    process_job(sample_job.id)

    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == JobStatus.CANCELLED
    s3.get_job_from_s3.assert_not_called()
    tasks.process_row.assert_not_called()


def test_get_email_template_instance(mocker, sample_email_template, sample_job):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=("", {}),
    )
    sample_job.template_id = sample_email_template.id
    (
        recipient_csv,
        template,
        _sender_id,
    ) = get_recipient_csv_and_template_and_sender_id(sample_job)

    assert isinstance(template, PlainTextEmailTemplate)
    assert recipient_csv.placeholders == ["email address"]


def test_get_sms_template_instance(mocker, sample_template, sample_job):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=("", {}),
    )
    sample_job.template = sample_template
    (
        recipient_csv,
        template,
        _sender_id,
    ) = get_recipient_csv_and_template_and_sender_id(sample_job)

    assert isinstance(template, SMSMessageTemplate)
    assert recipient_csv.placeholders == ["phone number"]


def test_send_inbound_sms_to_service_post_https_request_to_service(
    notify_api, sample_service
):
    inbound_api = create_service_inbound_api(
        service=sample_service,
        url="https://some.service.gov.uk/",
        bearer_token="something_unique",
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="+14254147755",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )
    data = {
        "id": str(inbound_sms.id),
        "source_number": inbound_sms.user_number,
        "destination_number": inbound_sms.notify_number,
        "message": inbound_sms.content,
        "date_received": inbound_sms.provider_date.strftime(DATETIME_FORMAT),
    }

    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url, json={}, status_code=200)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)
    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == inbound_api.url
    assert request_mock.request_history[0].method == "POST"
    assert request_mock.request_history[0].text == json.dumps(data)
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"
    assert (
        request_mock.request_history[0].headers["Authorization"]
        == f"Bearer {inbound_api.bearer_token}"
    )


def test_send_inbound_sms_to_service_does_not_send_request_when_inbound_sms_does_not_exist(
    notify_api, sample_service
):
    inbound_api = create_service_inbound_api(service=sample_service)
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url, json={}, status_code=200)
        with pytest.raises(SQLAlchemyError):
            send_inbound_sms_to_service(
                inbound_sms_id=uuid.uuid4(), service_id=sample_service.id
            )

    assert request_mock.call_count == 0


def test_send_inbound_sms_to_service_does_not_sent_request_when_inbound_api_does_not_exist(
    notify_api, sample_service, mocker
):
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="+14254147755",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )
    mocked = mocker.patch("requests.request")
    send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 0


def test_send_inbound_sms_to_service_retries_if_request_returns_500(
    notify_api, sample_service, mocker
):
    inbound_api = create_service_inbound_api(
        service=sample_service,
        url="https://some.service.gov.uk/",
        bearer_token="something_unique",
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="+14254147755",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )

    mocked = mocker.patch("app.celery.tasks.send_inbound_sms_to_service.retry")
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url, json={}, status_code=500)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 1
    assert mocked.call_args[1]["queue"] == "retry-tasks"


def test_send_inbound_sms_to_service_retries_if_request_throws_unknown(
    notify_api, sample_service, mocker
):
    create_service_inbound_api(
        service=sample_service,
        url="https://some.service.gov.uk/",
        bearer_token="something_unique",
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="+14254147755",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )

    mocked = mocker.patch("app.celery.tasks.send_inbound_sms_to_service.retry")
    mocker.patch("app.celery.tasks.request", side_effect=RequestException())

    send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 1
    assert mocked.call_args[1]["queue"] == "retry-tasks"


def test_send_inbound_sms_to_service_does_not_retries_if_request_returns_404(
    notify_api, sample_service, mocker
):
    inbound_api = create_service_inbound_api(
        service=sample_service,
        url="https://some.service.gov.uk/",
        bearer_token="something_unique",
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="+14254147755",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )

    mocked = mocker.patch("app.celery.tasks.send_inbound_sms_to_service.retry")
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url, json={}, status_code=404)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 0


def test_process_incomplete_job_sms(mocker, sample_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=utc_now() - timedelta(hours=2),
        scheduled_for=utc_now() - timedelta(minutes=31),
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.ERROR,
    )

    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.job_id == job.id)
    )
    count = db.session.execute(stmt).scalar()
    assert count == 2

    process_incomplete_job(str(job.id))

    stmt = select(Job).where(Job.id == job.id)
    completed_job = db.session.execute(stmt).scalars().one()

    assert completed_job.job_status == JobStatus.FINISHED

    assert (
        save_sms.call_count == 8
    )  # There are 10 in the file and we've added two already


def test_process_incomplete_job_with_notifications_all_sent(mocker, sample_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=utc_now() - timedelta(hours=2),
        scheduled_for=utc_now() - timedelta(minutes=31),
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.ERROR,
    )

    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)
    create_notification(sample_template, job, 2)
    create_notification(sample_template, job, 3)
    create_notification(sample_template, job, 4)
    create_notification(sample_template, job, 5)
    create_notification(sample_template, job, 6)
    create_notification(sample_template, job, 7)
    create_notification(sample_template, job, 8)
    create_notification(sample_template, job, 9)

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.job_id == job.id)
    )
    assert db.session.execute(stmt).scalar() == 10

    process_incomplete_job(str(job.id))

    stmt = select(Job).where(Job.id == job.id)
    completed_job = db.session.execute(stmt).scalars().one()

    assert completed_job.job_status == JobStatus.FINISHED

    assert (
        mock_save_sms.call_count == 0
    )  # There are 10 in the file and we've added 10 it should not have been called


def test_process_incomplete_jobs_sms(mocker, sample_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=utc_now() - timedelta(hours=2),
        scheduled_for=utc_now() - timedelta(minutes=31),
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.ERROR,
    )
    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)
    create_notification(sample_template, job, 2)

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.job_id == job.id)
    )
    assert db.session.execute(stmt).scalar() == 3

    job2 = create_job(
        template=sample_template,
        notification_count=10,
        created_at=utc_now() - timedelta(hours=2),
        scheduled_for=utc_now() - timedelta(minutes=31),
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.ERROR,
    )

    create_notification(sample_template, job2, 0)
    create_notification(sample_template, job2, 1)
    create_notification(sample_template, job2, 2)
    create_notification(sample_template, job2, 3)
    create_notification(sample_template, job2, 4)

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.job_id == job2.id)
    )

    assert db.session.execute(stmt).scalar() == 5

    jobs = [job.id, job2.id]
    process_incomplete_jobs(jobs)

    stmt = select(Job).where(Job.id == job.id)
    completed_job = db.session.execute(stmt).scalars().one()
    stmt = select(Job).where(Job.id == job2.id)
    completed_job2 = db.session.execute(stmt).scalars().one()

    assert completed_job.job_status == JobStatus.FINISHED

    assert completed_job2.job_status == JobStatus.FINISHED

    assert (
        mock_save_sms.call_count == 12
    )  # There are 20 in total over 2 jobs we've added 8 already


def test_process_incomplete_jobs_no_notifications_added(mocker, sample_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=utc_now() - timedelta(hours=2),
        scheduled_for=utc_now() - timedelta(minutes=31),
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.ERROR,
    )
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.job_id == job.id)
    )
    assert db.session.execute(stmt).scalar() == 0

    process_incomplete_job(job.id)
    stmt = select(Job).where(Job.id == job.id)
    completed_job = db.session.execute(stmt).scalars().one()

    assert completed_job.job_status == JobStatus.FINISHED

    assert mock_save_sms.call_count == 10  # There are 10 in the csv file


def test_process_incomplete_jobs(mocker):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    jobs = []
    process_incomplete_jobs(jobs)

    assert (
        mock_save_sms.call_count == 0
    )  # There are no jobs to process so it will not have been called


def test_process_incomplete_job_no_job_in_database(mocker, fake_uuid):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    with pytest.raises(expected_exception=Exception):
        process_incomplete_job(fake_uuid)

    assert (
        mock_save_sms.call_count == 0
    )  # There is no job in the db it will not have been called


def test_process_incomplete_job_email(mocker, sample_email_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mock_email_saver = mocker.patch("app.celery.tasks.save_email.apply_async")

    job = create_job(
        template=sample_email_template,
        notification_count=10,
        created_at=utc_now() - timedelta(hours=2),
        scheduled_for=utc_now() - timedelta(minutes=31),
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.ERROR,
    )

    create_notification(sample_email_template, job, 0)
    create_notification(sample_email_template, job, 1)

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.job_id == job.id)
    )
    assert db.session.execute(stmt).scalar() == 2

    process_incomplete_job(str(job.id))

    stmt = select(Job).where(Job.id == job.id)
    completed_job = db.session.execute(stmt).scalars().one()

    assert completed_job.job_status == JobStatus.FINISHED

    assert (
        mock_email_saver.call_count == 8
    )  # There are 10 in the file and we've added two already


@freeze_time("2017-01-01")
def test_process_incomplete_jobs_sets_status_to_in_progress_and_resets_processing_started_time(
    mocker, sample_template
):
    mock_process_incomplete_job = mocker.patch(
        "app.celery.tasks.process_incomplete_job"
    )

    job1 = create_job(
        sample_template,
        processing_started=utc_now() - timedelta(minutes=30),
        job_status=JobStatus.ERROR,
    )
    job2 = create_job(
        sample_template,
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.ERROR,
    )

    process_incomplete_jobs([str(job1.id), str(job2.id)])

    assert job1.job_status == JobStatus.IN_PROGRESS
    assert job1.processing_started == utc_now()

    assert job2.job_status == JobStatus.IN_PROGRESS
    assert job2.processing_started == utc_now()

    assert mock_process_incomplete_job.mock_calls == [
        call(str(job1.id)),
        call(str(job2.id)),
    ]


@freeze_time("2020-03-25 14:30")
@pytest.mark.parametrize(
    "notification_type",
    [NotificationType.SMS, NotificationType.EMAIL],
)
def test_save_api_email_or_sms(mocker, sample_service, notification_type):
    template = (
        create_template(sample_service)
        if notification_type == NotificationType.SMS
        else create_template(sample_service, template_type=TemplateType.EMAIL)
    )
    mock_provider_task = mocker.patch(
        f"app.celery.provider_tasks.deliver_{notification_type}.apply_async"
    )
    api_key = create_api_key(service=template.service)
    data = {
        "id": str(uuid.uuid4()),
        "template_id": str(template.id),
        "template_version": template.version,
        "service_id": str(template.service_id),
        "personalisation": None,
        "notification_type": template.template_type,
        "api_key_id": str(api_key.id),
        "key_type": api_key.key_type,
        "client_reference": "our email",
        "reply_to_text": None,
        "document_download_count": 0,
        "status": NotificationStatus.CREATED,
        "created_at": utc_now().strftime(DATETIME_FORMAT),
    }

    if notification_type == NotificationType.EMAIL:
        data.update({"to": "jane.citizen@example.com"})
        expected_queue = QueueNames.SEND_EMAIL
    else:
        data.update({"to": "+14254147755"})
        expected_queue = QueueNames.SEND_SMS

    encrypted = encryption.encrypt(data)

    assert len(_get_notification_query_all()) == 0
    if notification_type == NotificationType.EMAIL:
        save_api_email(encrypted_notification=encrypted)
    else:
        save_api_sms(encrypted_notification=encrypted)
    notifications = _get_notification_query_all()
    assert len(notifications) == 1
    assert str(notifications[0].id) == data["id"]
    assert notifications[0].created_at == datetime(2020, 3, 25, 14, 30)
    assert notifications[0].notification_type == notification_type
    mock_provider_task.assert_called_once_with([data["id"]], queue=expected_queue)


@freeze_time("2020-03-25 14:30")
@pytest.mark.parametrize(
    "notification_type", [NotificationType.SMS, NotificationType.EMAIL]
)
def test_save_api_email_dont_retry_if_notification_already_exists(
    sample_service, mocker, notification_type
):
    template = (
        create_template(sample_service)
        if notification_type == NotificationType.SMS
        else create_template(sample_service, template_type=TemplateType.EMAIL)
    )
    mock_provider_task = mocker.patch(
        f"app.celery.provider_tasks.deliver_{notification_type}.apply_async"
    )
    api_key = create_api_key(service=template.service)
    data = {
        "id": str(uuid.uuid4()),
        "template_id": str(template.id),
        "template_version": template.version,
        "service_id": str(template.service_id),
        "personalisation": None,
        "notification_type": template.template_type,
        "api_key_id": str(api_key.id),
        "key_type": api_key.key_type,
        "client_reference": "our email",
        "reply_to_text": "our.email@gov.uk",
        "document_download_count": 0,
        "status": NotificationStatus.CREATED,
        "created_at": utc_now().strftime(DATETIME_FORMAT),
    }

    if notification_type == NotificationType.EMAIL:
        data.update({"to": "jane.citizen@example.com"})
        expected_queue = QueueNames.SEND_EMAIL
    else:
        data.update({"to": "+14254147755"})
        expected_queue = QueueNames.SEND_SMS

    encrypted = encryption.encrypt(data)
    assert len(_get_notification_query_all()) == 0

    if notification_type == NotificationType.EMAIL:
        save_api_email(encrypted_notification=encrypted)
    else:
        save_api_sms(encrypted_notification=encrypted)
    notifications = _get_notification_query_all()
    assert len(notifications) == 1
    # call the task again with the same notification
    if notification_type == NotificationType.EMAIL:
        save_api_email(encrypted_notification=encrypted)
    else:
        save_api_sms(encrypted_notification=encrypted)
    notifications = _get_notification_query_all()
    assert len(notifications) == 1
    assert str(notifications[0].id) == data["id"]
    assert notifications[0].created_at == datetime(2020, 3, 25, 14, 30)
    # should only have sent the notification once.
    mock_provider_task.assert_called_once_with([data["id"]], queue=expected_queue)


@pytest.mark.parametrize(
    "task_function, delivery_mock, recipient, template_args",
    (
        (
            save_email,
            "app.celery.provider_tasks.deliver_email.apply_async",
            "test@example.com",
            {"template_type": TemplateType.EMAIL, "subject": "Hello"},
        ),
        (
            save_sms,
            "app.celery.provider_tasks.deliver_sms.apply_async",
            "202-867-5309",
            {"template_type": TemplateType.SMS},
        ),
    ),
)
def test_save_tasks_use_cached_service_and_template(
    notify_db_session,
    mocker,
    task_function,
    delivery_mock,
    recipient,
    template_args,
):
    service = create_service()
    template = create_template(service=service, **template_args)

    notification = _notification_json(template, to=recipient)
    delivery_mock = mocker.patch(delivery_mock)
    service_dict_mock = mocker.patch(
        "app.serialised_models.SerialisedService.get_dict",
        wraps=SerialisedService.get_dict,
    )
    template_dict_mock = mocker.patch(
        "app.serialised_models.SerialisedTemplate.get_dict",
        wraps=SerialisedTemplate.get_dict,
    )

    for _ in range(2):
        task_function(
            service.id,
            uuid.uuid4(),
            encryption.encrypt(notification),
        )

    # We talk to the database once for the service and once for the
    # template; subsequent calls are caught by the in memory cache
    assert service_dict_mock.call_args_list == [
        call(service.id),
    ]
    assert template_dict_mock.call_args_list == [
        call(str(template.id), str(service.id), 1),
    ]

    # But we save 2 notifications and enqueue 2 tasks
    assert len(_get_notification_query_all()) == 2
    assert len(delivery_mock.call_args_list) == 2


@freeze_time("2020-03-25 14:30")
@pytest.mark.parametrize(
    "notification_type, task_function, expected_queue, recipient",
    (
        (
            NotificationType.SMS,
            save_api_sms,
            QueueNames.SEND_SMS,
            "+14254147755",
        ),
        (
            NotificationType.EMAIL,
            save_api_email,
            QueueNames.SEND_EMAIL,
            "jane.citizen@example.com",
        ),
    ),
)
def test_save_api_tasks_use_cache(
    sample_service,
    mocker,
    notification_type,
    task_function,
    expected_queue,
    recipient,
):
    mock_provider_task = mocker.patch(
        f"app.celery.provider_tasks.deliver_{notification_type}.apply_async"
    )
    service_dict_mock = mocker.patch(
        "app.serialised_models.SerialisedService.get_dict",
        wraps=SerialisedService.get_dict,
    )

    template = create_template(sample_service, template_type=notification_type)
    api_key = create_api_key(service=template.service)

    def create_encrypted_notification():
        return encryption.encrypt(
            {
                "to": recipient,
                "id": str(uuid.uuid4()),
                "template_id": str(template.id),
                "template_version": template.version,
                "service_id": str(template.service_id),
                "personalisation": None,
                "notification_type": template.template_type,
                "api_key_id": str(api_key.id),
                "key_type": api_key.key_type,
                "client_reference": "our email",
                "reply_to_text": "our.email@gov.uk",
                "document_download_count": 0,
                "status": NotificationStatus.CREATED,
                "created_at": utc_now().strftime(DATETIME_FORMAT),
            }
        )

    assert len(_get_notification_query_all()) == 0

    for _ in range(3):
        task_function(encrypted_notification=create_encrypted_notification())

    assert service_dict_mock.call_args_list == [call(str(template.service_id))]

    assert len(_get_notification_query_all()) == 3
    assert len(mock_provider_task.call_args_list) == 3


def test_total_sending_limits_exceeded(mocker):
    mock_service = MagicMock()
    mock_service.total_message_limit = 1000
    mock_job = MagicMock()
    mock_job.notification_count = 300
    job_id = "test_job_id"

    mock_check_service_limit = mocker.patch(
        "app.celery.tasks.check_service_over_total_message_limit"
    )
    mock_check_service_limit.return_value = 800

    mock_utc_now = mocker.patch("app.celery.tasks.utc_now")
    mock_utc_now.return_value = datetime(2024, 11, 10, 12, 0, 0)

    mock_dao_update_job = mocker.patch("app.celery.tasks.dao_update_job")

    result = __total_sending_limits_for_job_exceeded(mock_service, mock_job, job_id)
    assert result is True

    assert mock_job.job_status == "sending limits exceeded"
    assert mock_job.processing_finished == datetime(2024, 11, 10, 12, 0, 0)
    mock_dao_update_job.assert_called_once_with(mock_job)


def test_save_api_email_or_sms_integrity_error():
    mock_self = MagicMock()
    encrypted = MagicMock()
    decrypted = {
        "id": "notif-id",
        "service_id": "service-id",
        "notification_type": "email",
        "template_id": "template-id",
        "template_version": 1,
        "to": "test@example.com",
        "client_reference": None,
        "created_at": "2025-01-01T00:00:00",
        "reply_to_text": None,
        "status": "created",
        "document_download_count": 0,
    }

    with patch("app.celery.tasks.encryption.decrypt", return_value=decrypted), patch(
        "app.celery.tasks.SerialisedService.from_id"
    ), patch("app.celery.tasks.get_notification", return_value=None), patch(
        "app.celery.tasks.persist_notification",
        side_effect=IntegrityError("msg", None, None),
    ), patch(
        "app.celery.tasks.current_app.logger.warning"
    ) as mock_log:

        with pytest.raises(IntegrityError):
            save_api_email_or_sms(mock_self, encrypted)
            mock_log.assert_called_once()
            assert "already exists" in mock_log.call_args[0][0]
            mock_self.retry.assert_not_called()


def test_save_api_email_or_sms_sqlalchemy_error_with_max_retries():
    encrypted = MagicMock()
    decrypted = {
        "id": "notif-id",
        "service_id": "svc-id",
        "notification_type": "sms",
        "template_id": "template-id",
        "template_version": 1,
        "to": "+15555555",
        "client_reference": None,
        "created_at": "2025-01-01T00:00:00",
        "reply_to_text": "",
        "status": "created",
        "document_download_count": 0,
    }

    class FakeMaxRetriesExceeded(Exception):
        pass

    mock_self = MagicMock()
    mock_self.retry.side_effect = FakeMaxRetriesExceeded
    mock_self.MaxRetriesExceededError = FakeMaxRetriesExceeded

    with patch("app.celery.tasks.encryption.decrypt", return_value=decrypted), patch(
        "app.celery.tasks.SerialisedService.from_id"
    ), patch("app.celery.tasks.get_notification", return_value=None), patch(
        "app.celery.tasks.persist_notification", side_effect=SQLAlchemyError("db issue")
    ), patch(
        "app.celery.tasks.current_app.logger.exception"
    ) as mock_exception:

        save_api_email_or_sms(mock_self, encrypted)
        mock_exception.assert_called_once()
        assert "Max retry failed" in mock_exception.call_args[0][0]


def get_mock_notification():
    notif = MagicMock()
    notif.job_id = "job-id"
    notif.service_id = "service-id"
    notif.job_row_number = 5
    notif.serialize_for_csv.return_value = {
        "recipient": "1234567890",
        "template_name": "Test Template",
        "created_by_name": "Tester",
        "carrier": "TestCarrier",
        "status": "delivered",
        "created_at": "2025-08-10T12:00:00",
        "job_name": "Job A",
        "provider_response": "Success",
    }
    return notif


@patch("app.dao.notifications_dao.get_notifications_for_service")
@patch("app.aws.s3.get_personalisation_from_s3")
@patch("app.aws.s3.get_phone_number_from_s3")
@patch("app.celery.tasks.get_csv_location")
@patch("app.aws.s3.s3upload")
@patch("app.aws.s3.delete_s3_object")
@patch("app.celery.tasks.current_app")
def test_generate_notifications_report_normal_case(
    mock_current_app,
    mock_delete,
    mock_upload,
    mock_get_csv_location,
    mock_get_phone_number,
    mock_get_personalisation,
    mock_get_notifications,
    notify_api,
):

    mock_get_notifications.return_value.items = [get_mock_notification()]
    mock_get_phone_number.return_value = "1234567890"
    mock_get_personalisation.return_value = {"name": "John"}
    mock_get_csv_location.return_value = (
        "my-bucket",
        "some/file/location.csv",
        "access",
        "sekret",
        "region",
    )

    mock_current_app.config = {
        "CSV_UPLOAD_BUCKET": {"bucket": "my-bucket", "region": "region"}
    }

    _generate_notifications_report("service-id", "report-id", 7)

    mock_get_personalisation.assert_called_once()
    mock_get_phone_number.assert_called_once()

    mock_upload.assert_called_once()
    args, kwargs = mock_upload.call_args
    assert kwargs["bucket_name"] == "my-bucket"
    assert kwargs["file_location"] == "some/file/location.csv"
    assert isinstance(kwargs["filedata"], io.BytesIO)


@patch("app.aws.s3.delete_s3_object")
@patch("app.celery.tasks.get_csv_location")
@patch("app.dao.notifications_dao.get_notifications_for_service")
@patch("app.celery.tasks.current_app")
def test_generate_notifications_report_no_notifications(
    mock_current_app,
    mock_get_notifications,
    mock_get_csv_location,
    mock_delete_s3,
    notify_api,
):
    mock_get_notifications.return_value.items = []
    mock_get_csv_location.return_value = (
        "bucket",
        "service-id-service-notify/report-id.csv",
        "access",
        "secret",
        "region",
    )

    _generate_notifications_report("service-id", "report-id", 7)

    mock_current_app.logger.info.assert_any_call("SKIP service-id")
    mock_delete_s3.assert_called_once_with("service-id-service-notify/report-id.csv")
    mock_current_app.logger.info.assert_any_call(
        "Deleted stale report service-id-service-notify/report-id.csv - no new data"
    )
