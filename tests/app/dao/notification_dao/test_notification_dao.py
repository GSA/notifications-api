import uuid
from datetime import date, datetime, timedelta
from functools import partial
from unittest.mock import ANY, MagicMock, patch

import pytest
from freezegun import freeze_time
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao.notifications_dao import (
    dao_close_out_delivery_receipts,
    dao_create_notification,
    dao_delete_notifications_by_id,
    dao_get_last_notification_added_for_job_id,
    dao_get_notification_by_reference,
    dao_get_notification_count_for_job_id,
    dao_get_notification_count_for_service,
    dao_get_notification_count_for_service_message_ratio,
    dao_get_notification_history_by_reference,
    dao_get_notifications_by_recipient_or_reference,
    dao_timeout_notifications,
    dao_update_delivery_receipts,
    dao_update_notification,
    dao_update_notifications_by_reference,
    get_notification_by_id,
    get_notification_with_personalisation,
    get_notifications_for_job,
    get_notifications_for_service,
    get_recent_notifications_for_job,
    get_service_ids_with_notifications_on_date,
    notifications_not_yet_sent,
    sanitize_successful_notification_by_id,
    update_notification_status_by_id,
    update_notification_status_by_reference,
)
from app.enums import (
    JobStatus,
    KeyType,
    NotificationStatus,
    NotificationType,
)
from app.models import Job, Notification, NotificationHistory
from app.utils import utc_now
from tests.app.db import (
    create_ft_notification_status,
    create_job,
    create_notification,
    create_notification_history,
    create_service,
    create_template,
)


def test_should_by_able_to_update_status_by_reference(
    sample_email_template, ses_provider
):
    data = _notification_json(sample_email_template, status=NotificationStatus.SENDING)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.SENDING
    )
    notification.reference = "reference"
    dao_update_notification(notification)

    updated = update_notification_status_by_reference(
        "reference", NotificationStatus.DELIVERED
    )
    assert updated.status == NotificationStatus.DELIVERED
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )


def test_should_by_able_to_update_status_by_id(
    sample_template, sample_job, sns_provider
):
    with freeze_time("2000-01-01 12:00:00"):
        data = _notification_json(
            sample_template,
            job_id=sample_job.id,
            status=NotificationStatus.SENDING,
        )
        notification = Notification(**data)
        dao_create_notification(notification)
        assert notification.status == NotificationStatus.SENDING

    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.SENDING
    )

    with freeze_time("2000-01-02 12:00:00"):
        updated = update_notification_status_by_id(
            notification.id,
            NotificationStatus.DELIVERED,
        )

    assert updated.status == NotificationStatus.DELIVERED
    assert updated.updated_at == datetime(2000, 1, 2, 12, 0, 0)
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )
    assert notification.updated_at == datetime(2000, 1, 2, 12, 0, 0)
    assert notification.status == NotificationStatus.DELIVERED


def test_should_not_update_status_by_id_if_not_sending_and_does_not_update_job(
    sample_job,
):
    notification = create_notification(
        template=sample_job.template,
        status=NotificationStatus.DELIVERED,
        job=sample_job,
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )
    assert not update_notification_status_by_id(
        notification.id, NotificationStatus.FAILED
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )
    assert sample_job == db.session.get(Job, notification.job_id)


def test_should_not_update_status_by_reference_if_not_sending_and_does_not_update_job(
    sample_job,
):
    notification = create_notification(
        template=sample_job.template,
        status=NotificationStatus.DELIVERED,
        reference="reference",
        job=sample_job,
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )
    assert not update_notification_status_by_reference(
        "reference", NotificationStatus.FAILED
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )
    assert sample_job == db.session.get(Job, notification.job_id)


def test_should_update_status_by_id_if_created(sample_template, sample_notification):
    assert (
        db.session.get(Notification, sample_notification.id).status
        == NotificationStatus.CREATED
    )
    updated = update_notification_status_by_id(
        sample_notification.id,
        NotificationStatus.FAILED,
    )
    assert (
        db.session.get(Notification, sample_notification.id).status
        == NotificationStatus.FAILED
    )
    assert updated.status == NotificationStatus.FAILED


def test_should_update_status_by_id_and_set_sent_by(sample_template):
    notification = create_notification(
        template=sample_template, status=NotificationStatus.SENDING
    )

    updated = update_notification_status_by_id(
        notification.id,
        NotificationStatus.DELIVERED,
        sent_by="sns",
    )
    assert updated.status == NotificationStatus.DELIVERED
    assert updated.sent_by == "sns"


def test_should_not_update_status_by_reference_if_from_country_with_no_delivery_receipts(
    sample_template,
):
    notification = create_notification(
        sample_template, status=NotificationStatus.SENT, reference="foo"
    )

    res = update_notification_status_by_reference("foo", NotificationStatus.FAILED)

    assert res is None
    assert notification.status == NotificationStatus.SENT


def test_should_not_update_status_by_id_if_sent_to_country_with_unknown_delivery_receipts(
    sample_template,
):
    notification = create_notification(
        sample_template,
        status=NotificationStatus.SENT,
        international=True,
        phone_prefix="249",  # sudan has no delivery receipts (or at least, that we know about)
    )

    res = update_notification_status_by_id(
        notification.id, NotificationStatus.DELIVERED
    )

    assert res is None
    assert notification.status == NotificationStatus.SENT


