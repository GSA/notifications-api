import pytest

from notifications_utils.template_change import TemplateChange
from tests.notifications_utils.test_base_template import ConcreteTemplate


@pytest.mark.parametrize(
    "old_template, new_template, should_differ",
    [
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            False,
        ),
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((3)) ((2)) ((1))"}),
            False,
        ),
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((1)) ((1)) ((2)) ((2)) ((3)) ((3))"}),
            False,
        ),
        (
            ConcreteTemplate({"content": "((1))"}),
            ConcreteTemplate({"content": "((1)) ((2))"}),
            True,
        ),
        (
            ConcreteTemplate({"content": "((1)) ((2))"}),
            ConcreteTemplate({"content": "((1))"}),
            True,
        ),
        (
            ConcreteTemplate({"content": "((a)) ((b))"}),
            ConcreteTemplate({"content": "((A)) (( B_ ))"}),
            False,
        ),
    ],
)
def test_checking_for_difference_between_templates(
    old_template, new_template, should_differ
):
    assert (
        TemplateChange(old_template, new_template).has_different_placeholders
        == should_differ
    )


@pytest.mark.parametrize(
    "old_template, new_template, placeholders_added",
    [
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            set(),
        ),
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((1)) ((1)) ((2)) ((2)) ((3)) ((3))"}),
            set(),
        ),
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((1))"}),
            set(),
        ),
        (
            ConcreteTemplate({"content": "((1))"}),
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            set(["2", "3"]),
        ),
        (
            ConcreteTemplate({"content": "((a))"}),
            ConcreteTemplate({"content": "((A)) ((B)) ((C))"}),
            set(["B", "C"]),
        ),
    ],
)
def test_placeholders_added(old_template, new_template, placeholders_added):
    assert (
        TemplateChange(old_template, new_template).placeholders_added
        == placeholders_added
    )


@pytest.mark.parametrize(
    "old_template, new_template, placeholders_removed",
    [
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            set(),
        ),
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((1)) ((1)) ((2)) ((2)) ((3)) ((3))"}),
            set(),
        ),
        (
            ConcreteTemplate({"content": "((1))"}),
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            set(),
        ),
        (
            ConcreteTemplate({"content": "((1)) ((2)) ((3))"}),
            ConcreteTemplate({"content": "((1))"}),
            set(["2", "3"]),
        ),
        (
            ConcreteTemplate({"content": "((a)) ((b)) ((c))"}),
            ConcreteTemplate({"content": "((A))"}),
            set(["b", "c"]),
        ),
    ],
)
def test_placeholders_removed(old_template, new_template, placeholders_removed):
    assert (
        TemplateChange(old_template, new_template).placeholders_removed
        == placeholders_removed
    )


def test_ordering_of_placeholders_is_preserved():
    before = ConcreteTemplate({"content": "((dog)) ((cat)) ((rat))"})
    after = ConcreteTemplate({"content": "((platypus)) ((echidna)) ((quokka))"})
    change = TemplateChange(before, after)
    assert change.placeholders_removed == ["dog", "cat", "rat"] == before.placeholders
    assert (
        change.placeholders_added
        == ["platypus", "echidna", "quokka"]
        == after.placeholders
    )
