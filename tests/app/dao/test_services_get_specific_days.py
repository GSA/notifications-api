from datetime import datetime
from unittest.mock import Mock

import pytest
import pytz

from app.dao.services_dao import get_specific_days_stats
from app.enums import StatisticsType
from app.models import TemplateType


def generate_expected_output(requested_days, requested_sms_days):
    output = {}
    for day in requested_days:
        output[day] = {
            TemplateType.SMS: {
                StatisticsType.REQUESTED: 1 if day in requested_sms_days else 0,
                StatisticsType.DELIVERED: 0,
                StatisticsType.FAILURE: 0,
            },
            TemplateType.EMAIL: {
                StatisticsType.REQUESTED: 0,
                StatisticsType.DELIVERED: 0,
                StatisticsType.FAILURE: 0,
            },
        }
    return output


def create_mock_notification(notification_type, status, timestamp, count=1):
    return Mock(
        notification_type=notification_type,
        status=status,
        timestamp=timestamp,
        count=count,
    )


test_cases = [
    # Case with normal dates that don't carry over
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 29, 1, 20, 18, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 28, tzinfo=pytz.utc),
        2,
        "America/New_York",
        generate_expected_output(["2025-01-28", "2025-01-29"], ["2025-01-28"]),
    ),

    # Case where EST is saved as next day in UTC
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 30, 4, 30, 0, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 29, tzinfo=pytz.utc),
        2,
        "America/New_York",
        generate_expected_output(["2025-01-29", "2025-01-30"], ["2025-01-29"]),
    ),

    # UTC query
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 29, 10, 15, 0, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 28, tzinfo=pytz.utc),
        2,
        "UTC",
        generate_expected_output(["2025-01-28", "2025-01-29"], ["2025-01-29"]),
    ),

    # Central time test
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 29, 3, 0, 0, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 28, tzinfo=pytz.utc),
        2,
        "America/Chicago",
        generate_expected_output(["2025-01-28", "2025-01-29"], ["2025-01-28"]),
    ),

    # Mountain time test
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 29, 5, 0, 0, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 28, tzinfo=pytz.utc),
        2,
        "America/Denver",
        generate_expected_output(["2025-01-28", "2025-01-29"], ["2025-01-28"]),
    ),

    # Pacific time test
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 29, 7, 30, 0, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 28, tzinfo=pytz.utc),
        2,
        "America/Los_Angeles",
        generate_expected_output(["2025-01-28", "2025-01-29"], ["2025-01-28"]),
    ),

    # No timezone provided => defaults to UTC
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 29, 10, 15, 0, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 28, tzinfo=pytz.utc),
        2,
        None,
        generate_expected_output(["2025-01-28", "2025-01-29"], ["2025-01-29"]),
    ),

    # DST Spring Forward
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2024, 3, 10, 6, 30, 0, tzinfo=pytz.utc),
        )],
        datetime(2024, 3, 9, tzinfo=pytz.utc),
        2,
        "America/New_York",
        generate_expected_output(["2024-03-09", "2024-03-10"], ["2024-03-10"]),
    ),

    # DST Fall Back
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2024, 11, 3, 5, 30, 0, tzinfo=pytz.utc),
        )],
        datetime(2024, 11, 2, tzinfo=pytz.utc),
        2,
        "America/New_York",
        generate_expected_output(["2024-11-02", "2024-11-03"], ["2024-11-03"]),
    ),

    # No notifications
    (
        [],
        datetime(2025, 1, 29, tzinfo=pytz.utc),
        2,
        "UTC",
        generate_expected_output(["2025-01-29", "2025-01-30"], []),
    ),

    # Midnight edge case => 12:00 AM UTC => 7:00 PM previous day EST
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 10, 0, 0, 0, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 9, tzinfo=pytz.utc),
        2,
        "America/New_York",
        generate_expected_output(["2025-01-09", "2025-01-10"], ["2025-01-09"]),
    ),

    # Large query (30 days)
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 1, 15, 12, 0, 0, tzinfo=pytz.utc),
        )],
        datetime(2025, 1, 1, tzinfo=pytz.utc),
        30,
        "America/New_York",
        generate_expected_output(
            [f"2025-01-{str(day).zfill(2)}" for day in range(1, 31)],
            ["2025-01-15"],
        ),
    ),
]


@pytest.mark.parametrize(
    "mocked_notifications, start_date, days, timezone, expected_output",
    test_cases,
)
def test_get_specific_days(mocked_notifications, start_date, days, timezone, expected_output):
    results = get_specific_days_stats(
        mocked_notifications,
        start_date,
        days,
        timezone=timezone,
    )
    assert results == expected_output