def test_should_not_update_status_by_id_if_sent_to_country_with_carrier_delivery_receipts(
    sample_template,
):
    notification = create_notification(
        sample_template,
        status=NotificationStatus.SENT,
        international=True,
        phone_prefix="1",  # americans only have carrier delivery receipts
    )

    res = update_notification_status_by_id(
        notification.id,
        NotificationStatus.DELIVERED,
    )

    assert res is None
    assert notification.status == NotificationStatus.SENT


def test_should_not_update_status_by_id_if_sent_to_country_with_delivery_receipts(
    sample_template,
):
    notification = create_notification(
        sample_template,
        status=NotificationStatus.SENT,
        international=True,
        phone_prefix="7",  # russians have full delivery receipts
    )

    res = update_notification_status_by_id(
        notification.id,
        NotificationStatus.DELIVERED,
    )

    assert res == notification
    assert notification.status == NotificationStatus.DELIVERED


def test_should_not_update_status_by_reference_if_not_sending(sample_template):
    notification = create_notification(
        template=sample_template,
        status=NotificationStatus.CREATED,
        reference="reference",
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.CREATED
    )
    updated = update_notification_status_by_reference(
        "reference", NotificationStatus.FAILED
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.CREATED
    )
    assert not updated


def test_should_by_able_to_update_status_by_id_from_pending_to_delivered(
    sample_template, sample_job
):
    notification = create_notification(
        template=sample_template,
        job=sample_job,
        status=NotificationStatus.SENDING,
    )

    assert update_notification_status_by_id(
        notification_id=notification.id, status=NotificationStatus.PENDING
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.PENDING
    )

    assert update_notification_status_by_id(
        notification.id,
        NotificationStatus.DELIVERED,
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )


def test_should_by_able_to_update_status_by_id_from_pending_to_temporary_failure(
    sample_template, sample_job
):
    notification = create_notification(
        template=sample_template,
        job=sample_job,
        status=NotificationStatus.SENDING,
        sent_by="sns",
    )

    assert update_notification_status_by_id(
        notification_id=notification.id,
        status=NotificationStatus.PENDING,
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.PENDING
    )

    assert update_notification_status_by_id(
        notification.id,
        status=NotificationStatus.PERMANENT_FAILURE,
    )

    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.TEMPORARY_FAILURE
    )


def test_should_by_able_to_update_status_by_id_from_sending_to_permanent_failure(
    sample_template, sample_job
):
    data = _notification_json(
        sample_template,
        job_id=sample_job.id,
        status=NotificationStatus.SENDING,
    )
    notification = Notification(**data)
    dao_create_notification(notification)
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.SENDING
    )

    assert update_notification_status_by_id(
        notification.id,
        status=NotificationStatus.PERMANENT_FAILURE,
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.PERMANENT_FAILURE
    )


def test_should_not_update_status_once_notification_status_is_delivered(
    sample_email_template,
):
    notification = create_notification(
        template=sample_email_template,
        status=NotificationStatus.SENDING,
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.SENDING
    )

    notification.reference = "reference"
    dao_update_notification(notification)
    update_notification_status_by_reference(
        "reference",
        NotificationStatus.DELIVERED,
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )

    update_notification_status_by_reference(
        "reference",
        NotificationStatus.FAILED,
    )
    assert (
        db.session.get(Notification, notification.id).status
        == NotificationStatus.DELIVERED
    )


def test_should_return_zero_count_if_no_notification_with_id():
    assert not update_notification_status_by_id(
        str(uuid.uuid4()),
        NotificationStatus.DELIVERED,
    )


def test_should_return_zero_count_if_no_notification_with_reference():
    assert not update_notification_status_by_reference(
        "something",
        NotificationStatus.DELIVERED,
    )


def test_create_notification_creates_notification_with_personalisation(
    sample_template_with_placeholders,
    sample_job,
):
    assert _get_notification_query_count() == 0

    data = create_notification(
        template=sample_template_with_placeholders,
        job=sample_job,
        personalisation={"name": "Jo"},
        status=NotificationStatus.CREATED,
    )

    assert _get_notification_query_count() == 1
    notification_from_db = _get_notification_query_all()[0]
    assert notification_from_db.id
    assert data.to == notification_from_db.to
    assert data.job_id == notification_from_db.job_id
    assert data.service == notification_from_db.service
    assert data.template == notification_from_db.template
    assert data.template_version == notification_from_db.template_version
    assert data.created_at == notification_from_db.created_at
    assert notification_from_db.status == NotificationStatus.CREATED
    assert {"name": "Jo"} == notification_from_db.personalisation


def test_save_notification_creates_sms(sample_template, sample_job):
    assert _get_notification_query_count() == 0

    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert _get_notification_query_count() == 1
    notification_from_db = _get_notification_query_all()[0]
    assert notification_from_db.id
    assert "1" == notification_from_db.to
    assert data["job_id"] == notification_from_db.job_id
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == NotificationStatus.CREATED


def _get_notification_query_all():
    stmt = select(Notification)
    return db.session.execute(stmt).scalars().all()


def _get_notification_query_one():
    stmt = select(Notification)
    return db.session.execute(stmt).scalars().one()


def _get_notification_query_count():
    stmt = select(func.count(Notification.id))
    return db.session.execute(stmt).scalar() or 0


