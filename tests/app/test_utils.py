import uuid
from datetime import date, datetime

import pytest
from freezegun import freeze_time

from app.models import UPLOAD_DOCUMENT
from app.utils import (
    format_sequential_number,
    get_midnight_for_day_before,
    get_midnight_in_utc,
    get_public_notify_type_text,
    get_reference_from_personalisation,
    get_uuid_string_or_none,
    midnight_n_days_ago,
)


@pytest.mark.parametrize(
    "date, expected_date",
    [
        (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 15, 0, 0)),
        (datetime(2016, 6, 15, 0, 0), datetime(2016, 6, 15, 0, 0)),
        (datetime(2016, 9, 15, 11, 59), datetime(2016, 9, 15, 0, 0)),
        # works for both dates and datetimes
        (date(2016, 1, 15), datetime(2016, 1, 15, 0, 0)),
        (date(2016, 6, 15), datetime(2016, 6, 15, 0, 0)),
    ],
)
def test_get_midnight_in_utc_returns_expected_date(date, expected_date):
    assert get_midnight_in_utc(date) == expected_date


@pytest.mark.parametrize(
    "date, expected_date",
    [
        (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 14, 0, 0)),
        (datetime(2016, 7, 15, 0, 0), datetime(2016, 7, 14, 0, 0)),
        (datetime(2016, 8, 23, 11, 59), datetime(2016, 8, 22, 0, 0)),
    ],
)
def test_get_midnight_for_day_before_returns_expected_date(date, expected_date):
    assert get_midnight_for_day_before(date) == expected_date


@pytest.mark.parametrize(
    "current_time, arg, expected_datetime",
    [
        # winter
        ("2018-01-10 23:59", 1, datetime(2018, 1, 9, 0, 0)),
        ("2018-01-11 00:00", 1, datetime(2018, 1, 10, 0, 0)),
        # bst switchover at 1am 25th
        ("2018-03-25 10:00", 1, datetime(2018, 3, 24, 0, 0)),
        ("2018-03-26 10:00", 1, datetime(2018, 3, 25, 0, 0)),
        ("2018-03-27 10:00", 1, datetime(2018, 3, 26, 0, 0)),
        # summer
        ("2018-06-05 10:00", 1, datetime(2018, 6, 4, 0, 0)),
        # zero days ago
        ("2018-01-11 00:00", 0, datetime(2018, 1, 11, 0, 0)),
        ("2018-06-05 10:00", 0, datetime(2018, 6, 5, 0, 0)),
    ],
)
def test_midnight_n_days_ago(current_time, arg, expected_datetime):
    with freeze_time(current_time):
        assert midnight_n_days_ago(arg) == expected_datetime


def test_format_sequential_number():
    assert format_sequential_number(123) == "0000007b"


@pytest.mark.parametrize(
    "personalisation, expected_response",
    [
        ({"nothing": "interesting"}, None),
        ({"reference": "something"}, "something"),
        (None, None),
    ],
)
def test_get_reference_from_personalisation(personalisation, expected_response):
    assert get_reference_from_personalisation(personalisation) == expected_response


def test_get_uuid_string_or_none():
    my_uuid = uuid.uuid4()
    assert str(my_uuid) == get_uuid_string_or_none(my_uuid)

    assert get_uuid_string_or_none(None) is None


def test_get_public_notify_type_text():
    assert get_public_notify_type_text(UPLOAD_DOCUMENT) == "document"


# This method is used for simulating bulk sends.  We use localstack and run on a developer's machine to do the
# simulation.  Please see docs->bulk_testing.md for instructions.
# def test_generate_csv_for_bulk_testing():
#     f = open("bulktest_1000.csv", "w")
#     f.write("phone number\n")
#     for _ in range(0, 500):
#         f.write("14254147755\n")   # AWS Pinpoint Simulated Success
#         f.write("14254147167\n")   # AWS Pinpoint Simulated Failure
#     f.close()
