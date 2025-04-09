import pytest
from markupsafe import Markup

from notifications_utils.formatters import (
    autolink_urls,
    escape_html,
    formatted_list,
    make_quotes_smart,
    normalise_whitespace,
    remove_smart_quotes_from_email_addresses,
    remove_whitespace_before_punctuation,
    replace_hyphens_with_en_dashes,
    sms_encode,
    strip_all_whitespace,
    strip_and_remove_obscure_whitespace,
    strip_unsupported_characters,
    unlink_govuk_escaped,
)
from notifications_utils.template import (
    HTMLEmailTemplate,
    PlainTextEmailTemplate,
    SMSMessageTemplate,
    SMSPreviewTemplate,
)


@pytest.mark.parametrize(
    ("url", "expected_html"),
    [
        (
            """https://example.com/"onclick="alert('hi')""",
            """<a class="govuk-link govuk-link--no-visited-state" href="https://example.com/%22onclick=%22alert%28%27hi%27%29">https://example.com/"onclick="alert('hi')</a>""",  # noqa
        ),
        (
            """https://example.com/"style='text-decoration:blink'""",
            """<a class="govuk-link govuk-link--no-visited-state" href="https://example.com/%22style=%27text-decoration:blink%27">https://example.com/"style='text-decoration:blink'</a>""",  # noqa
        ),
    ],
)
def test_URLs_get_escaped_in_sms(url, expected_html):
    assert expected_html in str(
        SMSPreviewTemplate({"content": url, "template_type": "sms"})
    )


def test_HTML_template_has_URLs_replaced_with_links():
    assert (
        '<a style="word-wrap: break-word; color: #1D70B8;" href="https://service.example.com/accept_invite/a1b2c3d4">'
        "https://service.example.com/accept_invite/a1b2c3d4"
        "</a>"
    ) in str(
        HTMLEmailTemplate(
            {
                "content": (
                    "You’ve been invited to a service. Click this link:\n"
                    "https://service.example.com/accept_invite/a1b2c3d4\n"
                    "\n"
                    "Thanks\n"
                ),
                "subject": "",
                "template_type": "email",
            }
        )
    )


def test_escaping_govuk_in_email_templates():
    template_content = "GOV.UK"
    expected = "GOV.\u200bUK"
    assert unlink_govuk_escaped(template_content) == expected
    template_json = {
        "content": template_content,
        "subject": "",
        "template_type": "email",
    }
    assert expected in str(PlainTextEmailTemplate(template_json))
    assert expected in str(HTMLEmailTemplate(template_json))


