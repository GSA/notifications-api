from datetime import datetime

import pytest
import pytz
from freezegun import freeze_time

from notifications_utils.letter_timings import (
    get_letter_timings,
    letter_can_be_cancelled,
)


@freeze_time("2017-07-14 13:59:59")  # Friday, before print deadline (3PM EST)
@pytest.mark.parametrize(
    (
        "upload_time",
        "expected_print_time",
        "is_printed",
        "first_class",
        "expected_earliest",
        "expected_latest",
    ),
    [
        # EST
        # ==================================================================
        #  First thing Monday
        (
            "Monday 2017-07-10 00:00:01",
            "Tuesday 2017-07-11 15:00",
            True,
            "Wednesday 2017-07-12 16:00",
            "Thursday 2017-07-13 16:00",
            "Friday 2017-07-14 16:00",
        ),
        #  Monday at 17:29 EST (sent on monday)
        (
            "Monday 2017-07-10 16:29:59",
            "Tuesday 2017-07-11 15:00",
            True,
            "Wednesday 2017-07-12 16:00",
            "Thursday 2017-07-13 16:00",
            "Friday 2017-07-14 16:00",
        ),
        #  Monday at 17:30 EST (sent on tuesday)
        (
            "Monday 2017-07-10 16:30:01",
            "Wednesday 2017-07-12 15:00",
            True,
            "Thursday 2017-07-13 16:00",
            "Friday 2017-07-14 16:00",
            "Saturday 2017-07-15 16:00",
        ),
        #  Tuesday before 17:30 EST
        (
            "Tuesday 2017-07-11 12:00:00",
            "Wednesday 2017-07-12 15:00",
            True,
            "Thursday 2017-07-13 16:00",
            "Friday 2017-07-14 16:00",
            "Saturday 2017-07-15 16:00",
        ),
        #  Wednesday before 17:30 EST
        (
            "Wednesday 2017-07-12 12:00:00",
            "Thursday 2017-07-13 15:00",
            True,
            "Friday 2017-07-14 16:00",
            "Saturday 2017-07-15 16:00",
            "Monday 2017-07-17 16:00",
        ),
        #  Thursday before 17:30 EST
        (
            "Thursday 2017-07-13 12:00:00",
            "Friday 2017-07-14 15:00",
            False,
            "Saturday 2017-07-15 16:00",
            "Monday 2017-07-17 16:00",
            "Tuesday 2017-07-18 16:00",
        ),
        #  Friday anytime
        (
            "Friday 2017-07-14 00:00:00",
            "Monday 2017-07-17 15:00",
            False,
            "Tuesday 2017-07-18 16:00",
            "Wednesday 2017-07-19 16:00",
            "Thursday 2017-07-20 16:00",
        ),
        (
            "Friday 2017-07-14 12:00:00",
            "Monday 2017-07-17 15:00",
            False,
            "Tuesday 2017-07-18 16:00",
            "Wednesday 2017-07-19 16:00",
            "Thursday 2017-07-20 16:00",
        ),
        (
            "Friday 2017-07-14 22:00:00",
            "Monday 2017-07-17 15:00",
            False,
            "Tuesday 2017-07-18 16:00",
            "Wednesday 2017-07-19 16:00",
            "Thursday 2017-07-20 16:00",
        ),
        #  Saturday anytime
        (
            "Saturday 2017-07-14 12:00:00",
            "Monday 2017-07-17 15:00",
            False,
            "Tuesday 2017-07-18 16:00",
            "Wednesday 2017-07-19 16:00",
            "Thursday 2017-07-20 16:00",
        ),
        #  Sunday before 1730 EST
        (
            "Sunday 2017-07-15 15:59:59",
            "Monday 2017-07-17 15:00",
            False,
            "Tuesday 2017-07-18 16:00",
            "Wednesday 2017-07-19 16:00",
            "Thursday 2017-07-20 16:00",
        ),
        #  Sunday after 17:30 EST
        (
            "Sunday 2017-07-16 16:30:01",
            "Tuesday 2017-07-18 15:00",
            False,
            "Wednesday 2017-07-19 16:00",
            "Thursday 2017-07-20 16:00",
            "Friday 2017-07-21 16:00",
        ),
        # GMT
        # ==================================================================
        #  Monday at 17:29 GMT
        (
            "Monday 2017-01-02 17:29:59",
            "Tuesday 2017-01-03 15:00",
            True,
            "Wednesday 2017-01-04 16:00",
            "Thursday 2017-01-05 16:00",
            "Friday 2017-01-06 16:00",
        ),
        #  Monday at 17:00 GMT
        (
            "Monday 2017-01-02 17:30:01",
            "Wednesday 2017-01-04 15:00",
            True,
            "Thursday 2017-01-05 16:00",
            "Friday 2017-01-06 16:00",
            "Saturday 2017-01-07 16:00",
        ),
    ],
)
@pytest.mark.skip(reason="Letters being developed later")
def test_get_estimated_delivery_date_for_letter(
    upload_time,
    expected_print_time,
    is_printed,
    first_class,
    expected_earliest,
    expected_latest,
):
    # remove the day string from the upload_time, which is purely informational

    def format_dt(x):
        return x.astimezone(pytz.timezone("America/New_York")).strftime(
            "%A %Y-%m-%d %H:%M"
        )

    upload_time = upload_time.split(" ", 1)[1]

    timings = get_letter_timings(upload_time, postage="second")

    assert format_dt(timings.printed_by) == expected_print_time
    assert timings.is_printed == is_printed
    assert format_dt(timings.earliest_delivery) == expected_earliest
    assert format_dt(timings.latest_delivery) == expected_latest

    first_class_timings = get_letter_timings(upload_time, postage="first")

    assert format_dt(first_class_timings.printed_by) == expected_print_time
    assert first_class_timings.is_printed == is_printed
    assert format_dt(first_class_timings.earliest_delivery) == first_class
    assert format_dt(first_class_timings.latest_delivery) == first_class