def _get_notification_history_query_count():
    stmt = select(func.count(NotificationHistory.id))
    return db.session.execute(stmt).scalar() or 0


def test_save_notification_and_create_email(sample_email_template, sample_job):
    assert _get_notification_query_count() == 0

    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert _get_notification_query_count() == 1
    notification_from_db = _get_notification_query_all()[0]
    assert notification_from_db.id
    assert "1" == notification_from_db.to
    assert data["job_id"] == notification_from_db.job_id
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == NotificationStatus.CREATED


def test_save_notification(sample_email_template, sample_job):
    assert _get_notification_query_count() == 0
    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    notification_2 = Notification(**data)
    dao_create_notification(notification_1)

    assert _get_notification_query_count() == 1

    dao_create_notification(notification_2)

    assert _get_notification_query_count() == 2


def test_save_notification_does_not_creates_history(sample_email_template, sample_job):
    assert _get_notification_query_count() == 0
    data = _notification_json(sample_email_template, job_id=sample_job.id)

    notification_1 = Notification(**data)
    dao_create_notification(notification_1)

    assert _get_notification_query_count() == 1
    assert _get_notification_history_query_count() == 0


def test_update_notification_with_research_mode_service_does_not_create_or_update_history(
    sample_template,
):
    sample_template.service.research_mode = True
    notification = create_notification(template=sample_template)

    assert _get_notification_query_count() == 1
    assert _get_notification_history_query_count() == 0

    notification.status = NotificationStatus.DELIVERED
    dao_update_notification(notification)

    assert _get_notification_query_one().status == NotificationStatus.DELIVERED
    assert _get_notification_history_query_count() == 0


def test_not_save_notification_and_not_create_stats_on_commit_error(
    sample_template, sample_job, sns_provider
):
    random_id = str(uuid.uuid4())

    assert _get_notification_query_count() == 0
    data = _notification_json(sample_template, job_id=random_id)

    notification = Notification(**data)
    with pytest.raises(SQLAlchemyError):
        dao_create_notification(notification)

    assert _get_notification_query_count() == 0
    assert db.session.get(Job, sample_job.id).notifications_sent == 0


