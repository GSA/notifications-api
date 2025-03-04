from datetime import date, datetime, timedelta
from uuid import UUID

import pytest
from freezegun import freeze_time
from sqlalchemy import func, select

from app import db
from app.dao.fact_notification_status_dao import (
    fetch_monthly_notification_statuses_per_service,
    fetch_monthly_template_usage_for_service,
    fetch_notification_status_for_service_by_month,
    fetch_notification_status_for_service_for_day,
    fetch_notification_status_for_service_for_today_and_7_previous_days,
    fetch_notification_status_totals_for_all_services,
    fetch_notification_statuses_for_job,
    fetch_stats_for_all_services_by_date_range,
    get_total_notifications_for_date_range,
    update_fact_notification_status,
)
from app.enums import KeyType, NotificationStatus, NotificationType, TemplateType
from app.models import FactNotificationStatus
from app.utils import utc_now
from tests.app.db import (
    create_ft_notification_status,
    create_job,
    create_notification,
    create_service,
    create_template,
    create_template_folder,
)


def test_fetch_notification_status_for_service_by_month(notify_db_session):
    service_1 = create_service(service_name="service_1")
    service_2 = create_service(service_name="service_2")

    create_template(service=service_1)
    # not the service being tested
    create_template(service=service_2)

    # loop messages for the month
    for x in range(0, 14):
        create_notification(
            service_1.templates[0],
            created_at=datetime(2018, 1, 1, 1, x, 0),
            status=NotificationStatus.DELIVERED,
        )
    create_notification(
        service_1.templates[0], created_at=datetime(2018, 1, 1, 1, 1, 0)
    )

    create_notification(
        service_1.templates[0],
        created_at=datetime(2018, 2, 1, 1, 1, 0),
        status=NotificationStatus.DELIVERED,
    )

    # not the right month
    create_notification(
        service_1.templates[0],
        created_at=datetime(2018, 4, 1, 1, 1, 0),
        status=NotificationStatus.DELIVERED,
    )

    # not the right service
    create_notification(
        service_2.templates[0],
        created_at=datetime(2018, 2, 1, 1, 1, 0),
        status=NotificationStatus.DELIVERED,
    )

    results = sorted(
        fetch_notification_status_for_service_by_month(
            date(2018, 1, 1), date(2018, 2, 28), service_1.id
        ),
        key=lambda x: (x.month, x.notification_status),
    )

    assert len(results) == 3

    assert results[0].month.date() == date(2018, 1, 1)
    assert results[0].notification_type == NotificationType.SMS
    assert results[0].notification_status == NotificationStatus.CREATED
    assert results[0].count == 1

    assert results[1].month.date() == date(2018, 1, 1)
    assert results[1].notification_type == NotificationType.SMS
    assert results[1].notification_status == NotificationStatus.DELIVERED
    assert results[1].count == 14

    assert results[2].month.date() == date(2018, 2, 1)
    assert results[2].notification_type == NotificationType.SMS
    assert results[2].notification_status == NotificationStatus.DELIVERED
    assert results[2].count == 1


