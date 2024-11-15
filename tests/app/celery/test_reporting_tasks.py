from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from freezegun import freeze_time
from sqlalchemy import func, select

from app import db
from app.celery.reporting_tasks import (
    create_nightly_billing,
    create_nightly_billing_for_day,
    create_nightly_notification_status,
    create_nightly_notification_status_for_service_and_day,
)
from app.config import QueueNames
from app.dao.fact_billing_dao import get_rate
from app.enums import KeyType, NotificationStatus, NotificationType, TemplateType
from app.models import FactBilling, FactNotificationStatus, Notification
from app.utils import utc_now
from tests.app.db import (
    create_notification,
    create_notification_history,
    create_rate,
    create_service,
    create_template,
)


def mocker_get_rate(
    non_letter_rates, notification_type, local_date, rate_multiplier=None
):
    if notification_type == NotificationType.SMS:
        return Decimal(1.33)
    elif notification_type == NotificationType.EMAIL:
        return Decimal(0)


@freeze_time("2019-08-01T05:30")
@pytest.mark.parametrize(
    "day_start, expected_kwargs",
    [
        (None, [f"2019-07-{31-i}" for i in range(10)]),
        ("2019-07-21", [f"2019-07-{21-i}" for i in range(10)]),
    ],
)
def test_create_nightly_billing_triggers_tasks_for_days(
    notify_api, mocker, day_start, expected_kwargs
):
    mock_celery = mocker.patch(
        "app.celery.reporting_tasks.create_nightly_billing_for_day"
    )
    create_nightly_billing(day_start)

    assert mock_celery.apply_async.call_count == 10
    for i in range(10):
        assert mock_celery.apply_async.call_args_list[i][1]["kwargs"] == {
            "process_day": expected_kwargs[i]
        }


@freeze_time("2019-08-01T00:30")
def test_create_nightly_notification_status_triggers_tasks(
    notify_api,
    sample_service,
    sample_template,
    mocker,
):
    mock_celery = mocker.patch(
        "app.celery.reporting_tasks.create_nightly_notification_status_for_service_and_day"
    ).apply_async

    create_notification(template=sample_template, created_at="2019-07-31")
    create_nightly_notification_status()

    mock_celery.assert_called_with(
        kwargs={
            "service_id": sample_service.id,
            "process_day": "2019-07-31",
            "notification_type": NotificationType.SMS,
        },
        queue=QueueNames.REPORTING,
    )


@freeze_time("2019-08-01T00:30")
@pytest.mark.parametrize(
    "notification_date, expected_types_aggregated",
    [
        ("2019-08-01", set()),
        ("2019-07-31", {NotificationType.EMAIL, NotificationType.SMS}),
        ("2019-07-28", {NotificationType.EMAIL, NotificationType.SMS}),
        ("2019-07-21", set()),
    ],
)
def test_create_nightly_notification_status_triggers_relevant_tasks(
    notify_api,
    sample_service,
    mocker,
    notification_date,
    expected_types_aggregated,
):
    mock_celery = mocker.patch(
        "app.celery.reporting_tasks.create_nightly_notification_status_for_service_and_day"
    ).apply_async

    for notification_type in NotificationType:
        template = create_template(sample_service, template_type=notification_type)
        create_notification(template=template, created_at=notification_date)

    create_nightly_notification_status()

    types = {
        call.kwargs["kwargs"]["notification_type"] for call in mock_celery.mock_calls
    }
    assert types == expected_types_aggregated


def test_create_nightly_billing_for_day_checks_history(
    sample_service, sample_template, mocker
):
    yesterday = datetime.now() - timedelta(days=1)
    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_template,
        status=NotificationStatus.SENDING,
    )

    create_notification_history(
        created_at=yesterday,
        template=sample_template,
        status=NotificationStatus.DELIVERED,
    )

    records = _get_fact_billing_records()
    assert len(records) == 0

    create_nightly_billing_for_day(str(yesterday.date()))
    records = _get_fact_billing_records()
    assert len(records) == 1

    record = records[0]
    assert record.notification_type == NotificationType.SMS
    assert record.notifications_sent == 2


