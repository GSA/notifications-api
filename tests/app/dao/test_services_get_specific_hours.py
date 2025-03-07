from collections import namedtuple
from datetime import datetime

import pytest

from app.dao.services_dao import get_specific_hours_stats
from app.enums import StatisticsType
from app.models import TemplateType

NotificationRow = namedtuple(
    "NotificationRow", ["notification_type", "status", "timestamp", "count"]
)


def generate_expected_hourly_output(requested_sms_hours):
    return {
        hour: {
            TemplateType.SMS: {
                StatisticsType.REQUESTED: 1,
                StatisticsType.DELIVERED: 0,
                StatisticsType.FAILURE: 0,
                StatisticsType.PENDING: 0,
            },
            TemplateType.EMAIL: {
                StatisticsType.REQUESTED: 0,
                StatisticsType.DELIVERED: 0,
                StatisticsType.FAILURE: 0,
                StatisticsType.PENDING: 0,
            },
        }
        for hour in requested_sms_hours
    }


def create_mock_notification(notification_type, status, timestamp, count=1):
    """
    Creates a named tuple with the attributes required by format_statistics.
    """
    return NotificationRow(
        notification_type=notification_type,
        status=status,
        timestamp=timestamp.replace(minute=0, second=0, microsecond=0),
        count=count,
    )


test_cases = [
    (
        [
            create_mock_notification(
                TemplateType.SMS,
                StatisticsType.REQUESTED,
                datetime(2025, 2, 18, 14, 15, 0),
            )
        ],
        datetime(2025, 2, 18, 12, 0),
        6,
        generate_expected_hourly_output(["2025-02-18T14:00:00Z"]),
    ),
    (
        [
            create_mock_notification(
                TemplateType.SMS,
                StatisticsType.REQUESTED,
                datetime(2025, 2, 18, 17, 59, 59),
            )
        ],
        datetime(2025, 2, 18, 15, 0),
        3,
        generate_expected_hourly_output(["2025-02-18T17:00:00Z"]),
    ),
    ([], datetime(2025, 2, 18, 10, 0), 4, {}),
    (
        [
            create_mock_notification(
                TemplateType.SMS,
                StatisticsType.REQUESTED,
                datetime(2025, 2, 18, 9, 30, 0),
            ),
            create_mock_notification(
                TemplateType.SMS,
                StatisticsType.REQUESTED,
                datetime(2025, 2, 18, 11, 45, 0),
            ),
        ],
        datetime(2025, 2, 18, 8, 0),
        5,
        generate_expected_hourly_output(
            ["2025-02-18T09:00:00Z", "2025-02-18T11:00:00Z"]
        ),
    ),
]


@pytest.mark.parametrize(
    "mocked_notifications, start_date, hours, expected_output", test_cases
)
def test_get_specific_hours(mocked_notifications, start_date, hours, expected_output):
    results = get_specific_hours_stats(mocked_notifications, start_date, hours=hours)
    assert results == expected_output, f"Expected {expected_output}, but got {results}"
