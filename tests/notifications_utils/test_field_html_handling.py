import pytest

from notifications_utils.field import Field


@pytest.mark.parametrize(
    "content, values, expected_stripped, expected_escaped, expected_passthrough",
    [
        (
            "string <em>with</em> html",
            {},
            "string with html",
            "string &lt;em&gt;with&lt;/em&gt; html",
            "string <em>with</em> html",
        ),
        (
            "string ((<em>with</em>)) html",
            {},
            "string <span class='placeholder'>((with))</span> html",
            "string <span class='placeholder'>((&lt;em&gt;with&lt;/em&gt;))</span> html",
            "string <span class='placeholder'>((<em>with</em>))</span> html",
        ),
        (
            "string ((placeholder)) html",
            {"placeholder": "<em>without</em>"},
            "string without html",
            "string &lt;em&gt;without&lt;/em&gt; html",
            "string <em>without</em> html",
        ),
        (
            "string ((<em>conditional</em>??<em>placeholder</em>)) html",
            {},
            "string <span class='placeholder-conditional'>((conditional??</span>placeholder)) html",
            (
                "string "
                "<span class='placeholder-conditional'>"
                "((&lt;em&gt;conditional&lt;/em&gt;??</span>"
                "&lt;em&gt;placeholder&lt;/em&gt;)) "
                "html"
            ),
            (
                "string "
                "<span class='placeholder-conditional'>"
                "((<em>conditional</em>??</span>"
                "<em>placeholder</em>)) "
                "html"
            ),
        ),
        (
            "string ((conditional??<em>placeholder</em>)) html",
            {"conditional": True},
            "string placeholder html",
            "string &lt;em&gt;placeholder&lt;/em&gt; html",
            "string <em>placeholder</em> html",
        ),
        (
            "string & entity",
            {},
            "string &amp; entity",
            "string &amp; entity",
            "string & entity",
        ),
    ],
)
def test_field_handles_html(
    content, values, expected_stripped, expected_escaped, expected_passthrough
):
    assert str(Field(content, values)) == expected_stripped
    assert str(Field(content, values, html="strip")) == expected_stripped
    assert str(Field(content, values, html="escape")) == expected_escaped
    assert str(Field(content, values, html="passthrough")) == expected_passthrough