@pytest.mark.parametrize(
    ("template_content", "expected"),
    [
        # Cases that we add the breaking space
        ("GOV.UK", "GOV.\u200bUK"),
        ("gov.uk", "gov.\u200buk"),
        (
            "content with space infront GOV.UK",
            "content with space infront GOV.\u200bUK",
        ),
        ("content with tab infront\tGOV.UK", "content with tab infront\tGOV.\u200bUK"),
        (
            "content with newline infront\nGOV.UK",
            "content with newline infront\nGOV.\u200bUK",
        ),
        ("*GOV.UK", "*GOV.\u200bUK"),
        ("#GOV.UK", "#GOV.\u200bUK"),
        ("^GOV.UK", "^GOV.\u200bUK"),
        (" #GOV.UK", " #GOV.\u200bUK"),
        ("GOV.UK with CONTENT after", "GOV.\u200bUK with CONTENT after"),
        ("#GOV.UK with CONTENT after", "#GOV.\u200bUK with CONTENT after"),
        # Cases that we don't add the breaking space
        ("https://gov.uk", "https://gov.uk"),
        ("https://www.gov.uk", "https://www.gov.uk"),
        ("www.gov.uk", "www.gov.uk"),
        ("WWW.GOV.UK", "WWW.GOV.UK"),
        ("WWW.GOV.UK.", "WWW.GOV.UK."),
        (
            "https://www.gov.uk/?utm_source=gov.uk",
            "https://www.gov.uk/?utm_source=gov.uk",
        ),
        ("mygov.uk", "mygov.uk"),
        ("www.this-site-is-not-gov.uk", "www.this-site-is-not-gov.uk"),
        (
            "www.gov.uk?websites=bbc.co.uk;gov.uk;nsh.scot",
            "www.gov.uk?websites=bbc.co.uk;gov.uk;nsh.scot",
        ),
        ("reply to: xxxx@xxx.gov.uk", "reply to: xxxx@xxx.gov.uk"),
        ("southwark.gov.uk", "southwark.gov.uk"),
        ("data.gov.uk", "data.gov.uk"),
        ("gov.uk/foo", "gov.uk/foo"),
        ("*GOV.UK/foo", "*GOV.UK/foo"),
        ("#GOV.UK/foo", "#GOV.UK/foo"),
        ("^GOV.UK/foo", "^GOV.UK/foo"),
        ("gov.uk#departments-and-policy", "gov.uk#departments-and-policy"),
        # Cases that we know currently aren't supported by our regex and have a non breaking space added when they
        # shouldn't however, we accept the fact that our regex isn't perfect as we think the chance of a user using a
        # URL like this in their content is very small.
        # We document these edge cases here
        pytest.param("gov.uk.com", "gov.uk.com", marks=pytest.mark.xfail),
        pytest.param("gov.ukandi.com", "gov.ukandi.com", marks=pytest.mark.xfail),
        pytest.param("gov.uks", "gov.uks", marks=pytest.mark.xfail),
    ],
)
def test_unlink_govuk_escaped(template_content, expected):
    assert unlink_govuk_escaped(template_content) == expected


@pytest.mark.parametrize(
    ("prefix", "body", "expected"),
    [
        ("a", "b", "a: b"),
        (None, "b", "b"),
    ],
)
def test_sms_message_adds_prefix(prefix, body, expected):
    template = SMSMessageTemplate({"content": body, "template_type": "sms"})
    template.prefix = prefix
    template.sender = None
    assert str(template) == expected


def test_sms_preview_adds_newlines():
    template = SMSPreviewTemplate(
        {
            "content": """
        the
        quick

        brown fox
    """,
            "template_type": "sms",
        }
    )
    template.prefix = None
    template.sender = None
    assert "<br>" in str(template)


def test_sms_encode(mocker):
    sanitise_mock = mocker.patch("notifications_utils.formatters.SanitiseSMS")
    assert sms_encode("foo") == sanitise_mock.encode.return_value
    sanitise_mock.encode.assert_called_once_with("foo")


@pytest.mark.parametrize(
    ("items", "kwargs", "expected_output"),
    [
        ([1], {}, "‘1’"),
        ([1, 2], {}, "‘1’ and ‘2’"),
        ([1, 2, 3], {}, "‘1’, ‘2’ and ‘3’"),
        ([1, 2, 3], {"prefix": "foo", "prefix_plural": "bar"}, "bar ‘1’, ‘2’ and ‘3’"),
        ([1], {"prefix": "foo", "prefix_plural": "bar"}, "foo ‘1’"),
        ([1, 2, 3], {"before_each": "a", "after_each": "b"}, "a1b, a2b and a3b"),
        ([1, 2, 3], {"conjunction": "foo"}, "‘1’, ‘2’ foo ‘3’"),
        (["&"], {"before_each": "<i>", "after_each": "</i>"}, "<i>&amp;</i>"),
        (
            [1, 2, 3],
            {"before_each": "<i>", "after_each": "</i>"},
            "<i>1</i>, <i>2</i> and <i>3</i>",
        ),
    ],
)
def test_formatted_list(items, kwargs, expected_output):
    assert formatted_list(items, **kwargs) == expected_output


