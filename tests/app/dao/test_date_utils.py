from datetime import date, datetime

import pytest

from app.dao.date_util import (
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