def test_save_notification_and_increment_job(sample_template, sample_job, sns_provider):
    assert _get_notification_query_count() == 0
    data = _notification_json(sample_template, job_id=sample_job.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert _get_notification_query_count() == 1
    notification_from_db = _get_notification_query_all()[0]
    assert notification_from_db.id
    assert "1" == notification_from_db.to
    assert data["job_id"] == notification_from_db.job_id
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == NotificationStatus.CREATED

    notification_2 = Notification(**data)
    dao_create_notification(notification_2)
    assert _get_notification_query_count() == 2


def test_save_notification_and_increment_correct_job(sample_template, sns_provider):
    job_1 = create_job(sample_template)
    job_2 = create_job(sample_template)

    assert _get_notification_query_count() == 0
    data = _notification_json(sample_template, job_id=job_1.id)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert _get_notification_query_count() == 1
    notification_from_db = _get_notification_query_all()[0]
    assert notification_from_db.id
    assert "1" == notification_from_db.to
    assert data["job_id"] == notification_from_db.job_id
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == NotificationStatus.CREATED
    assert job_1.id != job_2.id


def test_save_notification_with_no_job(sample_template, sns_provider):
    assert _get_notification_query_count() == 0
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert _get_notification_query_count() == 1
    notification_from_db = _get_notification_query_all()[0]
    assert notification_from_db.id
    assert "1" == notification_from_db.to
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert data["created_at"] == notification_from_db.created_at
    assert notification_from_db.status == NotificationStatus.CREATED


def test_get_notification_with_personalisation_by_id(sample_template):
    notification = create_notification(
        template=sample_template,
        status=NotificationStatus.CREATED,
    )
    notification_from_db = get_notification_with_personalisation(
        sample_template.service.id,
        notification.id,
        key_type=None,
    )
    assert notification == notification_from_db


def test_get_notification_by_id_when_notification_exists(sample_notification):
    notification_from_db = get_notification_by_id(sample_notification.id)

    assert sample_notification == notification_from_db


def test_get_notification_by_id_when_notification_does_not_exist(
    notify_db_session, fake_uuid
):
    notification_from_db = get_notification_by_id(fake_uuid)

    assert notification_from_db is None


def test_get_notification_by_id_when_notification_exists_for_different_service(
    sample_notification,
):
    another_service = create_service(service_name="Another service")

    with pytest.raises(NoResultFound):
        get_notification_by_id(sample_notification.id, another_service.id, _raise=True)


def test_get_notifications_by_reference(sample_template):
    client_reference = "some-client-ref"
    assert len(_get_notification_query_all()) == 0
    create_notification(sample_template, client_reference=client_reference)
    create_notification(sample_template, client_reference=client_reference)
    create_notification(sample_template, client_reference="other-ref")
    all_notifications = get_notifications_for_service(
        sample_template.service_id, client_reference=client_reference
    ).items
    assert len(all_notifications) == 2


def test_save_notification_no_job_id(sample_template):
    assert _get_notification_query_count() == 0
    data = _notification_json(sample_template)

    notification = Notification(**data)
    dao_create_notification(notification)

    assert _get_notification_query_count() == 1
    notification_from_db = _get_notification_query_all()[0]
    assert notification_from_db.id
    assert "1" == notification_from_db.to
    assert data["service"] == notification_from_db.service
    assert data["template_id"] == notification_from_db.template_id
    assert data["template_version"] == notification_from_db.template_version
    assert notification_from_db.status == NotificationStatus.CREATED
    assert data.get("job_id") is None


def test_get_all_notifications_for_job(sample_job):
    for _ in range(0, 5):
        try:
            create_notification(template=sample_job.template, job=sample_job)
        except IntegrityError:
            pass

    notifications_from_db = get_notifications_for_job(
        sample_job.service.id, sample_job.id
    ).items
    assert len(notifications_from_db) == 5


def test_get_recent_notifications_for_job(sample_job):

    for status in NotificationStatus:
        create_notification(template=sample_job.template, job=sample_job, status=status)

    notifications_from_db = get_recent_notifications_for_job(
        sample_job.service.id, sample_job.id
    ).items
    assert len(notifications_from_db) == 13


def test_get_all_notifications_for_job_by_status(sample_job):
    notifications = partial(
        get_notifications_for_job, sample_job.service.id, sample_job.id
    )

    for status in NotificationStatus:
        create_notification(template=sample_job.template, job=sample_job, status=status)

    # assert len(notifications().items) == len(NotificationStatus)

    assert len(notifications(filter_dict={"status": status}).items) == 1

    assert (
        len(notifications(filter_dict={"status": list(NotificationStatus)[:3]}).items)
        == 3
    )


def test_dao_get_notification_count_for_job_id(notify_db_session):
    service = create_service()
    template = create_template(service)
    job = create_job(template, notification_count=3)
    for _ in range(3):
        create_notification(job=job)

    create_notification(template)

    assert dao_get_notification_count_for_job_id(job_id=job.id) == 3


def test_dao_get_notification_count_for_service(notify_db_session):
    service = create_service()
    template = create_template(service)

    create_notification(template)

    assert dao_get_notification_count_for_service(service_id=service.id) == 1


def test_dao_get_notification_count_for_job_id_returns_zero_for_no_notifications_for_job(
    notify_db_session,
):
    service = create_service()
    template = create_template(service)
    job = create_job(template, notification_count=3)
    create_notification(template)

    assert dao_get_notification_count_for_job_id(job_id=job.id) == 0


def test_update_notification_sets_status(sample_notification):
    assert sample_notification.status == NotificationStatus.CREATED
    sample_notification.status = NotificationStatus.FAILED
    dao_update_notification(sample_notification)
    notification_from_db = db.session.get(Notification, sample_notification.id)
    assert notification_from_db.status == NotificationStatus.FAILED


@freeze_time("2016-01-10")
def test_should_limit_notifications_return_by_day_limit_plus_one(sample_template):
    assert len(_get_notification_query_all()) == 0

    # create one notification a day between 1st and 9th,
    # with assumption that the local timezone is EST
    for i in range(1, 11):
        past_date = "2016-01-{0:02d} 12:00:00".format(i)
        with freeze_time(past_date):
            create_notification(
                sample_template,
                created_at=utc_now(),
                status=NotificationStatus.FAILED,
            )

    all_notifications = _get_notification_query_all()
    assert len(all_notifications) == 10

    all_notifications = get_notifications_for_service(
        sample_template.service_id, limit_days=10
    ).items
    assert len(all_notifications) == 10

    all_notifications = get_notifications_for_service(
        sample_template.service_id, limit_days=1
    ).items
    assert len(all_notifications) == 2


def test_creating_notification_does_not_add_notification_history(sample_template):
    create_notification(template=sample_template)
    assert _get_notification_query_count() == 1
    assert _get_notification_history_query_count() == 0


def test_should_delete_notification_for_id(sample_template):
    notification = create_notification(template=sample_template)

    assert _get_notification_query_count() == 1
    assert _get_notification_history_query_count() == 0

    dao_delete_notifications_by_id(notification.id)

    assert _get_notification_query_count() == 0


def test_should_delete_notification_and_ignore_history_for_research_mode(
    sample_template,
):
    sample_template.service.research_mode = True

    notification = create_notification(template=sample_template)

    assert _get_notification_query_count() == 1

    dao_delete_notifications_by_id(notification.id)

    assert _get_notification_query_count() == 0


def test_should_delete_only_notification_with_id(sample_template):
    notification_1 = create_notification(template=sample_template)
    notification_2 = create_notification(template=sample_template)
    assert _get_notification_query_count() == 2

    dao_delete_notifications_by_id(notification_1.id)

    assert _get_notification_query_count() == 1
    stmt = select(Notification)
    assert db.session.execute(stmt).scalars().first().id == notification_2.id


def test_should_delete_no_notifications_if_no_matching_ids(sample_template):
    create_notification(template=sample_template)
    assert _get_notification_query_count() == 1

    dao_delete_notifications_by_id(uuid.uuid4())

    assert _get_notification_query_count() == 1


def _notification_json(sample_template, job_id=None, id=None, status=None):
    data = {
        "to": "+44709123456",
        "service": sample_template.service,
        "service_id": sample_template.service.id,
        "template_id": sample_template.id,
        "template_version": sample_template.version,
        "created_at": utc_now(),
        "billable_units": 1,
        "notification_type": sample_template.template_type,
        "key_type": KeyType.NORMAL,
    }
    if job_id:
        data.update({"job_id": job_id})
    if id:
        data.update({"id": id})
    if status:
        data.update({"status": status})
    return data


def test_dao_timeout_notifications(sample_template):
    with freeze_time(utc_now() - timedelta(minutes=2)):
        created = create_notification(
            sample_template,
            status=NotificationStatus.CREATED,
        )
        sending = create_notification(
            sample_template,
            status=NotificationStatus.SENDING,
        )
        pending = create_notification(
            sample_template,
            status=NotificationStatus.PENDING,
        )
        delivered = create_notification(
            sample_template,
            status=NotificationStatus.DELIVERED,
        )

    temporary_failure_notifications = dao_timeout_notifications(utc_now())

    assert len(temporary_failure_notifications) == 2
    assert db.session.get(Notification, created.id).status == NotificationStatus.CREATED
    assert (
        db.session.get(Notification, sending.id).status
        == NotificationStatus.TEMPORARY_FAILURE
    )
    assert (
        db.session.get(Notification, pending.id).status
        == NotificationStatus.TEMPORARY_FAILURE
    )
    assert (
        db.session.get(Notification, delivered.id).status
        == NotificationStatus.DELIVERED
    )


def test_dao_timeout_notifications_only_updates_for_older_notifications(
    sample_template,
):
    with freeze_time(utc_now() + timedelta(minutes=10)):
        sending = create_notification(
            sample_template,
            status=NotificationStatus.SENDING,
        )
        pending = create_notification(
            sample_template,
            status=NotificationStatus.PENDING,
        )

    temporary_failure_notifications = dao_timeout_notifications(utc_now())

    assert len(temporary_failure_notifications) == 0
    assert db.session.get(Notification, sending.id).status == NotificationStatus.SENDING
    assert db.session.get(Notification, pending.id).status == NotificationStatus.PENDING


def test_should_return_notifications_excluding_jobs_by_default(
    sample_template, sample_job, sample_api_key
):
    create_notification(sample_template, job=sample_job)
    without_job = create_notification(sample_template, api_key=sample_api_key)

    include_jobs = get_notifications_for_service(
        sample_template.service_id, include_jobs=True
    ).items
    assert len(include_jobs) == 2

    exclude_jobs_by_default = get_notifications_for_service(
        sample_template.service_id
    ).items
    assert len(exclude_jobs_by_default) == 1
    assert exclude_jobs_by_default[0].id == without_job.id

    exclude_jobs_manually = get_notifications_for_service(
        sample_template.service_id, include_jobs=False
    ).items
    assert len(exclude_jobs_manually) == 1
    assert exclude_jobs_manually[0].id == without_job.id


def test_should_return_notifications_including_one_offs_by_default(
    sample_user, sample_template
):
    create_notification(sample_template, one_off=True, created_by_id=sample_user.id)
    not_one_off = create_notification(sample_template)

    exclude_one_offs = get_notifications_for_service(
        sample_template.service_id, include_one_off=False
    ).items
    assert len(exclude_one_offs) == 1
    assert exclude_one_offs[0].id == not_one_off.id

    include_one_offs_manually = get_notifications_for_service(
        sample_template.service_id, include_one_off=True
    ).items
    assert len(include_one_offs_manually) == 2

    include_one_offs_by_default = get_notifications_for_service(
        sample_template.service_id
    ).items
    assert len(include_one_offs_by_default) == 2


# TODO this test seems a little bogus.  Why are we messing with the pagination object
# based on a flag?
def test_should_not_count_pages_when_given_a_flag(sample_user, sample_template):
    create_notification(sample_template)
    notification = create_notification(sample_template)

    pagination = get_notifications_for_service(
        sample_template.service_id, count_pages=False, page_size=1
    )
    assert len(pagination.items) == 1
    # In the original test this was set to None, but pagination has completely changed
    # in sqlalchemy 2 so updating the test to what it delivers.
    assert pagination.total == 2
    assert pagination.items[0].id == notification.id


def test_get_notifications_created_by_api_or_csv_are_returned_correctly_excluding_test_key_notifications(
    notify_db_session,
    sample_service,
    sample_job,
    sample_api_key,
    sample_team_api_key,
    sample_test_api_key,
):
    create_notification(
        template=sample_job.template, created_at=utc_now(), job=sample_job
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    all_notifications = _get_notification_query_all()
    assert len(all_notifications) == 4

    # returns all real API derived notifications
    all_notifications = get_notifications_for_service(sample_service.id).items
    assert len(all_notifications) == 2

    # returns all API derived notifications, including those created with test key
    all_notifications = get_notifications_for_service(
        sample_service.id, include_from_test_key=True
    ).items
    assert len(all_notifications) == 3

    # all real notifications including jobs
    all_notifications = get_notifications_for_service(
        sample_service.id, limit_days=1, include_jobs=True
    ).items
    assert len(all_notifications) == 3


def test_get_notifications_with_a_live_api_key_type(
    sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        job=sample_job,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    all_notifications = _get_notification_query_all()
    assert len(all_notifications) == 4

    # only those created with normal API key, no jobs
    all_notifications = get_notifications_for_service(
        sample_job.service.id, limit_days=1, key_type=KeyType.NORMAL
    ).items
    assert len(all_notifications) == 1

    # only those created with normal API key, with jobs
    all_notifications = get_notifications_for_service(
        sample_job.service.id, limit_days=1, include_jobs=True, key_type=KeyType.NORMAL
    ).items
    assert len(all_notifications) == 2


def test_get_notifications_with_a_test_api_key_type(
    sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(
        template=sample_job.template, created_at=utc_now(), job=sample_job
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    # only those created with test API key, no jobs
    all_notifications = get_notifications_for_service(
        sample_job.service_id,
        limit_days=1,
        key_type=KeyType.TEST,
    ).items
    assert len(all_notifications) == 1

    # only those created with test API key, no jobs, even when requested
    all_notifications = get_notifications_for_service(
        sample_job.service_id,
        limit_days=1,
        include_jobs=True,
        key_type=KeyType.TEST,
    ).items
    assert len(all_notifications) == 1


def test_get_notifications_with_a_team_api_key_type(
    sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        job=sample_job,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        sample_job.template,
        created_at=utc_now(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    # only those created with team API key, no jobs
    all_notifications = get_notifications_for_service(
        sample_job.service_id,
        limit_days=1,
        key_type=KeyType.TEAM,
    ).items
    assert len(all_notifications) == 1

    # only those created with team API key, no jobs, even when requested
    all_notifications = get_notifications_for_service(
        sample_job.service_id,
        limit_days=1,
        include_jobs=True,
        key_type=KeyType.TEAM,
    ).items
    assert len(all_notifications) == 1


def test_should_exclude_test_key_notifications_by_default(
    sample_job, sample_api_key, sample_team_api_key, sample_test_api_key
):
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        job=sample_job,
    )

    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_api_key,
        key_type=sample_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_team_api_key,
        key_type=sample_team_api_key.key_type,
    )
    create_notification(
        template=sample_job.template,
        created_at=utc_now(),
        api_key=sample_test_api_key,
        key_type=sample_test_api_key.key_type,
    )

    all_notifications = _get_notification_query_all()
    assert len(all_notifications) == 4

    all_notifications = get_notifications_for_service(
        sample_job.service_id, limit_days=1
    ).items
    assert len(all_notifications) == 2

    all_notifications = get_notifications_for_service(
        sample_job.service_id,
        limit_days=1,
        include_jobs=True,
    ).items
    assert len(all_notifications) == 3

    all_notifications = get_notifications_for_service(
        sample_job.service_id,
        limit_days=1,
        key_type=KeyType.TEST,
    ).items
    assert len(all_notifications) == 1


def test_dao_get_last_notification_added_for_job_id_valid_job_id(sample_template):
    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=utc_now() - timedelta(hours=2),
        scheduled_for=utc_now() - timedelta(minutes=31),
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.IN_PROGRESS,
    )
    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)
    last = create_notification(sample_template, job, 2)

    assert dao_get_last_notification_added_for_job_id(job.id) == last


def test_dao_get_last_notification_added_for_job_id_no_notifications(sample_template):
    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=utc_now() - timedelta(hours=2),
        scheduled_for=utc_now() - timedelta(minutes=31),
        processing_started=utc_now() - timedelta(minutes=31),
        job_status=JobStatus.IN_PROGRESS,
    )

    assert dao_get_last_notification_added_for_job_id(job.id) is None


def test_dao_get_last_notification_added_for_job_id_no_job(sample_template, fake_uuid):
    assert dao_get_last_notification_added_for_job_id(fake_uuid) is None


def test_dao_update_notifications_by_reference_updated_notifications(sample_template):
    notification_1 = create_notification(template=sample_template, reference="ref1")
    notification_2 = create_notification(template=sample_template, reference="ref2")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref1", "ref2"],
        update_dict={"status": NotificationStatus.DELIVERED, "billable_units": 2},
    )
    assert updated_count == 2
    updated_1 = db.session.get(Notification, notification_1.id)
    assert updated_1.billable_units == 2
    assert updated_1.status == NotificationStatus.DELIVERED
    updated_2 = db.session.get(Notification, notification_2.id)
    assert updated_2.billable_units == 2
    assert updated_2.status == NotificationStatus.DELIVERED

    assert updated_history_count == 0


def test_dao_update_notifications_by_reference_updates_history_some_notifications_exist(
    sample_template,
):
    create_notification(template=sample_template, reference="ref1")
    create_notification_history(template=sample_template, reference="ref2")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref1", "ref2"],
        update_dict={"status": NotificationStatus.DELIVERED, "billable_units": 2},
    )
    assert updated_count == 1
    assert updated_history_count == 1