def test_formatted_list_returns_markup():
    assert isinstance(formatted_list([0]), Markup)


def test_bleach_doesnt_try_to_make_valid_html_before_cleaning():
    assert escape_html("<to cancel daily cat facts reply 'cancel'>") == (
        "&lt;to cancel daily cat facts reply 'cancel'&gt;"
    )


@pytest.mark.parametrize(
    ("content", "expected_escaped"),
    [
        ("&?a;", "&amp;?a;"),
        ("&>a;", "&amp;&gt;a;"),
        ("&*a;", "&amp;*a;"),
        ("&a?;", "&amp;a?;"),
        ("&x?xa;", "&amp;x?xa;"),
        # We need to be careful that query arguments don’t get turned into entities
        ("&timestamp=&times;", "&amp;timestamp=×"),
        ("&times=1,2,3", "&amp;times=1,2,3"),
        # &minus; should have a trailing semicolon according to the HTML5
        # spec but &micro doesn’t need one
        ("2&minus;1", "2−1"),
        ("200&micro;g", "200µg"),
        # …we ignore it when it’s ambiguous
        ("2&minus1", "2&amp;minus1"),
        ("200&microg", "200&amp;microg"),
        # …we still ignore when there’s a space afterwards
        ("2 &minus 1", "2 &amp;minus 1"),
        ("200&micro g", "200&amp;micro g"),
        # Things which aren’t real entities are ignored, not removed
        ("This &isnotarealentity;", "This &amp;isnotarealentity;"),
        # We let users use &nbsp; for backwards compatibility
        ("Before&nbsp;after", "Before&nbsp;after"),
        # We let users use &amp; because it’s often pasted in URLs
        ("?a=1&amp;b=2", "?a=1&amp;b=2"),
        # We let users use &lpar; and &rpar; because otherwise it’s
        # impossible to put brackets in the body of conditional placeholders
        ("((var??&lpar;in brackets&rpar;))", "((var??&lpar;in brackets&rpar;))"),
    ],
)
def test_escaping_html_entities(
    content,
    expected_escaped,
):
    assert escape_html(content) == expected_escaped


@pytest.mark.parametrize(
    ("dirty", "clean"),
    [
        (
            "Hello ((name)) ,\n\nThis is a message",
            "Hello ((name)),\n\nThis is a message",
        ),
        ("Hello Jo ,\n\nThis is a message", "Hello Jo,\n\nThis is a message"),
        (
            "\n   \t    , word",
            "\n, word",
        ),
    ],
)
def test_removing_whitespace_before_commas(dirty, clean):
    assert remove_whitespace_before_punctuation(dirty) == clean


@pytest.mark.parametrize(
    ("dirty", "clean"),
    [
        (
            "Hello ((name)) .\n\nThis is a message",
            "Hello ((name)).\n\nThis is a message",
        ),
        ("Hello Jo .\n\nThis is a message", "Hello Jo.\n\nThis is a message"),
        (
            "\n   \t    . word",
            "\n. word",
        ),
    ],
)
def test_removing_whitespace_before_full_stops(dirty, clean):
    assert remove_whitespace_before_punctuation(dirty) == clean


@pytest.mark.parametrize(
    ("dumb", "smart"),
    [
        (
            """And I said, "what about breakfast at Tiffany's"?""",
            """And I said, “what about breakfast at Tiffany’s”?""",
        ),
        (
            """
            <a href="http://example.com?q='foo'">http://example.com?q='foo'</a>
        """,
            """
            <a href="http://example.com?q='foo'">http://example.com?q='foo'</a>
        """,
        ),
    ],
)
def test_smart_quotes(dumb, smart):
    assert make_quotes_smart(dumb) == smart


