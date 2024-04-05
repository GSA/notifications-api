import pytest

from notifications_utils.safe_string import (
    make_string_safe_for_email_local_part,
    make_string_safe_for_id,
)


@pytest.mark.parametrize(
    "unsafe_string, expected_safe",
    [
        ("name with spaces", "name.with.spaces"),
        ("singleword", "singleword"),
        ("UPPER CASE", "upper.case"),
        ("Service - with dash", "service.with.dash"),
        ("lots      of spaces", "lots.of.spaces"),
        ("name.with.dots", "name.with.dots"),
        ("name-with-other-delimiters", "namewithotherdelimiters"),
        (".leading", "leading"),
        ("trailing.", "trailing"),
        ("üńïçödë wördś", "unicode.words"),
    ],
)
def test_email_safe_return_dot_separated_email_local_part(unsafe_string, expected_safe):
    assert make_string_safe_for_email_local_part(unsafe_string) == expected_safe


@pytest.mark.parametrize(
    "unsafe_string, expected_safe",
    [
        ("name with spaces", "name-with-spaces"),
        ("singleword", "singleword"),
        ("UPPER CASE", "upper-case"),
        ("Service - with dash", "service---with-dash"),
        ("lots      of spaces", "lots-of-spaces"),
        ("name.with.dots", "namewithdots"),
        ("name-with-dashes", "name-with-dashes"),
        ("N. London", "n-london"),
        (".leading", "leading"),
        ("-leading", "-leading"),
        ("trailing.", "trailing"),
        ("trailing-", "trailing-"),
        ("üńïçödë wördś", "unicode-words"),
    ],
)
def test_id_safe_return_dash_separated_string(unsafe_string, expected_safe):
    assert make_string_safe_for_id(unsafe_string) == expected_safe
