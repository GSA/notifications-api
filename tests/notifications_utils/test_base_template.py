from unittest.mock import patch

import pytest

from notifications_utils.template import SubjectMixin, Template


class ConcreteImplementation:
    template_type = None

    # Can’t instantiate and test templates unless they implement __str__
    def __str__(self):
        pass


class ConcreteTemplate(ConcreteImplementation, Template):
    pass


class ConcreteTemplateWithSubject(SubjectMixin, ConcreteTemplate):
    pass


def test_class():
    assert (
        repr(ConcreteTemplate({"content": "hello ((name))"}))
        == 'ConcreteTemplate("hello ((name))", {})'
    )


def test_passes_through_template_attributes():
    assert ConcreteTemplate({"content": ""}).name is None
    assert (
        ConcreteTemplate({"content": "", "name": "Two week reminder"}).name
        == "Two week reminder"
    )
    assert ConcreteTemplate({"content": ""}).id is None
    assert ConcreteTemplate({"content": "", "id": "1234"}).id == "1234"
    assert ConcreteTemplate({"content": ""}).template_type is None


def test_passes_through_subject():
    assert (
        ConcreteTemplateWithSubject(
            {"content": "", "subject": "Your tax is due"}
        ).subject
        == "Your tax is due"
    )


def test_errors_for_missing_template_content():
    with pytest.raises(KeyError):
        ConcreteTemplate({})


@pytest.mark.parametrize("template", [0, 1, 2, True, False, None])
def test_errors_for_invalid_template_types(template):
    with pytest.raises(TypeError):
        ConcreteTemplate(template)


@pytest.mark.parametrize("values", [[], False])
def test_errors_for_invalid_values(values):
    with pytest.raises(TypeError):
        ConcreteTemplate({"content": ""}, values)


def test_matches_keys_to_placeholder_names():
    template = ConcreteTemplate({"content": "hello ((name))"})

    template.values = {"NAME": "Chris"}
    assert template.values == {"name": "Chris"}

    template.values = {"NAME": "Chris", "Town": "London"}
    assert template.values == {"name": "Chris", "Town": "London"}
    assert template.additional_data == {"Town"}

    template.values = None
    assert template.missing_data == ["name"]


@pytest.mark.parametrize(
    "template_content, template_subject, expected",
    [
        ("the quick brown fox", "jumps", []),
        ("the quick ((colour)) fox", "jumps", ["colour"]),
        ("the quick ((colour)) ((animal))", "jumps", ["colour", "animal"]),
        ("((colour)) ((animal)) ((colour)) ((animal))", "jumps", ["colour", "animal"]),
        ("the quick brown fox", "((colour))", ["colour"]),
        ("the quick ((colour)) ", "((animal))", ["animal", "colour"]),
        ("((colour)) ((animal)) ", "((colour)) ((animal))", ["colour", "animal"]),
        ("Dear ((name)), ((warning?? This is a warning))", "", ["name", "warning"]),
        ("((warning? one question mark))", "", ["warning? one question mark"]),
    ],
)
def test_extracting_placeholders(template_content, template_subject, expected):
    assert (
        ConcreteTemplateWithSubject(
            {"content": template_content, "subject": template_subject}
        ).placeholders
        == expected
    )


def test_random_variable_retrieve():
    template = ConcreteTemplate({"content": "content", "created_by": "now"})
    assert template.get_raw("created_by") == "now"
    assert template.get_raw("missing", default="random") == "random"
    assert template.get_raw("missing") is None


def test_compare_template():
    with patch(
        "notifications_utils.template_change.TemplateChange.__init__", return_value=None
    ) as mocked:
        old_template = ConcreteTemplate({"content": "faked"})
        new_template = ConcreteTemplate({"content": "faked"})
        old_template.compare_to(new_template)
        mocked.assert_called_once_with(old_template, new_template)
