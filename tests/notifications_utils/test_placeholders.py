import re

import pytest

from notifications_utils.field import Placeholder


@pytest.mark.parametrize(
    "body, expected",
    [
        ("((with-brackets))", "with-brackets"),
        ("without-brackets", "without-brackets"),
    ],
)
def test_placeholder_returns_name(body, expected):
    assert Placeholder(body).name == expected


@pytest.mark.parametrize(
    "body, is_conditional",
    [
        ("not a conditional", False),
        ("not? a conditional", False),
        ("a?? conditional", True),
    ],
)
def test_placeholder_identifies_conditional(body, is_conditional):
    assert Placeholder(body).is_conditional() == is_conditional


@pytest.mark.parametrize(
    "body, conditional_text",
    [
        ("a??b", "b"),
        ("a?? b ", " b "),
        ("a??b??c", "b??c"),
    ],
)
def test_placeholder_gets_conditional_text(body, conditional_text):
    assert Placeholder(body).conditional_text == conditional_text


def test_placeholder_raises_if_accessing_conditional_text_on_non_conditional():
    with pytest.raises(ValueError):
        Placeholder("hello").conditional_text


@pytest.mark.parametrize(
    "body, value, result",
    [
        ("a??b", "Yes", "b"),
        ("a??b", "No", ""),
    ],
)
def test_placeholder_gets_conditional_body(body, value, result):
    assert Placeholder(body).get_conditional_body(value) == result


def test_placeholder_raises_if_getting_conditional_body_on_non_conditional():
    with pytest.raises(ValueError):
        Placeholder("hello").get_conditional_body("Yes")


def test_placeholder_can_be_constructed_from_regex_match():
    match = re.search(r"\(\(.*\)\)", "foo ((bar)) baz")
    assert Placeholder.from_match(match).name == "bar"
