from datetime import date, datetime

import pytest

from app.dao.date_util import (
    generate_hourly_range,
    get_calendar_year,
    get_calendar_year_for_datetime,
    get_month_start_and_end_date_in_utc,
    get_new_years,
)


def test_get_calendar_year():
    start, end = get_calendar_year(2000)
    assert str(start) == "2000-01-01 00:00:00"
    assert str(end) == "2000-12-31 23:59:59.999999"


def test_get_new_years():
    new_years = get_new_years(2016)
    assert str(new_years) == "2016-01-01 00:00:00"
    assert new_years.tzinfo is None


@pytest.mark.parametrize(
    "month, year, expected_start, expected_end",
    [
        (
            7,
            2017,
            datetime(2017, 7, 1, 0, 00, 00),
            datetime(2017, 7, 31, 23, 59, 59, 99999),
        ),
        (
            2,
            2016,
            datetime(2016, 2, 1, 0, 00, 00),
            datetime(2016, 2, 29, 23, 59, 59, 99999),
        ),
        (
            2,
            2017,
            datetime(2017, 2, 1, 0, 00, 00),
            datetime(2017, 2, 28, 23, 59, 59, 99999),
        ),
        (
            9,
            2018,
            datetime(2018, 9, 1, 0, 00, 00),
            datetime(2018, 9, 30, 23, 59, 59, 99999),
        ),
        (
            12,
            2019,
            datetime(2019, 12, 1, 0, 00, 00),
            datetime(2019, 12, 31, 23, 59, 59, 99999),
        ),
    ],
)
def test_get_month_start_and_end_date_in_utc(month, year, expected_start, expected_end):
    month_year = datetime(year, month, 10, 13, 30, 00)
    result = get_month_start_and_end_date_in_utc(month_year)
    assert result[0] == expected_start
    assert result[1] == expected_end


@pytest.mark.parametrize(
    "dt, fy",
    [
        (datetime(2018, 4, 1, 1, 0, 0), 2018),
        (datetime(2019, 3, 31, 23, 59, 59), 2019),
        (date(2019, 3, 31), 2019),
        (date(2019, 4, 2), 2019),
    ],
)
def test_get_calendar_year_for_datetime(dt, fy):
    assert get_calendar_year_for_datetime(dt) == fy


def test_generate_hourly_range_with_end_date():
    start_date = datetime(2025, 2, 18, 12, 0)
    end_date = datetime(2025, 2, 18, 15, 0)
    result = list(generate_hourly_range(start_date, end_date=end_date))

    expected = [
        datetime(2025, 2, 18, 12, 0),
        datetime(2025, 2, 18, 13, 0),
        datetime(2025, 2, 18, 14, 0),
        datetime(2025, 2, 18, 15, 0),
    ]

    assert result == expected, f"Expected {expected}, but got {result}"

def test_generate_hourly_range_with_hours():
    start_date = datetime(2025, 2, 18, 12, 0)
    result = list(generate_hourly_range(start_date, hours=3))

    expected = [
        datetime(2025, 2, 18, 12, 0),
        datetime(2025, 2, 18, 13, 0),
        datetime(2025, 2, 18, 14, 0),
    ]

    assert result == expected, f"Expected {expected}, but got {result}"

def test_generate_hourly_range_with_zero_hours():
    start_date = datetime(2025, 2, 18, 12, 0)
    result = list(generate_hourly_range(start_date, hours=0))

    assert result == [], f"Expected an empty list, but got {result}"


def test_generate_hourly_range_with_end_date_before_start():
    start_date = datetime(2025, 2, 18, 12, 0)
    end_date = datetime(2025, 2, 18, 10, 0)
    result = list(generate_hourly_range(start_date, end_date=end_date))

    assert result == [], f"Expected empty list, but got {result}"