def test_dao_update_notifications_by_reference_updates_history_no_notifications_exist(
    sample_template,
):
    create_notification_history(template=sample_template, reference="ref1")
    create_notification_history(template=sample_template, reference="ref2")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref1", "ref2"],
        update_dict={"status": NotificationStatus.DELIVERED, "billable_units": 2},
    )
    assert updated_count == 0
    assert updated_history_count == 2


def test_dao_update_notifications_by_reference_returns_zero_when_no_notifications_to_update(
    notify_db_session,
):
    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref"],
        update_dict={"status": NotificationStatus.DELIVERED, "billable_units": 2},
    )

    assert updated_count == 0
    assert updated_history_count == 0


def test_dao_update_notifications_by_reference_updates_history_when_one_of_two_notifications_exists(
    sample_template,
):
    notification1 = create_notification_history(
        template=sample_template, reference="ref1"
    )
    notification2 = create_notification(template=sample_template, reference="ref2")

    updated_count, updated_history_count = dao_update_notifications_by_reference(
        references=["ref1", "ref2"],
        update_dict={"status": NotificationStatus.DELIVERED},
    )

    assert updated_count == 1
    assert updated_history_count == 1
    assert (
        db.session.get(Notification, notification2.id).status
        == NotificationStatus.DELIVERED
    )
    assert (
        db.session.get(NotificationHistory, notification1.id).status
        == NotificationStatus.DELIVERED
    )


