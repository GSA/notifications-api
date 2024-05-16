import dateutil
import pytest

from notifications_utils.timezones import utc_string_to_aware_gmt_datetime


@pytest.mark.parametrize(
    "input_value,expectation",
    [
        ("foo", pytest.raises(dateutil.parser._parser.ParserError)),
        (100, pytest.raises(TypeError)),
        (True, pytest.raises(TypeError)),
        (False, pytest.raises(TypeError)),
        (None, pytest.raises(TypeError)),
    ],
)
def test_utc_string_to_aware_gmt_datetime_rejects_bad_input(input_value, expectation):
    with expectation:
        utc_string_to_aware_gmt_datetime(input_value)


@pytest.mark.parametrize(
    "naive_time, expected_aware_hour",
    [
        ("2000-12-1 20:01", "15:01"),
        ("2000-06-1 20:01", "16:01"),
    ],
)
def test_utc_string_to_aware_gmt_datetime_handles_summer_and_winter(
    naive_time,
    expected_aware_hour,
):
    assert (
        utc_string_to_aware_gmt_datetime(naive_time).strftime("%H:%M")
        == expected_aware_hour
    )
