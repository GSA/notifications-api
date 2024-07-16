import collections
from datetime import datetime
from unittest.mock import Mock

import pytest
from freezegun import freeze_time

from app.enums import KeyType, NotificationStatus, NotificationType, StatisticsType
from app.service.statistics import (
    add_monthly_notification_status_stats,
    create_empty_monthly_notification_status_stats_dict,
    create_stats_dict,
    create_zeroed_stats_dicts,
    format_admin_stats,
    format_statistics,
)

StatsRow = collections.namedtuple("row", ("notification_type", "status", "count"))
NewStatsRow = collections.namedtuple(
    "row", ("notification_type", "status", "key_type", "count")
)


# email_counts and sms_counts are 3-tuple of requested, delivered, failed
@pytest.mark.idparametrize(
    "stats, email_counts, sms_counts",
    {
        "empty": ([], [0, 0, 0], [0, 0, 0]),
        "always_increment_requested": (
            [
                StatsRow(NotificationType.EMAIL, NotificationStatus.DELIVERED, 1),
                StatsRow(NotificationType.EMAIL, NotificationStatus.FAILED, 1),
            ],
            [2, 1, 1],
            [0, 0, 0],
        ),
        "dont_mix_template_types": (
            [
                StatsRow(NotificationType.EMAIL, NotificationStatus.DELIVERED, 1),
                StatsRow(NotificationType.SMS, NotificationStatus.DELIVERED, 1),
            ],
            [1, 1, 0],
            [1, 1, 0],
        ),
        "convert_fail_statuses_to_failed": (
            [
                StatsRow(NotificationType.EMAIL, NotificationStatus.FAILED, 1),
                StatsRow(
                    NotificationType.EMAIL, NotificationStatus.TECHNICAL_FAILURE, 1
                ),
                StatsRow(
                    NotificationType.EMAIL, NotificationStatus.TEMPORARY_FAILURE, 1
                ),
                StatsRow(
                    NotificationType.EMAIL, NotificationStatus.PERMANENT_FAILURE, 1
                ),
            ],
            [4, 0, 4],
            [0, 0, 0],
        ),
        "convert_sent_to_delivered": (
            [
                StatsRow(NotificationType.SMS, NotificationStatus.SENDING, 1),
                StatsRow(NotificationType.SMS, NotificationStatus.DELIVERED, 1),
                StatsRow(NotificationType.SMS, NotificationStatus.SENT, 1),
            ],
            [0, 0, 0],
            [3, 2, 0],
        ),
        "handles_none_rows": (
            [
                StatsRow(NotificationType.SMS, NotificationStatus.SENDING, 1),
                StatsRow(None, None, None),
            ],
            [0, 0, 0],
            [1, 0, 0],
        ),
    },
)
def test_format_statistics(stats, email_counts, sms_counts):
    ret = format_statistics(stats)

    assert ret[NotificationType.EMAIL] == {
        status: count
        for status, count in zip(
            [
                StatisticsType.REQUESTED,
                StatisticsType.DELIVERED,
                StatisticsType.FAILURE,
            ],
            email_counts,
        )
    }

    assert ret[NotificationType.SMS] == {
        status: count
        for status, count in zip(
            [
                StatisticsType.REQUESTED,
                StatisticsType.DELIVERED,
                StatisticsType.FAILURE,
            ],
            sms_counts,
        )
    }


def test_create_zeroed_stats_dicts():
    assert create_zeroed_stats_dicts() == {
        NotificationType.SMS: {
            StatisticsType.REQUESTED: 0,
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
        },
        NotificationType.EMAIL: {
            StatisticsType.REQUESTED: 0,
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
        },
    }


def test_create_stats_dict():
    assert create_stats_dict() == {
        NotificationType.SMS: {
            "total": 0,
            "test-key": 0,
            "failures": {
                NotificationStatus.TECHNICAL_FAILURE: 0,
                NotificationStatus.PERMANENT_FAILURE: 0,
                NotificationStatus.TEMPORARY_FAILURE: 0,
                NotificationStatus.VIRUS_SCAN_FAILED: 0,
            },
        },
        NotificationType.EMAIL: {
            "total": 0,
            "test-key": 0,
            "failures": {
                NotificationStatus.TECHNICAL_FAILURE: 0,
                NotificationStatus.PERMANENT_FAILURE: 0,
                NotificationStatus.TEMPORARY_FAILURE: 0,
                NotificationStatus.VIRUS_SCAN_FAILED: 0,
            },
        },
    }


def test_format_admin_stats_only_includes_test_key_notifications_in_test_key_section():
    rows = [
        NewStatsRow(
            NotificationType.EMAIL,
            NotificationStatus.TECHNICAL_FAILURE,
            KeyType.TEST,
            3,
        ),
        NewStatsRow(
            NotificationType.SMS, NotificationStatus.PERMANENT_FAILURE, KeyType.TEST, 4
        ),
    ]
    stats_dict = format_admin_stats(rows)

    assert stats_dict[NotificationType.EMAIL]["total"] == 0
    assert (
        stats_dict[NotificationType.EMAIL]["failures"][
            NotificationStatus.TECHNICAL_FAILURE
        ]
        == 0
    )
    assert stats_dict[NotificationType.EMAIL]["test-key"] == 3

    assert stats_dict[NotificationType.SMS]["total"] == 0
    assert (
        stats_dict[NotificationType.SMS]["failures"][
            NotificationStatus.PERMANENT_FAILURE
        ]
        == 0
    )
    assert stats_dict[NotificationType.SMS]["test-key"] == 4


