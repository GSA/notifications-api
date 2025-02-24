from datetime import datetime
from unittest.mock import Mock
import pytest

from app.dao.services_dao import get_specific_hours_stats
from app.enums import StatisticsType
from app.models import TemplateType


def generate_expected_hourly_output(requested_sms_hours):
    """
    Generates expected output only for hours where notifications exist.
    Removes empty hours from the output to match function behavior.
    """
    output = {}
    for hour in requested_sms_hours:
        output[hour] = {
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
    return output


def create_mock_notification(notification_type, status, timestamp, count=1):
    """
    Creates a mock notification object with the required attributes.
    """
    mock = Mock()
    mock.notification_type = notification_type
    mock.status = status
    mock.timestamp = timestamp.replace(minute=0, second=0, microsecond=0)
    mock.count = count
    return mock


test_cases = [
    # Single notification at 14:00 (Only 14:00 is expected in output)
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 2, 18, 14, 15, 0),
        )],
        datetime(2025, 2, 18, 12, 0),
        6,
        generate_expected_hourly_output(
            ["2025-02-18T14:00:00Z"]
        ),
    ),
    # Notification at 17:59 (Only 17:00 is expected in output)
    (
        [create_mock_notification(
            TemplateType.SMS,
            StatisticsType.REQUESTED,
            datetime(2025, 2, 18, 17, 59, 59),
        )],
        datetime(2025, 2, 18, 15, 0),
        3,
        generate_expected_hourly_output(
            ["2025-02-18T17:00:00Z"]
        ),
    ),
    # No notifications at all (Expect empty `{}`)
    (
        [],
        datetime(2025, 2, 18, 10, 0),
        4,
        {},
    ),
    # Two notifications at 09:00 and 11:00 (Only those hours expected)
    (
        [
            create_mock_notification(TemplateType.SMS, StatisticsType.REQUESTED, datetime(2025, 2, 18, 9, 30, 0)),
            create_mock_notification(TemplateType.SMS, StatisticsType.REQUESTED, datetime(2025, 2, 18, 11, 45, 0)),
        ],
        datetime(2025, 2, 18, 8, 0),
        5,
        generate_expected_hourly_output(
            ["2025-02-18T09:00:00Z", "2025-02-18T11:00:00Z"]
        ),
    ),
]


@pytest.mark.parametrize(
    "mocked_notifications, start_date, hours, expected_output",
    test_cases,
)
def test_get_specific_hours(mocked_notifications, start_date, hours, expected_output):
    """
    Tests get_specific_hours_stats to ensure it correctly aggregates hourly statistics.
    """
    results = get_specific_hours_stats(
        mocked_notifications,
        start_date,
        hours=hours
    )

    assert results == expected_output, f"Expected {expected_output}, but got {results}"