@pytest.mark.parametrize(
    ("nasty", "nice"),
    [
        (
            (
                "The en dash - always with spaces in running text when, as "
                "discussed in this section, indicating a parenthesis or "
                "pause - and the spaced em dash both have a certain "
                "technical advantage over the unspaced em dash. "
            ),
            (
                "The en dash \u2013 always with spaces in running text when, as "
                "discussed in this section, indicating a parenthesis or "
                "pause \u2013 and the spaced em dash both have a certain "
                "technical advantage over the unspaced em dash. "
            ),
        ),
        (
            "double -- dash",
            "double \u2013 dash",
        ),
        (
            "triple --- dash",
            "triple \u2013 dash",
        ),
        (
            "quadruple ---- dash",
            "quadruple ---- dash",
        ),
        (
            "em — dash",
            "em – dash",
        ),
        (
            "already\u0020–\u0020correct",  # \u0020 is a normal space character
            "already\u0020–\u0020correct",
        ),
        (
            "2004-2008",
            "2004-2008",  # no replacement
        ),
    ],
)
def test_en_dashes(nasty, nice):
    assert replace_hyphens_with_en_dashes(nasty) == nice


def test_unicode_dash_lookup():
    en_dash_replacement_sequence = "\u0020\u2013"
    hyphen = "-"
    en_dash = "–"
    space = " "
    non_breaking_space = " "
    assert en_dash_replacement_sequence == space + en_dash
    assert non_breaking_space not in en_dash_replacement_sequence
    assert hyphen not in en_dash_replacement_sequence


@pytest.mark.parametrize(
    "value",
    [
        "bar",
        " bar ",
        """
        \t    bar
    """,
        " \u180e\u200b \u200c bar \u200d \u2060\ufeff ",
    ],
)
def test_strip_all_whitespace(value):
    assert strip_all_whitespace(value) == "bar"


@pytest.mark.parametrize(
    "value",
    [
        "notifications-email",
        "  \tnotifications-email \x0c ",
        "\rn\u200coti\u200dfi\u200bcati\u2060ons-\u180eemai\ufeffl\ufeff",
    ],
)
def test_strip_and_remove_obscure_whitespace(value):
    assert strip_and_remove_obscure_whitespace(value) == "notifications-email"


def test_strip_and_remove_obscure_whitespace_only_removes_normal_whitespace_from_ends():
    sentence = "   words \n over multiple lines with \ttabs\t   "
    assert (
        strip_and_remove_obscure_whitespace(sentence)
        == "words \n over multiple lines with \ttabs"
    )


def test_remove_smart_quotes_from_email_addresses():
    assert (
        remove_smart_quotes_from_email_addresses(
            """
        line one’s quote
        first.o’last@example.com is someone’s email address
        line ‘three’
    """
        )
        == (
            """
        line one’s quote
        first.o'last@example.com is someone’s email address
        line ‘three’
    """
        )
    )


def test_strip_unsupported_characters():
    assert strip_unsupported_characters("line one\u2028line two") == (
        "line oneline two"
    )


@pytest.mark.parametrize(
    "value",
    [
        "\u200c Your tax   is\ndue\n\n",
        "  Your tax is due  ",
        # Non breaking spaces replaced by single spaces
        "\u00a0Your\u00a0tax\u00a0 is\u00a0\u00a0due\u00a0",
        # zero width spaces are removed
        "\u180eYour \u200btax\u200c is \u200d\u2060due \ufeff",
        # tabs are replaced by single spaces
        "\tYour tax\tis due  ",
    ],
)
def test_normalise_whitespace(value):
    assert normalise_whitespace(value) == "Your tax is due"