def test_dao_get_notification_by_reference_with_one_match_returns_notification(
    sample_template,
):
    create_notification(template=sample_template, reference="REF1")
    notification = dao_get_notification_by_reference("REF1")

    assert notification.reference == "REF1"


def test_dao_get_notification_by_reference_with_multiple_matches_raises_error(
    sample_template,
):
    create_notification(template=sample_template, reference="REF1")
    create_notification(template=sample_template, reference="REF1")

    with pytest.raises(SQLAlchemyError):
        dao_get_notification_by_reference("REF1")


def test_dao_get_notification_by_reference_with_no_matches_raises_error(
    notify_db_session,
):
    with pytest.raises(SQLAlchemyError):
        dao_get_notification_by_reference("REF1")


def test_dao_get_notification_history_by_reference_with_one_match_returns_notification(
    sample_template,
):
    create_notification(template=sample_template, reference="REF1")
    notification = dao_get_notification_history_by_reference("REF1")

    assert notification.reference == "REF1"


def test_dao_get_notification_history_by_reference_with_multiple_matches_raises_error(
    sample_template,
):
    create_notification(template=sample_template, reference="REF1")
    create_notification(template=sample_template, reference="REF1")

    with pytest.raises(SQLAlchemyError):
        dao_get_notification_history_by_reference("REF1")


