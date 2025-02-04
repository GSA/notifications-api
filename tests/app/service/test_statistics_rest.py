import uuid
from datetime import date, datetime

import pytest
from freezegun import freeze_time

from app.enums import (
    KeyType,
    NotificationStatus,
    NotificationType,
    StatisticsType,
    TemplateType,
)
from app.utils import utc_now
from tests.app.db import (
    create_ft_notification_status,
    create_notification,
    create_service,
    create_template,
)


@freeze_time("2017-11-11 06:00")
def test_get_template_usage_by_month_returns_correct_data(
    admin_request, sample_template
):
    create_ft_notification_status(
        local_date=date(2017, 4, 2),
        template=sample_template,
        count=3,
    )
    create_notification(sample_template, created_at=utc_now())

    resp_json = admin_request.get(
        "service.get_monthly_template_usage",
        service_id=sample_template.service_id,
        year=2017,
    )
    resp_json = resp_json["stats"]

    assert len(resp_json) == 2

    assert resp_json[0]["template_id"] == str(sample_template.id)
    assert resp_json[0]["name"] == sample_template.name
    assert resp_json[0]["type"] == sample_template.template_type
    assert resp_json[0]["month"] == 4
    assert resp_json[0]["year"] == 2017
    assert resp_json[0]["count"] == 3

    assert resp_json[1]["template_id"] == str(sample_template.id)
    assert resp_json[1]["name"] == sample_template.name
    assert resp_json[1]["type"] == sample_template.template_type
    assert resp_json[1]["month"] == 11
    assert resp_json[1]["year"] == 2017
    assert resp_json[1]["count"] == 1


@freeze_time("2017-11-11 06:00")
def test_get_template_usage_by_month_returns_two_templates(
    admin_request, sample_template, sample_service
):
    template_one = create_template(
        sample_service,
        template_type=TemplateType.SMS,
        template_name="TEST TEMPLATE",
        hidden=True,
    )
    create_ft_notification_status(
        local_date=datetime(2017, 4, 2),
        template=template_one,
        count=1,
    )
    create_ft_notification_status(
        local_date=datetime(2017, 4, 2),
        template=sample_template,
        count=3,
    )
    create_notification(sample_template, created_at=utc_now())

    resp_json = admin_request.get(
        "service.get_monthly_template_usage",
        service_id=sample_template.service_id,
        year=2017,
    )

    resp_json = sorted(
        resp_json["stats"], key=lambda k: (k["year"], k["month"], k["count"])
    )
    assert len(resp_json) == 3

    assert resp_json[0]["template_id"] == str(template_one.id)
    assert resp_json[0]["name"] == template_one.name
    assert resp_json[0]["type"] == template_one.template_type
    assert resp_json[0]["month"] == 4
    assert resp_json[0]["year"] == 2017
    assert resp_json[0]["count"] == 1

    assert resp_json[1]["template_id"] == str(sample_template.id)
    assert resp_json[1]["name"] == sample_template.name
    assert resp_json[1]["type"] == sample_template.template_type
    assert resp_json[1]["month"] == 4
    assert resp_json[1]["year"] == 2017
    assert resp_json[1]["count"] == 3

    assert resp_json[2]["template_id"] == str(sample_template.id)
    assert resp_json[2]["name"] == sample_template.name
    assert resp_json[2]["type"] == sample_template.template_type
    assert resp_json[2]["month"] == 11
    assert resp_json[2]["year"] == 2017
    assert resp_json[2]["count"] == 1


@pytest.mark.parametrize(
    "today_only, stats",
    [
        (
            False,
            {
                StatisticsType.REQUESTED: 2,
                StatisticsType.DELIVERED: 1,
                StatisticsType.FAILURE: 0,
                StatisticsType.PENDING: 0,
            },
        ),
        (
            True,
            {
                StatisticsType.REQUESTED: 1,
                StatisticsType.DELIVERED: 0,
                StatisticsType.FAILURE: 0,
                StatisticsType.PENDING: 0,
            },
        ),
    ],
    ids=["seven_days", "today"],
)
def test_get_service_notification_statistics(
    admin_request, sample_service, sample_template, today_only, stats
):
    create_ft_notification_status(
        date(2000, 1, 1), NotificationType.SMS, sample_service, count=1
    )
    with freeze_time("2000-01-02T12:00:00"):
        create_notification(sample_template, status=NotificationStatus.CREATED)
        resp = admin_request.get(
            "service.get_service_notification_statistics",
            service_id=sample_template.service_id,
            today_only=today_only,
        )

    assert set(resp["data"].keys()) == {
        NotificationType.SMS,
        NotificationType.EMAIL,
    }
    assert resp["data"][NotificationType.SMS] == stats


def test_get_service_notification_statistics_with_unknown_service(admin_request):
    resp = admin_request.get(
        "service.get_service_notification_statistics", service_id=uuid.uuid4()
    )

    assert resp["data"] == {
        NotificationType.SMS: {
            StatisticsType.REQUESTED: 0,
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
        },
        NotificationType.EMAIL: {
            StatisticsType.REQUESTED: 0,
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
        },
    }


@pytest.mark.parametrize(
    "kwargs, expected_json",
    [
        ({"year": "baz"}, {"message": "Year must be a number", "result": "error"}),
        ({}, {"message": "Year must be a number", "result": "error"}),
    ],
)
def test_get_monthly_notification_stats_returns_errors(
    admin_request, sample_service, kwargs, expected_json
):
    response = admin_request.get(
        "service.get_monthly_notification_stats",
        service_id=sample_service.id,
        _expected_status=400,
        **kwargs
    )
    assert response == expected_json