@pytest.mark.parametrize(
    ("content", "expected_html"),
    [
        (
            "http://example.com",
            '<a href="http://example.com">http://example.com</a>',
        ),
        (
            "https://example.com",
            '<a href="https://example.com">https://example.com</a>',
        ),
        (
            "example.com",
            '<a href="http://example.com">example.com</a>',
        ),
        (
            "www.foo.bar.example.com",
            '<a href="http://www.foo.bar.example.com">www.foo.bar.example.com</a>',
        ),
        (
            "example.com/",
            '<a href="http://example.com/">example.com/</a>',
        ),
        (
            "www.foo.bar.example.com/",
            '<a href="http://www.foo.bar.example.com/">www.foo.bar.example.com/</a>',
        ),
        (
            "example.com/foo",
            '<a href="http://example.com/foo">example.com/foo</a>',
        ),
        (
            "example.com?foo",
            '<a href="http://example.com?foo">example.com?foo</a>',
        ),
        (
            "example.com#foo",
            '<a href="http://example.com#foo">example.com#foo</a>',
        ),
        (
            "Go to gov.uk/example.",
            "Go to " '<a href="http://gov.uk/example">gov.uk/example</a>.',
        ),
        (
            "Go to gov.uk/example:",
            "Go to " '<a href="http://gov.uk/example">gov.uk/example</a>:',
        ),
        (
            "Go to gov.uk/example;",
            "Go to " '<a href="http://gov.uk/example;">gov.uk/example;</a>',
        ),
        (
            "(gov.uk/example)",
            "(" '<a href="http://gov.uk/example">gov.uk/example</a>)',
        ),
        (
            "(gov.uk/example)...",
            "(" '<a href="http://gov.uk/example">gov.uk/example</a>)...',
        ),
        (
            "(gov.uk/example.)",
            "(" '<a href="http://gov.uk/example">gov.uk/example</a>.)',
        ),
        (
            "(see example.com/foo_(bar))",
            "(see "
            '<a href="http://example.com/foo_%28bar%29">example.com/foo_(bar)</a>)',
        ),
        (
            "example.com/foo(((((((bar",
            '<a href="http://example.com/foo%28%28%28%28%28%28%28bar">example.com/foo(((((((bar</a>',
        ),
        (
            "government website (gov.uk). Other websites…",
            "government website ("
            '<a href="http://gov.uk">gov.uk</a>). Other websites…',
        ),
        (
            "[gov.uk/example]",
            "[" '<a href="http://gov.uk/example">gov.uk/example</a>]',
        ),
        (
            "gov.uk/foo, gov.uk/bar",
            '<a href="http://gov.uk/foo">gov.uk/foo</a>, '
            '<a href="http://gov.uk/bar">gov.uk/bar</a>',
        ),
        (
            "<p>gov.uk/foo</p>",
            "<p>" '<a href="http://gov.uk/foo">gov.uk/foo</a></p>',
        ),
        (
            "gov.uk?foo&amp;",
            '<a href="http://gov.uk?foo&amp;">gov.uk?foo&amp;</a>',
        ),
        (
            "a .service.gov.uk domain",
            "a .service.gov.uk domain",
        ),
        (
            'http://foo.com/"bar"?x=1#2',
            '<a href="http://foo.com/%22bar%22?x=1#2">http://foo.com/"bar"?x=1#2</a>',
        ),
        (
            "firstname.lastname@example.com",
            "firstname.lastname@example.com",
        ),
        (
            "with-subdomain@test.example.com",
            "with-subdomain@test.example.com",
        ),
    ],
)
def test_autolink_urls_matches_correctly(content, expected_html):
    assert autolink_urls(content) == expected_html


@pytest.mark.parametrize(
    ("extra_kwargs", "expected_html"),
    [
        (
            {},
            '<a href="http://example.com">http://example.com</a>',
        ),
        (
            {
                "classes": "govuk-link",
            },
            '<a class="govuk-link" href="http://example.com">http://example.com</a>',
        ),
    ],
)
def test_autolink_urls_applies_correct_attributes(extra_kwargs, expected_html):
    assert autolink_urls("http://example.com", **extra_kwargs) == expected_html


@pytest.mark.parametrize(
    "content", ["without link", "with link to https://example.com"]
)
def test_autolink_urls_returns_markup(content):
    assert isinstance(autolink_urls(content), Markup)