def test_dao_get_notification_history_by_reference_with_no_matches_raises_error(
    notify_db_session,
):
    with pytest.raises(SQLAlchemyError):
        dao_get_notification_history_by_reference("REF1")


@pytest.mark.parametrize(
    "notification_type", [NotificationType.EMAIL, NotificationType.SMS]
)
def test_notifications_not_yet_sent(sample_service, notification_type):
    older_than = 4  # number of seconds the notification can not be older than
    template = create_template(service=sample_service, template_type=notification_type)
    old_notification = create_notification(
        template=template,
        created_at=utc_now() - timedelta(seconds=older_than),
        status=NotificationStatus.CREATED,
    )
    create_notification(
        template=template,
        created_at=utc_now() - timedelta(seconds=older_than),
        status=NotificationStatus.SENDING,
    )
    create_notification(
        template=template,
        created_at=utc_now(),
        status=NotificationStatus.CREATED,
    )

    results = notifications_not_yet_sent(older_than, notification_type)
    assert len(results) == 1
    assert results[0] == old_notification


@pytest.mark.parametrize(
    "notification_type", [NotificationType.EMAIL, NotificationType.SMS]
)
def test_notifications_not_yet_sent_return_no_rows(sample_service, notification_type):
    older_than = 5  # number of seconds the notification can not be older than
    template = create_template(service=sample_service, template_type=notification_type)
    create_notification(
        template=template,
        created_at=utc_now(),
        status=NotificationStatus.CREATED,
    )
    create_notification(
        template=template,
        created_at=utc_now(),
        status=NotificationStatus.SENDING,
    )
    create_notification(
        template=template,
        created_at=utc_now(),
        status=NotificationStatus.DELIVERED,
    )

    results = notifications_not_yet_sent(older_than, notification_type)
    assert len(results) == 0


def test_update_delivery_receipts(mocker):
    mock_session = mocker.patch("app.dao.notifications_dao.db.session")
    receipts = [
        '{"notification.messageId": "msg1", "delivery.phoneCarrier": "carrier1", "delivery.providerResponse": "resp1", "@timestamp": "2024-01-01T12:00:00", "delivery.priceInUSD": "0.00881"}',  # noqa
        '{"notification.messageId": "msg2", "delivery.phoneCarrier": "carrier2", "delivery.providerResponse": "resp2", "@timestamp": "2024-01-01T13:00:00", "delivery.priceInUSD": "0.00881"}',  # noqa
    ]
    delivered = True
    mock_update = MagicMock()
    mock_where = MagicMock()
    mock_values = MagicMock()
    mock_update.where.return_value = mock_where
    mock_where.values.return_value = mock_values

    mock_session.execute.return_value = None
    with patch("app.dao.notifications_dao.update", return_value=mock_update):
        dao_update_delivery_receipts(receipts, delivered)
    mock_update.where.assert_called_once()
    mock_where.values.assert_called_once()
    mock_session.execute.assert_called_once_with(mock_values)
    mock_session.commit.assert_called_once()

    args, kwargs = mock_where.values.call_args
    assert "carrier" in kwargs
    assert "status" in kwargs
    assert "sent_at" in kwargs
    assert "provider_response" in kwargs