@pytest.mark.parametrize("status", ["sending", "pending"])
def test_letter_cannot_be_cancelled_if_letter_status_is_not_created_or_pending_virus_check(
    status,
):
    notification_created_at = datetime.utcnow()

    assert not letter_can_be_cancelled(status, notification_created_at)


@freeze_time("2018-7-7 16:00:00")
@pytest.mark.parametrize(
    "notification_created_at",
    [
        datetime(2018, 7, 6, 18, 0),  # created yesterday after 1730
        datetime(2018, 7, 7, 12, 0),  # created today
    ],
)
@pytest.mark.skip(reason="Letters not part of release")
def test_letter_can_be_cancelled_if_before_1730_and_letter_created_before_1730(
    notification_created_at,
):
    notification_status = "pending-virus-check"

    assert letter_can_be_cancelled(notification_status, notification_created_at)


@freeze_time("2017-12-12 17:30:00")
@pytest.mark.parametrize(
    "notification_created_at",
    [
        datetime(2017, 12, 12, 17, 0),
        datetime(2017, 12, 12, 17, 30),
    ],
)
@pytest.mark.skip(reason="Letters not part of release")
def test_letter_cannot_be_cancelled_if_1730_exactly_and_letter_created_at_or_before_1730(
    notification_created_at,
):
    notification_status = "pending-virus-check"

    assert not letter_can_be_cancelled(notification_status, notification_created_at)


@freeze_time("2018-7-7 19:00:00")
@pytest.mark.parametrize(
    "notification_created_at",
    [
        datetime(2018, 7, 6, 18, 0),  # created yesterday after 1730
        datetime(2018, 7, 7, 12, 0),  # created today before 1730
    ],
)
@pytest.mark.skip(reason="Letters not part of release")
def test_letter_cannot_be_cancelled_if_after_1730_and_letter_created_before_1730(
    notification_created_at,
):
    notification_status = "created"

    assert not letter_can_be_cancelled(notification_status, notification_created_at)


@freeze_time("2018-7-7 15:00:00")
@pytest.mark.skip(reason="Letters not part of release")
def test_letter_cannot_be_cancelled_if_before_1730_and_letter_created_before_1730_yesterday():
    notification_status = "created"

    assert not letter_can_be_cancelled(notification_status, datetime(2018, 7, 6, 14, 0))


@freeze_time("2018-7-7 15:00:00")
@pytest.mark.skip(reason="Letters not part of release")
def test_letter_cannot_be_cancelled_if_before_1730_and_letter_created_after_1730_two_days_ago():
    notification_status = "created"

    assert not letter_can_be_cancelled(notification_status, datetime(2018, 7, 5, 19, 0))


@freeze_time("2018-7-7 19:00:00")
@pytest.mark.parametrize(
    "notification_created_at",
    [
        datetime(2018, 7, 7, 18, 30),
        datetime(2018, 7, 7, 19, 0),
    ],
)
def test_letter_can_be_cancelled_if_after_1730_and_letter_created_at_1730_today_or_later(
    notification_created_at,
):
    notification_status = "created"

    assert letter_can_be_cancelled(notification_status, notification_created_at)