def _get_fact_billing_records():
    stmt = select(FactBilling)
    return db.session.execute(stmt).scalars().all()


@pytest.mark.parametrize(
    "second_rate, records_num, billable_units, multiplier",
    [(1.0, 1, 2, [1]), (2.0, 2, 1, [1, 2])],
)
def test_create_nightly_billing_for_day_sms_rate_multiplier(
    sample_service,
    sample_template,
    mocker,
    second_rate,
    records_num,
    billable_units,
    multiplier,
):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    # These are sms notifications
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        sent_by="sns",
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        sent_by="sns",
        international=False,
        rate_multiplier=second_rate,
        billable_units=1,
    )

    records = _get_fact_billing_records()
    assert len(records) == 0

    create_nightly_billing_for_day(str(yesterday.date()))
    records = (
        db.session.execute(select(FactBilling).order_by("rate_multiplier"))
        .scalars()
        .all()
    )
    assert len(records) == records_num

    for i, record in enumerate(records):
        assert record.local_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == billable_units
        assert record.rate_multiplier == multiplier[i]


def test_create_nightly_billing_for_day_different_templates(
    sample_service, sample_template, sample_email_template, mocker
):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        sent_by="sns",
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_email_template,
        status=NotificationStatus.DELIVERED,
        sent_by="sns",
        international=False,
        rate_multiplier=0,
        billable_units=0,
    )

    records = _get_fact_billing_records()
    assert len(records) == 0
    create_nightly_billing_for_day(str(yesterday.date()))

    records = (
        db.session.execute(select(FactBilling).order_by("rate_multiplier"))
        .scalars()
        .all()
    )
    assert len(records) == 2
    multiplier = [0, 1]
    billable_units = [0, 1]
    rate = [0, Decimal(1.33)]

    for i, record in enumerate(records):
        assert record.local_date == datetime.date(yesterday)
        assert record.rate == rate[i]
        assert record.billable_units == billable_units[i]
        assert record.rate_multiplier == multiplier[i]


def test_create_nightly_billing_for_day_same_sent_by(
    sample_service, sample_template, sample_email_template, mocker
):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    # These are sms notifications
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        sent_by="sns",
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        sent_by="sns",
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = _get_fact_billing_records()
    assert len(records) == 0
    create_nightly_billing_for_day(str(yesterday.date()))

    records = (
        db.session.execute(select(FactBilling).order_by("rate_multiplier"))
        .scalars()
        .all()
    )
    assert len(records) == 1

    for _, record in enumerate(records):
        assert record.local_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == 2
        assert record.rate_multiplier == 1.0


def test_create_nightly_billing_for_day_null_sent_by_sms(
    sample_service, sample_template, mocker
):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = _get_fact_billing_records()
    assert len(records) == 0

    create_nightly_billing_for_day(str(yesterday.date()))
    records = _get_fact_billing_records()
    assert len(records) == 1

    record = records[0]
    assert record.local_date == datetime.date(yesterday)
    assert record.rate == Decimal(1.33)
    assert record.billable_units == 1
    assert record.rate_multiplier == 1
    assert record.provider == "unknown"


def test_get_rate_for_sms_and_email(notify_db_session):
    non_letter_rates = [
        create_rate(datetime(2017, 12, 1), 0.15, NotificationType.SMS),
        create_rate(datetime(2017, 12, 1), 0, NotificationType.EMAIL),
    ]

    rate = get_rate(non_letter_rates, NotificationType.SMS, date(2018, 1, 1))
    assert rate == Decimal(0.15)

    rate = get_rate(non_letter_rates, NotificationType.EMAIL, date(2018, 1, 1))
    assert rate == Decimal(0)