def test_get_monthly_notification_stats_returns_404_if_no_service(admin_request):
    response = admin_request.get(
        "service.get_monthly_notification_stats",
        service_id=uuid.uuid4(),
        _expected_status=404,
    )
    assert response == {"message": "No result found", "result": "error"}


def test_get_monthly_notification_stats_returns_empty_stats_with_correct_dates(
    admin_request, sample_service
):
    response = admin_request.get(
        "service.get_monthly_notification_stats",
        service_id=sample_service.id,
        year=2016,
    )
    assert len(response["data"]) == 12

    keys = [
        "2016-01",
        "2016-02",
        "2016-03",
        "2016-04",
        "2016-05",
        "2016-06",
        "2016-07",
        "2016-08",
        "2016-09",
        "2016-10",
        "2016-11",
        "2016-12",
    ]
    assert sorted(response["data"].keys()) == keys
    for val in response["data"].values():
        assert val == {NotificationType.SMS: {}, NotificationType.EMAIL: {}}


def test_get_monthly_notification_stats_returns_stats(admin_request, sample_service):
    sms_t1 = create_template(sample_service)
    sms_t2 = create_template(sample_service)
    email_template = create_template(sample_service, template_type=TemplateType.EMAIL)

    create_notification(
        sms_t1,
        created_at=datetime(2016, 6, 1, 1, 1, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sms_t1,
        created_at=datetime(2016, 6, 2, 1, 1, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sms_t1,
        created_at=datetime(2016, 7, 1, 1, 1, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sms_t2,
        created_at=datetime(2016, 7, 1, 1, 1, 0),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sms_t1,
        created_at=datetime(2016, 7, 1, 1, 1, 0),
        status=NotificationStatus.CREATED,
    )
    create_notification(
        email_template,
        created_at=datetime(2016, 7, 1, 1, 1, 0),
        status=NotificationStatus.DELIVERED,
    )

    response = admin_request.get(
        "service.get_monthly_notification_stats",
        service_id=sample_service.id,
        year=2016,
    )
    assert len(response["data"]) == 12

    assert response["data"]["2016-06"] == {
        NotificationType.SMS: {
            # it combines the two days
            NotificationStatus.DELIVERED: 2,
            StatisticsType.REQUESTED: 2,
        },
        NotificationType.EMAIL: {},
    }
    assert response["data"]["2016-07"] == {
        # it combines the two template types
        NotificationType.SMS: {
            NotificationStatus.CREATED: 1,
            NotificationStatus.DELIVERED: 2,
            StatisticsType.REQUESTED: 3,
        },
        NotificationType.EMAIL: {
            StatisticsType.DELIVERED: 1,
            StatisticsType.REQUESTED: 1,
        },
    }


def test_get_monthly_notification_stats_ignores_test_keys(
    admin_request, sample_service
):
    create_template(service=sample_service)

    create_notification(
        sample_service.templates[0],
        created_at=datetime(2016, 6, 1, 1, 1, 0),
        key_type=KeyType.NORMAL,
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sample_service.templates[0],
        created_at=datetime(2016, 6, 2, 1, 1, 0),
        key_type=KeyType.NORMAL,
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sample_service.templates[0],
        created_at=datetime(2016, 6, 1, 1, 1, 0),
        key_type=KeyType.TEAM,
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        sample_service.templates[0],
        created_at=datetime(2016, 6, 1, 1, 1, 0),
        key_type=KeyType.TEST,
        status=NotificationStatus.DELIVERED,
    )

    response = admin_request.get(
        "service.get_monthly_notification_stats",
        service_id=sample_service.id,
        year=2016,
    )

    assert response["data"]["2016-06"][NotificationType.SMS] == {
        NotificationStatus.DELIVERED: 3,
        StatisticsType.REQUESTED: 3,
    }


def test_get_monthly_notification_stats_checks_dates(admin_request, sample_service):
    t = create_template(sample_service)

    create_notification(
        t,
        created_at=datetime(2016, 4, 2),
        status=NotificationStatus.SENDING,
    )
    create_notification(
        t,
        created_at=datetime(2017, 3, 31),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        t,
        created_at=datetime(2017, 4, 11),
        status=NotificationStatus.PERMANENT_FAILURE,
    )

    response = admin_request.get(
        "service.get_monthly_notification_stats",
        service_id=sample_service.id,
        year=2016,
    )
    assert "2016-04" in response["data"]
    assert "2017-04" not in response["data"]
    assert response["data"]["2016-04"][NotificationType.SMS] == {
        NotificationStatus.SENDING: 1,
        StatisticsType.REQUESTED: 1,
    }
    assert response["data"]["2016-04"][NotificationType.SMS] == {
        NotificationStatus.SENDING: 1,
        StatisticsType.REQUESTED: 1,
    }


def test_get_monthly_notification_stats_only_gets_for_one_service(
    admin_request, notify_db_session
):
    services = [create_service(), create_service(service_name="2")]

    templates = [create_template(services[0]), create_template(services[1])]

    create_notification(
        templates[0],
        created_at=datetime(2016, 6, 1),
        status=NotificationStatus.CREATED,
    )
    create_notification(
        templates[1],
        created_at=datetime(2016, 6, 1),
        status=NotificationStatus.DELIVERED,
    )

    response = admin_request.get(
        "service.get_monthly_notification_stats",
        service_id=services[0].id,
        year=2016,
    )

    assert response["data"]["2016-06"] == {
        NotificationType.SMS: {
            NotificationStatus.CREATED: 1,
            StatisticsType.REQUESTED: 1,
        },
        NotificationType.EMAIL: {},
    }