def test_fetch_notification_status_for_service_for_day(notify_db_session):
    service_1 = create_service(service_name="service_1")
    service_2 = create_service(service_name="service_2")

    create_template(service=service_1)
    create_template(service=service_2)

    # too early
    create_notification(
        service_1.templates[0], created_at=datetime(2018, 5, 31, 22, 59, 0)
    )

    # included
    create_notification(
        service_1.templates[0], created_at=datetime(2018, 5, 31, 23, 0, 0)
    )
    create_notification(
        service_1.templates[0], created_at=datetime(2018, 6, 1, 22, 59, 0)
    )
    create_notification(
        service_1.templates[0],
        created_at=datetime(2018, 6, 1, 12, 0, 0),
        key_type=KeyType.TEAM,
    )
    create_notification(
        service_1.templates[0],
        created_at=datetime(2018, 6, 1, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )

    # test key
    create_notification(
        service_1.templates[0],
        created_at=datetime(2018, 6, 1, 12, 0, 0),
        key_type=KeyType.TEST,
    )

    # wrong service
    create_notification(
        service_2.templates[0], created_at=datetime(2018, 6, 1, 12, 0, 0)
    )

    # tomorrow (somehow)
    create_notification(
        service_1.templates[0], created_at=datetime(2018, 6, 1, 23, 0, 0)
    )

    results = sorted(
        fetch_notification_status_for_service_for_day(
            datetime(2018, 6, 1), service_1.id
        ),
        key=lambda x: x.notification_status,
    )
    assert len(results) == 2

    assert results[0].month == datetime(2018, 6, 1, 0, 0)
    assert results[0].notification_type == NotificationType.SMS
    assert results[0].notification_status == NotificationStatus.CREATED
    assert results[0].count == 3

    assert results[1].month == datetime(2018, 6, 1, 0, 0)
    assert results[1].notification_type == NotificationType.SMS
    assert results[1].notification_status == NotificationStatus.DELIVERED
    assert results[1].count == 1


@freeze_time("2018-10-31T18:00:00")
def test_fetch_notification_status_for_service_for_today_and_7_previous_days(
    notify_db_session,
):
    service_1 = create_service(service_name="service_1")
    sms_template = create_template(service=service_1, template_type=TemplateType.SMS)
    sms_template_2 = create_template(service=service_1, template_type=TemplateType.SMS)
    email_template = create_template(
        service=service_1, template_type=TemplateType.EMAIL
    )

    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.SMS,
        service_1,
        count=10,
    )
    create_ft_notification_status(
        date(2018, 10, 25),
        NotificationType.SMS,
        service_1,
        count=8,
    )
    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.SMS,
        service_1,
        notification_status=NotificationStatus.CREATED,
    )
    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.EMAIL,
        service_1,
        count=3,
    )

    create_notification(sms_template, created_at=datetime(2018, 10, 31, 11, 0, 0))
    create_notification(sms_template_2, created_at=datetime(2018, 10, 31, 11, 0, 0))
    create_notification(
        sms_template,
        created_at=datetime(2018, 10, 31, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        email_template,
        created_at=datetime(2018, 10, 31, 13, 0, 0),
        status=NotificationStatus.DELIVERED,
    )

    # too early, shouldn't be included
    create_notification(
        service_1.templates[0],
        created_at=datetime(2018, 10, 30, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )

    results = sorted(
        fetch_notification_status_for_service_for_today_and_7_previous_days(
            service_1.id
        ),
        key=lambda x: (x.notification_type, x.status),
    )

    assert len(results) == 3

    assert results[0].notification_type == NotificationType.EMAIL
    assert results[0].status == NotificationStatus.DELIVERED
    assert results[0].count == 4

    assert results[1].notification_type == NotificationType.SMS
    assert results[1].status == NotificationStatus.CREATED
    assert results[1].count == 3

    assert results[2].notification_type == NotificationType.SMS
    assert results[2].status == NotificationStatus.DELIVERED
    assert results[2].count == 19


@freeze_time("2018-10-31T18:00:00")
def test_fetch_notification_status_by_template_for_service_for_today_and_7_previous_days(
    notify_db_session,
):
    service_1 = create_service(service_name="service_1")
    test_folder = create_template_folder(service=service_1, name="Test_Folder_For_This")
    sms_template = create_template(
        template_name="sms Template 1",
        service=service_1,
        template_type=TemplateType.SMS,
        folder=test_folder,
    )
    sms_template_2 = create_template(
        template_name="sms Template 2",
        service=service_1,
        template_type=TemplateType.SMS,
        folder=test_folder,
    )
    email_template = create_template(
        service=service_1, template_type=TemplateType.EMAIL
    )

    # create unused email template
    create_template(service=service_1, template_type=TemplateType.EMAIL)

    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.SMS,
        service_1,
        count=10,
    )
    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.SMS,
        service_1,
        count=11,
    )
    create_ft_notification_status(
        date(2018, 10, 25),
        NotificationType.SMS,
        service_1,
        count=8,
    )
    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.SMS,
        service_1,
        notification_status=NotificationStatus.CREATED,
    )
    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.EMAIL,
        service_1,
        count=3,
    )

    create_notification(sms_template, created_at=datetime(2018, 10, 31, 11, 0, 0))
    create_notification(
        sms_template,
        created_at=datetime(2018, 10, 31, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sms_template_2,
        created_at=datetime(2018, 10, 31, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        email_template,
        created_at=datetime(2018, 10, 31, 13, 0, 0),
        status=NotificationStatus.DELIVERED,
    )

    # too early, shouldn't be included
    create_notification(
        service_1.templates[0],
        created_at=datetime(2018, 10, 30, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )

    results = fetch_notification_status_for_service_for_today_and_7_previous_days(
        service_1.id,
        by_template=True,
    )

    expected = [
        {
            "folder": None,
            "template_name": "email Template Name",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 31, 0, 0),
            "notification_type": NotificationType.EMAIL,
            "status": NotificationStatus.DELIVERED,
            "count": 1,
        },
        {
            "folder": None,
            "template_name": "email Template Name",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 29, 0, 0),
            "notification_type": NotificationType.EMAIL,
            "status": NotificationStatus.DELIVERED,
            "count": 3,
        },
        {
            "folder": None,
            "template_name": "sms Template Name",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 29, 0, 0),
            "notification_type": NotificationType.SMS,
            "status": NotificationStatus.CREATED,
            "count": 1,
        },
        {
            "folder": "Test_Folder_For_This",
            "template_name": "sms Template 1",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 31, 0, 0),
            "notification_type": NotificationType.SMS,
            "status": NotificationStatus.CREATED,
            "count": 1,
        },
        {
            "folder": None,
            "template_name": "sms Template Name",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 29, 0, 0),
            "notification_type": NotificationType.SMS,
            "status": NotificationStatus.DELIVERED,
            "count": 10,
        },
        {
            "folder": "Test_Folder_For_This",
            "template_name": "sms Template 2",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 31, 0, 0),
            "notification_type": NotificationType.SMS,
            "status": NotificationStatus.DELIVERED,
            "count": 1,
        },
        {
            "folder": None,
            "template_name": "sms Template Name",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 25, 0, 0),
            "notification_type": NotificationType.SMS,
            "status": NotificationStatus.DELIVERED,
            "count": 8,
        },
        {
            "folder": "Test_Folder_For_This",
            "template_name": "sms Template 1",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 31, 0, 0),
            "notification_type": NotificationType.SMS,
            "status": NotificationStatus.DELIVERED,
            "count": 1,
        },
        {
            "folder": None,
            "template_name": "sms Template Name",
            "_no_label": False,
            "created_by": "Test User",
            "last_used": datetime(2018, 10, 29, 0, 0),
            "notification_type": NotificationType.SMS,
            "status": NotificationStatus.DELIVERED,
            "count": 11,
        },
    ]

    expected = [
        [
            str(row[k]) if k != "last_used" else row[k].strftime("%Y-%m-%d")
            for k in (
                "folder",
                "template_name",
                "created_by",
                "last_used",
                "notification_type",
                "status",
                "count",
            )
        ]
        for row in sorted(
            expected,
            key=lambda x: (
                str(x["notification_type"]),
                str(x["status"]),
                x["folder"] if x["folder"] is not None else "",
                x["template_name"],
                x["count"],
                x["last_used"],
            ),
        )
    ]

    results = [
        [
            str(row[k]) if k != "last_used" else row[k].strftime("%Y-%m-%d")
            for k in (
                "folder",
                "template_name",
                "created_by",
                "last_used",
                "notification_type",
                "status",
                "count",
            )
        ]
        for row in sorted(
            results,
            key=lambda x: (
                x.notification_type,
                x.status,
                x.folder if x.folder is not None else "",
                x.template_name,
                x.count,
                x.last_used,
            ),
        )
    ]

    assert expected == results