def test_format_admin_stats_counts_non_test_key_notifications_correctly():
    rows = [
        NewStatsRow(
            NotificationType.EMAIL,
            NotificationStatus.TECHNICAL_FAILURE,
            KeyType.NORMAL,
            1,
        ),
        NewStatsRow(
            NotificationType.EMAIL,
            NotificationStatus.CREATED,
            KeyType.TEAM,
            3,
        ),
        NewStatsRow(
            NotificationType.SMS,
            NotificationStatus.TEMPORARY_FAILURE,
            KeyType.NORMAL,
            6,
        ),
        NewStatsRow(
            NotificationType.SMS,
            NotificationStatus.SENT,
            KeyType.NORMAL,
            2,
        ),
    ]
    stats_dict = format_admin_stats(rows)

    assert stats_dict[NotificationType.EMAIL]["total"] == 4
    assert (
        stats_dict[NotificationType.EMAIL]["failures"][
            NotificationStatus.TECHNICAL_FAILURE
        ]
        == 1
    )

    assert stats_dict[NotificationType.SMS]["total"] == 8
    assert (
        stats_dict[NotificationType.SMS]["failures"][
            NotificationStatus.PERMANENT_FAILURE
        ]
        == 0
    )


def _stats(requested, delivered, failed):
    return {
        StatisticsType.REQUESTED: requested,
        StatisticsType.DELIVERED: delivered,
        StatisticsType.FAILURE: failed,
    }


@pytest.mark.parametrize(
    "year, expected_years",
    [
        (2018, ["2018-01", "2018-02", "2018-03", "2018-04", "2018-05", "2018-06"]),
        (
            2017,
            [
                "2017-01",
                "2017-02",
                "2017-03",
                "2017-04",
                "2017-05",
                "2017-06",
                "2017-07",
                "2017-08",
                "2017-09",
                "2017-10",
                "2017-11",
                "2017-12",
            ],
        ),
    ],
)
@freeze_time("2018-06-01 04:59:59")
def test_create_empty_monthly_notification_status_stats_dict(year, expected_years):
    output = create_empty_monthly_notification_status_stats_dict(year)
    assert sorted(output.keys()) == expected_years
    for v in output.values():
        assert v == {NotificationType.SMS: {}, NotificationType.EMAIL: {}}


@freeze_time("2018-06-01 04:59:59")
def test_add_monthly_notification_status_stats():
    row_data = [
        {
            "month": datetime(2018, 4, 1),
            "notification_type": NotificationType.SMS,
            "notification_status": NotificationStatus.SENDING,
            "count": 1,
        },
        {
            "month": datetime(2018, 4, 1),
            "notification_type": NotificationType.SMS,
            "notification_status": NotificationStatus.DELIVERED,
            "count": 2,
        },
        {
            "month": datetime(2018, 4, 1),
            "notification_type": NotificationType.EMAIL,
            "notification_status": NotificationStatus.SENDING,
            "count": 4,
        },
        {
            "month": datetime(2018, 5, 1),
            "notification_type": NotificationType.SMS,
            "notification_status": NotificationStatus.SENDING,
            "count": 8,
        },
    ]
    rows = []
    for r in row_data:
        m = Mock(spec=[])
        for k, v in r.items():
            setattr(m, k, v)
        rows.append(m)

    data = create_empty_monthly_notification_status_stats_dict(2018)
    # this data won't be affected
    data["2018-05"][NotificationType.EMAIL][NotificationStatus.SENDING] = 32
    data["2018-05"][NotificationType.EMAIL][StatisticsType.REQUESTED] = 32

    # this data will get combined with the 8 from row_data
    data["2018-05"][NotificationType.SMS][NotificationStatus.SENDING] = 16
    data["2018-05"][NotificationType.SMS][StatisticsType.REQUESTED] = 16

    add_monthly_notification_status_stats(data, rows)
    # first 3 months are empty

    assert data == {
        "2018-01": {NotificationType.SMS: {}, NotificationType.EMAIL: {}},
        "2018-02": {NotificationType.SMS: {}, NotificationType.EMAIL: {}},
        "2018-03": {NotificationType.SMS: {}, NotificationType.EMAIL: {}},
        "2018-04": {
            NotificationType.SMS: {
                NotificationStatus.SENDING: 1,
                NotificationStatus.DELIVERED: 2,
                StatisticsType.REQUESTED: 3,
            },
            NotificationType.EMAIL: {
                NotificationStatus.SENDING: 4,
                StatisticsType.REQUESTED: 4,
            },
        },
        "2018-05": {
            NotificationType.SMS: {
                NotificationStatus.SENDING: 24,
                StatisticsType.REQUESTED: 24,
            },
            NotificationType.EMAIL: {
                NotificationStatus.SENDING: 32,
                StatisticsType.REQUESTED: 32,
            },
        },
        "2018-06": {NotificationType.SMS: {}, NotificationType.EMAIL: {}},
    }