@freeze_time("2018-03-26T04:30:00")
# summer time starts on 2018-03-25
def test_create_nightly_billing_for_day_use_BST(
    sample_service, sample_template, mocker
):
    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    # too late
    create_notification(
        created_at=datetime(2018, 3, 26, 4, 1),
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        rate_multiplier=1.0,
        billable_units=1,
    )

    create_notification(
        created_at=datetime(2018, 3, 25, 23, 59),
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        rate_multiplier=1.0,
        billable_units=2,
    )

    # too early
    create_notification(
        created_at=datetime(2018, 3, 24, 23, 59),
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        rate_multiplier=1.0,
        billable_units=4,
    )
    stmt = select(func.count()).select_from(Notification)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 3
    stmt = select(func.count()).select_from(FactBilling)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 0

    create_nightly_billing_for_day("2018-03-25")
    records = (
        db.session.execute(select(FactBilling).order_by(FactBilling.local_date))
        .scalars()
        .all()
    )

    assert len(records) == 1
    assert records[0].local_date == date(2018, 3, 25)
    assert records[0].billable_units == 2


@freeze_time("2018-01-15T08:30:00")
def test_create_nightly_billing_for_day_update_when_record_exists(
    sample_service, sample_template, mocker
):
    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=datetime.now() - timedelta(days=1),
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = _get_fact_billing_records()
    assert len(records) == 0

    create_nightly_billing_for_day("2018-01-14")
    records = (
        db.session.execute(select(FactBilling).order_by(FactBilling.local_date))
        .scalars()
        .all()
    )

    assert len(records) == 1
    assert records[0].local_date == date(2018, 1, 14)
    assert records[0].billable_units == 1
    assert not records[0].updated_at

    create_notification(
        created_at=datetime.now() - timedelta(days=1),
        template=sample_template,
        status=NotificationStatus.DELIVERED,
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    # run again, make sure create_nightly_billing() updates with no error
    create_nightly_billing_for_day("2018-01-14")
    assert len(records) == 1
    assert records[0].billable_units == 2
    assert records[0].updated_at


def test_create_nightly_notification_status_for_service_and_day(notify_db_session):
    first_service = create_service(service_name="First Service")
    first_template = create_template(service=first_service)
    second_service = create_service(service_name="second Service")
    second_template = create_template(
        service=second_service,
        template_type=TemplateType.EMAIL,
    )

    process_day = utc_now().date() - timedelta(days=5)
    with freeze_time(datetime.combine(process_day, time.max)):
        create_notification(
            template=first_template,
            status=NotificationStatus.DELIVERED,
        )
        create_notification(template=second_template, status=NotificationStatus.FAILED)

        # team API key notifications are included
        create_notification(
            template=second_template,
            status=NotificationStatus.SENDING,
            key_type=KeyType.TEAM,
        )

        # test notifications are ignored
        create_notification(
            template=second_template,
            status=NotificationStatus.SENDING,
            key_type=KeyType.TEST,
        )

        # historical notifications are included
        create_notification_history(
            template=second_template,
            status=NotificationStatus.DELIVERED,
        )

    # these created notifications from a different day get ignored
    with freeze_time(datetime.combine(utc_now().date() - timedelta(days=4), time.max)):
        create_notification(template=first_template)
        create_notification_history(template=second_template)

    assert len(db.session.execute(select(FactNotificationStatus)).scalars().all()) == 0

    create_nightly_notification_status_for_service_and_day(
        str(process_day),
        first_service.id,
        NotificationType.SMS,
    )
    create_nightly_notification_status_for_service_and_day(
        str(process_day),
        second_service.id,
        NotificationType.EMAIL,
    )

    new_fact_data = (
        db.session.execute(
            select(FactNotificationStatus).order_by(
                FactNotificationStatus.notification_type,
                FactNotificationStatus.notification_status,
            )
        )
        .scalars()
        .all()
    )

    assert len(new_fact_data) == 4

    email_delivered = (NotificationType.EMAIL, NotificationStatus.DELIVERED)
    email_sending = (NotificationType.EMAIL, NotificationStatus.SENDING)
    email_failure = (NotificationType.EMAIL, NotificationStatus.FAILED)
    sms_delivered = (NotificationType.SMS, NotificationStatus.DELIVERED)

    for row in new_fact_data:
        current = (row.notification_type, row.notification_status)
        if current == email_delivered:
            assert row.template_id == second_template.id
            assert row.service_id == second_service.id
            assert row.notification_type == NotificationType.EMAIL
            assert row.notification_status == NotificationStatus.DELIVERED
            assert row.notification_count == 1
            assert row.key_type == KeyType.NORMAL
        elif current == email_failure:
            assert row.template_id == second_template.id
            assert row.service_id == second_service.id
            assert row.notification_type == NotificationType.EMAIL
            assert row.notification_status == NotificationStatus.FAILED
            assert row.notification_count == 1
            assert row.key_type == KeyType.NORMAL
        elif current == email_sending:
            assert row.local_date == process_day
            assert row.template_id == second_template.id
            assert row.service_id == second_service.id
            assert row.job_id == UUID("00000000-0000-0000-0000-000000000000")
            assert row.notification_type == NotificationType.EMAIL
            assert row.notification_status == NotificationStatus.SENDING
            assert row.notification_count == 1
            assert row.key_type == KeyType.TEAM
        elif current == sms_delivered:
            assert row.template_id == first_template.id
            assert row.service_id == first_service.id
            assert row.notification_type == NotificationType.SMS
            assert row.notification_status == NotificationStatus.DELIVERED
            assert row.notification_count == 1
            assert row.key_type == KeyType.NORMAL


def test_create_nightly_notification_status_for_service_and_day_overwrites_old_data(
    notify_db_session,
):
    first_service = create_service(service_name="First Service")
    first_template = create_template(service=first_service)
    process_day = utc_now().date()

    # first run: one notification, expect one row (just one status)
    notification = create_notification(
        template=first_template, status=NotificationStatus.SENDING
    )
    create_nightly_notification_status_for_service_and_day(
        str(process_day),
        first_service.id,
        NotificationType.SMS,
    )

    new_fact_data = db.session.execute(select(FactNotificationStatus)).scalars().all()

    assert len(new_fact_data) == 1
    assert new_fact_data[0].notification_count == 1
    assert new_fact_data[0].notification_status == NotificationStatus.SENDING

    # second run: status changed, still expect one row (one status)
    notification.status = NotificationStatus.DELIVERED
    create_notification(template=first_template, status=NotificationStatus.CREATED)
    create_nightly_notification_status_for_service_and_day(
        str(process_day),
        first_service.id,
        NotificationType.SMS,
    )

    updated_fact_data = (
        db.session.execute(
            select(FactNotificationStatus).order_by(
                FactNotificationStatus.notification_status
            )
        )
        .scalars()
        .all()
    )

    assert len(updated_fact_data) == 2
    assert updated_fact_data[0].notification_count == 1
    assert updated_fact_data[0].notification_status == NotificationStatus.CREATED
    assert updated_fact_data[1].notification_count == 1
    assert updated_fact_data[1].notification_status == NotificationStatus.DELIVERED


# the job runs at 04:30am EST time.
@freeze_time("2019-04-02T04:30")
def test_create_nightly_notification_status_for_service_and_day_respects_bst(
    sample_template,
):
    create_notification(
        sample_template,
        status=NotificationStatus.DELIVERED,
        created_at=datetime(2019, 4, 2, 5, 0),
    )  # too new

    create_notification(
        sample_template,
        status=NotificationStatus.CREATED,
        created_at=datetime(2019, 4, 2, 5, 59),
    )
    create_notification(
        sample_template,
        status=NotificationStatus.CREATED,
        created_at=datetime(2019, 4, 1, 4, 0),
    )

    create_notification(
        sample_template,
        status=NotificationStatus.DELIVERED,
        created_at=datetime(2019, 3, 21, 17, 59),
    )  # too old

    create_nightly_notification_status_for_service_and_day(
        "2019-04-01",
        sample_template.service_id,
        NotificationType.SMS,
    )

    noti_status = (
        db.session.execute(
            select(FactNotificationStatus).order_by(FactNotificationStatus.local_date)
        )
        .scalars()
        .all()
    )
    assert len(noti_status) == 1

    assert noti_status[0].local_date == date(2019, 4, 1)
    assert noti_status[0].notification_status == NotificationStatus.CREATED