@pytest.mark.parametrize(
    "start_date, end_date, expected_email, expected_sms, expected_created_sms",
    [
        (29, 30, 3, 10, 1),  # not including today
        (29, 31, 4, 11, 2),  # today included
        (26, 31, 4, 11, 2),
    ],
)
@freeze_time("2018-10-31 14:00")
def test_fetch_notification_status_totals_for_all_services(
    notify_db_session,
    start_date,
    end_date,
    expected_email,
    expected_sms,
    expected_created_sms,
):
    set_up_data()

    results = sorted(
        fetch_notification_status_totals_for_all_services(
            start_date=date(2018, 10, start_date), end_date=date(2018, 10, end_date)
        ),
        key=lambda x: (x.notification_type, x.status),
    )

    assert len(results) == 3

    assert results[0].notification_type == NotificationType.EMAIL
    assert results[0].status == NotificationStatus.DELIVERED
    assert results[0].count == expected_email

    assert results[1].notification_type == NotificationType.SMS
    assert results[1].status == NotificationStatus.CREATED
    assert results[1].count == expected_created_sms

    assert results[2].notification_type == NotificationType.SMS
    assert results[2].status == NotificationStatus.DELIVERED
    assert results[2].count == expected_sms


@freeze_time("2018-04-21 14:00")
def test_fetch_notification_status_totals_for_all_services_works_in_est(
    notify_db_session,
):
    service_1 = create_service(service_name="service_1")
    sms_template = create_template(service=service_1, template_type=TemplateType.SMS)
    email_template = create_template(
        service=service_1, template_type=TemplateType.EMAIL
    )

    create_notification(
        sms_template,
        created_at=datetime(2018, 4, 20, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sms_template,
        created_at=datetime(2018, 4, 21, 11, 0, 0),
        status=NotificationStatus.CREATED,
    )
    create_notification(
        sms_template,
        created_at=datetime(2018, 4, 21, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        email_template,
        created_at=datetime(2018, 4, 21, 13, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        email_template,
        created_at=datetime(2018, 4, 21, 14, 0, 0),
        status=NotificationStatus.DELIVERED,
    )

    results = sorted(
        fetch_notification_status_totals_for_all_services(
            start_date=date(2018, 4, 21), end_date=date(2018, 4, 21)
        ),
        key=lambda x: (x.notification_type, x.status),
    )

    assert len(results) == 3

    assert results[0].notification_type == NotificationType.EMAIL
    assert results[0].status == NotificationStatus.DELIVERED
    assert results[0].count == 2

    assert results[1].notification_type == NotificationType.SMS
    assert results[1].status == NotificationStatus.CREATED
    assert results[1].count == 1

    assert results[2].notification_type == NotificationType.SMS
    assert results[2].status == NotificationStatus.DELIVERED
    assert results[2].count == 1


def set_up_data():
    service_2 = create_service(service_name="service_2")
    service_1 = create_service(service_name="service_1")
    sms_template = create_template(service=service_1, template_type=TemplateType.SMS)
    email_template = create_template(
        service=service_1, template_type=TemplateType.EMAIL
    )
    create_ft_notification_status(
        date(2018, 10, 24),
        NotificationType.SMS,
        service_1,
        count=8,
    )
    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.SMS,
        service_1,
        count=10,
    )
    create_ft_notification_status(
        date(2018, 10, 29),
        NotificationType.SMS,
        service_1,
        notification_status=NotificationStatus.CREATED,
    )
    create_ft_notification_status(
        date(2018, 10, 29), NotificationType.EMAIL, service_1, count=3
    )

    create_notification(
        service_1.templates[0],
        created_at=datetime(2018, 10, 30, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(sms_template, created_at=datetime(2018, 10, 31, 11, 0, 0))
    create_notification(
        sms_template,
        created_at=datetime(2018, 10, 31, 12, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        email_template,
        created_at=datetime(2018, 10, 31, 13, 0, 0),
        status=NotificationStatus.DELIVERED,
    )
    return service_1, service_2


def test_fetch_notification_statuses_for_job(sample_template):
    j1 = create_job(sample_template)
    j2 = create_job(sample_template)

    create_ft_notification_status(
        date(2018, 10, 1),
        job=j1,
        notification_status=NotificationStatus.CREATED,
        count=1,
    )
    create_ft_notification_status(
        date(2018, 10, 1),
        job=j1,
        notification_status=NotificationStatus.DELIVERED,
        count=2,
    )
    create_ft_notification_status(
        date(2018, 10, 2),
        job=j1,
        notification_status=NotificationStatus.CREATED,
        count=4,
    )
    create_ft_notification_status(
        date(2018, 10, 1),
        job=j2,
        notification_status=NotificationStatus.CREATED,
        count=8,
    )

    assert {x.status: x.count for x in fetch_notification_statuses_for_job(j1.id)} == {
        NotificationStatus.CREATED: 5,
        NotificationStatus.DELIVERED: 2,
    }


@freeze_time("2018-10-31 14:00")
def test_fetch_stats_for_all_services_by_date_range(notify_db_session):
    service_1, service_2 = set_up_data()
    results = fetch_stats_for_all_services_by_date_range(
        start_date=date(2018, 10, 29), end_date=date(2018, 10, 31)
    )
    assert len(results) == 4

    assert results[0].service_id == service_1.id
    assert results[0].notification_type == NotificationType.EMAIL
    assert results[0].status == NotificationStatus.DELIVERED
    assert results[0].count == 4

    assert results[1].service_id == service_1.id
    assert results[1].notification_type == NotificationType.SMS
    assert results[1].status == NotificationStatus.CREATED
    assert results[1].count == 2

    assert results[2].service_id == service_1.id
    assert results[2].notification_type == NotificationType.SMS
    assert results[2].status == NotificationStatus.DELIVERED
    assert results[2].count == 11

    assert results[3].service_id == service_2.id
    assert not results[3].notification_type
    assert not results[3].status
    assert not results[3].count


@freeze_time("2018-03-30 14:00")
def test_fetch_monthly_template_usage_for_service(sample_service):
    template_one = create_template(
        service=sample_service,
        template_type=TemplateType.SMS,
        template_name="a",
    )
    template_two = create_template(
        service=sample_service,
        template_type=TemplateType.EMAIL,
        template_name="b",
    )

    create_ft_notification_status(
        local_date=date(2017, 12, 10),
        service=sample_service,
        template=template_two,
        count=3,
    )
    create_ft_notification_status(
        local_date=date(2017, 12, 10),
        service=sample_service,
        template=template_one,
        count=6,
    )

    create_ft_notification_status(
        local_date=date(2018, 1, 1),
        service=sample_service,
        template=template_one,
        count=4,
    )

    create_ft_notification_status(
        local_date=date(2018, 3, 1),
        service=sample_service,
        template=template_two,
        count=5,
    )
    create_notification(template=template_two, created_at=utc_now() - timedelta(days=1))
    create_notification(template=template_two, created_at=utc_now())
    results = fetch_monthly_template_usage_for_service(
        datetime(2017, 4, 1), datetime(2018, 3, 31), sample_service.id
    )

    assert len(results) == 4

    assert results[0].template_id == template_one.id
    assert results[0].name == template_one.name
    assert results[0].template_type == template_one.template_type
    assert results[0].month == 12
    assert results[0].year == 2017
    assert results[0].count == 6
    assert results[1].template_id == template_two.id
    assert results[1].name == template_two.name
    assert results[1].template_type == template_two.template_type
    assert results[1].month == 12
    assert results[1].year == 2017
    assert results[1].count == 3

    assert results[2].template_id == template_one.id
    assert results[2].name == template_one.name
    assert results[2].template_type == template_one.template_type
    assert results[2].month == 1
    assert results[2].year == 2018
    assert results[2].count == 4

    assert results[3].template_id == template_two.id
    assert results[3].name == template_two.name
    assert results[3].template_type == template_two.template_type
    assert results[3].month == 3
    assert results[3].year == 2018
    assert results[3].count == 6


@freeze_time("2018-03-30 14:00")
def test_fetch_monthly_template_usage_for_service_does_join_to_notifications_if_today_is_not_in_date_range(
    sample_service,
):
    template_one = create_template(
        service=sample_service,
        template_type=TemplateType.SMS,
        template_name="a",
    )
    template_two = create_template(
        service=sample_service,
        template_type=TemplateType.EMAIL,
        template_name="b",
    )
    create_ft_notification_status(
        local_date=date(2018, 2, 1),
        service=template_two.service,
        template=template_two,
        count=15,
    )
    create_ft_notification_status(
        local_date=date(2018, 2, 2),
        service=template_one.service,
        template=template_one,
        count=20,
    )
    create_ft_notification_status(
        local_date=date(2018, 3, 1),
        service=template_one.service,
        template=template_one,
        count=3,
    )
    create_notification(template=template_one, created_at=utc_now())
    results = fetch_monthly_template_usage_for_service(
        datetime(2018, 1, 1), datetime(2018, 2, 20), template_one.service_id
    )

    assert len(results) == 2

    assert results[0].template_id == template_one.id
    assert results[0].name == template_one.name
    assert results[0].template_type == template_one.template_type
    assert results[0].month == 2
    assert results[0].year == 2018
    assert results[0].count == 20
    assert results[1].template_id == template_two.id
    assert results[1].name == template_two.name
    assert results[1].template_type == template_two.template_type
    assert results[1].month == 2
    assert results[1].year == 2018
    assert results[1].count == 15


@freeze_time("2018-03-30 14:00")
def test_fetch_monthly_template_usage_for_service_does_not_include_cancelled_status(
    sample_template,
):
    create_ft_notification_status(
        local_date=date(2018, 3, 1),
        service=sample_template.service,
        template=sample_template,
        notification_status=NotificationStatus.CANCELLED,
        count=15,
    )
    create_notification(
        template=sample_template,
        created_at=utc_now(),
        status=NotificationStatus.CANCELLED,
    )
    results = fetch_monthly_template_usage_for_service(
        datetime(2018, 1, 1), datetime(2018, 3, 31), sample_template.service_id
    )

    assert len(results) == 0


@freeze_time("2018-03-30 14:00")
def test_fetch_monthly_template_usage_for_service_does_not_include_test_notifications(
    sample_template,
):
    create_ft_notification_status(
        local_date=date(2018, 3, 1),
        service=sample_template.service,
        template=sample_template,
        notification_status=NotificationStatus.DELIVERED,
        key_type=KeyType.TEST,
        count=15,
    )
    create_notification(
        template=sample_template,
        created_at=utc_now(),
        status=NotificationStatus.DELIVERED,
        key_type=KeyType.TEST,
    )
    results = fetch_monthly_template_usage_for_service(
        datetime(2018, 1, 1),
        datetime(2018, 3, 31),
        sample_template.service_id,
    )

    assert len(results) == 0


@freeze_time("2019-05-10 14:00")
def test_fetch_monthly_notification_statuses_per_service(notify_db_session):
    service_one = create_service(
        service_name="service one",
        service_id=UUID("e4e34c4e-73c1-4802-811c-3dd273f21da4"),
    )
    service_two = create_service(
        service_name="service two",
        service_id=UUID("b19d7aad-6f09-4198-8b62-f6cf126b87e5"),
    )

    create_ft_notification_status(
        date(2019, 4, 30),
        notification_type=NotificationType.SMS,
        service=service_one,
        notification_status=NotificationStatus.DELIVERED,
    )
    create_ft_notification_status(
        date(2019, 3, 1),
        notification_type=NotificationType.EMAIL,
        service=service_one,
        notification_status=NotificationStatus.SENDING,
        count=4,
    )
    create_ft_notification_status(
        date(2019, 3, 1),
        notification_type=NotificationType.EMAIL,
        service=service_one,
        notification_status=NotificationStatus.PENDING,
        count=1,
    )
    create_ft_notification_status(
        date(2019, 3, 2),
        notification_type=NotificationType.EMAIL,
        service=service_one,
        notification_status=NotificationStatus.TECHNICAL_FAILURE,
        count=2,
    )
    create_ft_notification_status(
        date(2019, 3, 7),
        notification_type=NotificationType.EMAIL,
        service=service_one,
        notification_status=NotificationStatus.FAILED,
        count=1,
    )
    create_ft_notification_status(
        date(2019, 3, 10),
        notification_type=NotificationType.SMS,
        service=service_two,
        notification_status=NotificationStatus.PERMANENT_FAILURE,
        count=1,
    )
    create_ft_notification_status(
        date(2019, 3, 10),
        notification_type=NotificationType.SMS,
        service=service_two,
        notification_status=NotificationStatus.PERMANENT_FAILURE,
        count=1,
    )
    create_ft_notification_status(
        date(2019, 3, 13),
        notification_type=NotificationType.SMS,
        service=service_one,
        notification_status=NotificationStatus.SENT,
        count=1,
    )
    create_ft_notification_status(
        date(2019, 4, 1),
        notification_type=NotificationType.SMS,
        service=service_two,
        notification_status=NotificationStatus.TEMPORARY_FAILURE,
        count=10,
    )
    create_ft_notification_status(
        date(2019, 3, 31),
        notification_type=NotificationType.SMS,
        service=service_one,
        notification_status=NotificationStatus.DELIVERED,
    )

    results = fetch_monthly_notification_statuses_per_service(
        date(2019, 3, 1), date(2019, 4, 30)
    )

    assert len(results) == 5
    # column order: date, service_id, service_name, notifaction_type, count_sending, count_delivered,
    # count_technical_failure, count_temporary_failure, count_permanent_failure, count_sent
    expected = [
        [
            date(2019, 3, 1),
            service_two.id,
            "service two",
            NotificationType.SMS,
            0,
            0,
            0,
            0,
            2,
            0,
        ],
        [
            date(2019, 3, 1),
            service_one.id,
            "service one",
            NotificationType.EMAIL,
            5,
            0,
            3,
            0,
            0,
            0,
        ],
        [
            date(2019, 3, 1),
            service_one.id,
            "service one",
            NotificationType.SMS,
            0,
            1,
            0,
            0,
            0,
            1,
        ],
        [
            date(2019, 4, 1),
            service_two.id,
            "service two",
            NotificationType.SMS,
            0,
            0,
            0,
            10,
            0,
            0,
        ],
        [
            date(2019, 4, 1),
            service_one.id,
            "service one",
            NotificationType.SMS,
            0,
            1,
            0,
            0,
            0,
            0,
        ],
    ]

    for row in results:
        assert [x for x in row] in expected


@freeze_time("2019-04-10 14:00")
def test_fetch_monthly_notification_statuses_per_service_for_rows_that_should_be_excluded(
    notify_db_session,
):
    valid_service = create_service(service_name="valid service")
    inactive_service = create_service(service_name="inactive", active=False)
    restricted_service = create_service(service_name="restricted", restricted=True)

    # notification in 'created' state
    create_ft_notification_status(
        date(2019, 3, 15),
        service=valid_service,
        notification_status=NotificationStatus.CREATED,
    )
    # notification created by inactive service
    create_ft_notification_status(date(2019, 3, 15), service=inactive_service)
    # notification created with test key
    create_ft_notification_status(
        date(2019, 3, 12), service=valid_service, key_type=KeyType.TEST
    )
    # notification created by trial mode service
    create_ft_notification_status(date(2019, 3, 19), service=restricted_service)
    # notifications outside date range
    create_ft_notification_status(date(2019, 2, 28), service=valid_service)
    create_ft_notification_status(date(2019, 4, 1), service=valid_service)

    results = fetch_monthly_notification_statuses_per_service(
        date(2019, 3, 1), date(2019, 3, 31)
    )
    assert len(results) == 0


def test_get_total_notifications_for_date_range(sample_service):
    template_sms = create_template(
        service=sample_service,
        template_type=TemplateType.SMS,
        template_name="a",
    )
    template_email = create_template(
        service=sample_service,
        template_type=TemplateType.EMAIL,
        template_name="b",
    )
    create_ft_notification_status(
        local_date=date(2021, 2, 28),
        service=template_email.service,
        template=template_email,
        count=15,
    )
    create_ft_notification_status(
        local_date=date(2021, 2, 28),
        service=template_sms.service,
        template=template_sms,
        count=20,
    )

    create_ft_notification_status(
        local_date=date(2021, 3, 1),
        service=template_email.service,
        template=template_email,
        count=15,
    )
    create_ft_notification_status(
        local_date=date(2021, 3, 1),
        service=template_sms.service,
        template=template_sms,
        count=20,
    )

    results = get_total_notifications_for_date_range(
        start_date=datetime(2021, 3, 1), end_date=datetime(2021, 3, 1)
    )

    assert len(results) == 1
    assert results[0] == (date.fromisoformat("2021-03-01"), 15, 20)


@pytest.mark.skip(reason="Need a better way to test variable DST date")
@freeze_time("2022-03-31T18:00:00")
@pytest.mark.parametrize(
    "created_at_utc,process_day,expected_count",
    [
        # Clocks change on the 27th of March 2022, so the query needs to look at the
        # time range 00:00 - 23:00 (UTC) thereafter.
        ("2022-03-27T00:30", date(2022, 3, 27), 1),  # 27/03 00:30 GMT
        ("2022-03-27T22:30", date(2022, 3, 27), 1),  # 27/03 23:30 BST
        ("2022-03-27T23:30", date(2022, 3, 27), 0),  # 28/03 00:30 BST
        ("2022-03-26T23:30", date(2022, 3, 26), 1),  # 26/03 23:30 GMT
    ],
)
def test_update_fact_notification_status_respects_gmt_bst(
    sample_template,
    sample_service,
    created_at_utc,
    process_day,
    expected_count,
):
    create_notification(template=sample_template, created_at=created_at_utc)
    update_fact_notification_status(
        process_day, NotificationType.SMS, sample_service.id
    )

    stmt = (
        select(func.count())
        .select_from(FactNotificationStatus)
        .where(
            FactNotificationStatus.service_id == sample_service.id,
            FactNotificationStatus.local_date == process_day,
        )
    )
    result = db.session.execute(stmt)
    assert result.rowcount == expected_count