def test_close_out_delivery_receipts(mocker):
    mock_session = mocker.patch("app.dao.notifications_dao.db.session")
    mock_update = MagicMock()
    mock_where = MagicMock()
    mock_values = MagicMock()
    mock_update.where.return_value = mock_where
    mock_where.values.return_value = mock_values

    mock_session.execute.return_value = None
    with patch("app.dao.notifications_dao.update", return_value=mock_update):
        dao_close_out_delivery_receipts()
    mock_update.where.assert_called_once()
    mock_where.values.assert_called_once()
    mock_session.execute.assert_called_once_with(mock_values)
    mock_session.commit.assert_called_once()


@pytest.mark.parametrize(
    "created_at_utc,date_to_check,expected_count",
    [
        # Clocks change on the 27th of March 2022, so the query needs to look at the
        # time range 00:00 - 23:00 (UTC) thereafter.
        ("2022-03-27T00:30", date(2022, 3, 27), 1),  # 27/03 00:30 GMT
        ("2022-03-27T22:30", date(2022, 3, 27), 1),  # 27/03 23:30 BST
        ("2022-03-27T23:30", date(2022, 3, 27), 1),  # 28/03 00:30 BST
        ("2022-03-26T23:30", date(2022, 3, 26), 1),  # 26/03 23:30 GMT
    ],
)
def test_get_service_ids_with_notifications_on_date_respects_gmt_bst(
    sample_template, created_at_utc, date_to_check, expected_count
):
    create_notification(template=sample_template, created_at=created_at_utc)
    service_ids = get_service_ids_with_notifications_on_date(
        NotificationType.SMS,
        date_to_check,
    )
    assert len(service_ids) == expected_count


def test_get_service_ids_with_notifications_on_date_checks_ft_status(
    sample_template,
):
    create_notification(template=sample_template, created_at="2022-01-01T09:30")
    create_ft_notification_status(template=sample_template, local_date="2022-01-02")

    assert (
        len(
            get_service_ids_with_notifications_on_date(
                NotificationType.SMS,
                date(2022, 1, 1),
            )
        )
        == 1
    )
    assert (
        len(
            get_service_ids_with_notifications_on_date(
                NotificationType.SMS,
                date(2022, 1, 2),
            )
        )
        == 1
    )


def test_sanitize_successful_notification_by_id():
    notification_id = "12345"
    carrier = "CarrierX"
    provider_response = "Success"

    mock_session = MagicMock()
    mock_text = MagicMock()
    with patch("app.dao.notifications_dao.db.session", mock_session), patch(
        "app.dao.notifications_dao.text", mock_text
    ):
        sanitize_successful_notification_by_id(
            notification_id, carrier, provider_response
        )
        mock_text.assert_called_once_with(
            "\n    update notifications set provider_response=:response, carrier=:carrier,\n    notification_status='delivered', sent_at=:sent_at, \"to\"='1', normalised_to='1'\n    where id=:notification_id\n    "  # noqa
        )
        mock_session.execute.assert_called_once_with(
            mock_text.return_value,
            {
                "notification_id": notification_id,
                "carrier": carrier,
                "response": provider_response,
                "sent_at": ANY,
            },
        )


def test_dao_get_notifications_by_recipient_or_reference_covers_sms_search_by_reference(
    notify_db_session,
):
    """
    This test:
      1. Creates a service and an SMS template.
      2. Creates a notification with a specific client_reference and status=FAILED.
      3. Calls dao_get_notifications_by_recipient_or_reference with notification_type=SMS,
         statuses=[FAILED], and a search term = client_reference.
      4. Confirms the function returns exactly one notification matching that reference.
    """

    service = create_service(service_name="Test Service")
    template = create_template(service=service, template_type=NotificationType.SMS)

    # Instead of matching phone logic, we'll match on client_reference
    data = {
        "id": uuid.uuid4(),
        "to": "1",
        "normalised_to": "1",  # phone is irrelevant here
        "service_id": service.id,
        "service": service,
        "template_id": template.id,
        "template_version": template.version,
        "status": NotificationStatus.FAILED,
        "created_at": utc_now(),
        "billable_units": 1,
        "notification_type": template.template_type,
        "key_type": KeyType.NORMAL,
        "client_reference": "some-ref",  # <--- We'll search for this
    }
    notification = Notification(**data)
    dao_create_notification(notification)

    # We'll search by this reference instead of a phone number
    search_term = "some-ref"

    results_page = dao_get_notifications_by_recipient_or_reference(
        service_id=service.id,
        search_term=search_term,
        notification_type=NotificationType.SMS,
        statuses=[NotificationStatus.FAILED],
        page=1,
        page_size=50,
    )

    # Now we should find exactly one match
    assert len(results_page.items) == 1, "Should find exactly one matching notification"
    found = results_page.items[0]
    assert found.id == notification.id
    assert found.status == NotificationStatus.FAILED
    assert found.client_reference == "some-ref"


@patch("app.dao.notifications_dao.db.session.execute")
def test_dao_get_notification_count_for_service_message_ratio(mock_execute):
    service_id = "service-123"
    current_year = 2025
    expected_recent_count = 10
    expected_old_count = 15

    mock_recent_result = MagicMock()
    mock_recent_result.scalar_one.return_value = expected_recent_count
    mock_old_result = MagicMock()
    mock_old_result.scalar_one.return_value = expected_old_count
    mock_execute.side_effect = [mock_recent_result, mock_old_result]
    result = dao_get_notification_count_for_service_message_ratio(
        service_id, current_year
    )
    assert result == expected_recent_count + expected_old_count
    assert mock_execute.call_count == 2
