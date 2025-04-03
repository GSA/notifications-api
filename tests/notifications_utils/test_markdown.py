import pytest

from notifications_utils.markdown import (
    notify_email_markdown,
    notify_plain_text_email_markdown,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://www.gov.uk/",
        "https://www.gov.uk/",
        "http://service.gov.uk",
        "http://service.gov.uk/blah.ext?q=a%20b%20c&order=desc#fragment",
        pytest.param(
            "http://service.gov.uk/blah.ext?q=one two three", marks=pytest.mark.xfail
        ),
    ],
)
def test_makes_links_out_of_URLs(url):
    link = '<a style="word-wrap: break-word; color: #1D70B8;" href="{}">{}</a>'.format(
        url, url
    )
    assert notify_email_markdown(url) == (
        '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
        "{}"
        "</p>"
    ).format(link)


@pytest.mark.parametrize(
    ("input", "output"),
    [
        (
            ("this is some text with a link http://example.com in the middle"),
            (
                "this is some text with a link "
                '<a style="word-wrap: break-word; color: #1D70B8;" href="http://example.com">http://example.com</a>'
                " in the middle"
            ),
        ),
        (
            ("this link is in parenthesis (http://example.com)"),
            (
                "this link is in parenthesis "
                '(<a style="word-wrap: break-word; color: #1D70B8;" href="http://example.com">http://example.com</a>)'
            ),
        ),
    ],
)
def test_makes_links_out_of_URLs_in_context(input, output):
    assert notify_email_markdown(input) == (
        '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
        "{}"
        "</p>"
    ).format(output)


@pytest.mark.parametrize(
    "url",
    [
        "example.com",
        "www.example.com",
        "ftp://example.com",
        "test@example.com",
        "mailto:test@example.com",
        '<a href="https://example.com">Example</a>',
    ],
)
def test_doesnt_make_links_out_of_invalid_urls(url):
    assert notify_email_markdown(url) == (
        '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
        "{}"
        "</p>"
    ).format(url)


# TODO broke after mistune upgrade 0.8.4->3.1.3
# def test_handles_placeholders_in_urls():
#     assert notify_email_markdown(
#         "http://example.com/?token=<span class='placeholder'>((token))</span>&key=1"
#     ) == (
#         '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
#         '<a style="word-wrap: break-word; color: #1D70B8;" href="http://example.com/?token=">'
#         "http://example.com/?token="
#         "</a>"
#         "<span class='placeholder'>((token))</span>&amp;key=1"
#         "</p>"
#     )


# TODO broke after mistune upgrade 0.8.4->3.1.3
# @pytest.mark.parametrize(
#     ("url", "expected_html", "expected_html_in_template"),
#     [
#         (
#             """https://example.com"onclick="alert('hi')""",
#             """<a style="word-wrap: break-word; color: #1D70B8;" href="https://example.com">https://example.com</a>"onclick="alert('hi')""",  # noqa
#             """<a style="word-wrap: break-word; color: #1D70B8;" href="https://example.com">https://example.com</a>"onclick="alert('hi‘)""",  # noqa
#         ),
#         (
#             """https://example.com"style='text-decoration:blink'""",
#             """<a style="word-wrap: break-word; color: #1D70B8;" href="https://example.com%22style=%27text-decoration:blink">https://example.com"style='text-decoration:blink</a>'""",  # noqa
#             """<a style="word-wrap: break-word; color: #1D70B8;" href="https://example.com%22style=%27text-decoration:blink">https://example.com"style='text-decoration:blink</a>’""",  # noqa
#         ),
#     ],
# )
# def test_URLs_get_escaped(url, expected_html, expected_html_in_template):
#     assert notify_email_markdown(url) == (
#         '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
#         "{}"
#         "</p>"
#     ).format(expected_html)
# TODO need template expertise to fix these
# assert expected_html_in_template in str(
#     HTMLEmailTemplate(
#         {
#             "content": url,
#             "subject": "",
#             "template_type": "email",
#         }
#     )
# )


@pytest.mark.parametrize(
    ("markdown_function", "expected_output"),
    [
        (
            notify_email_markdown,
            (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
                '<a style="word-wrap: break-word; color: #1D70B8;" href="https://example.com">'
                "https://example.com"
                "</a>"
                "</p>"
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
                "Next paragraph"
                "</p>"
            ),
        ),
        (
            notify_plain_text_email_markdown,
            ("\n" "\nhttps://example.com" "\n" "\nNext paragraph"),
        ),
    ],
)
def test_preserves_whitespace_when_making_links(markdown_function, expected_output):
    assert (
        markdown_function("https://example.com\n" "\n" "Next paragraph")
        == expected_output
    )


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (notify_letter_preview_markdown, 'print("hello")'),
        (notify_email_markdown, 'print("hello")'),
        (notify_plain_text_email_markdown, 'print("hello")'),
    ],
)
def test_block_code(markdown_function, expected):
    assert markdown_function('```\nprint("hello")\n```') == expected


# TODO broke in mistune upgrade 0.8.4 -> 3.1.3
# @pytest.mark.parametrize(
#     ("markdown_function", "expected"),
#     [
#         # (notify_letter_preview_markdown, ("<p>inset text</p>")),
#         (
#             notify_email_markdown,
#             (
#                 "<blockquote "
#                 'style="Margin: 0 0 20px 0; border-left: 10px solid #B1B4B6;'
#                 "padding: 15px 0 0.1px 15px; font-size: 19px; line-height: 25px;"
#                 '">'
#                 '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">inset text</p>'
#                 "</blockquote>"
#             ),
#         ),
#         (
#             notify_plain_text_email_markdown,
#             ("\n" "\ninset text"),
#         ),
#     ],
# )
# def test_block_quote(markdown_function, expected):
#     assert markdown_function("^ inset text") == expected


@pytest.mark.parametrize(
    "heading",
    [
        "# heading",
        # "#heading",  # This worked in mistune 0.8.4 but is not correct markdown syntax
    ],
)
@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (notify_letter_preview_markdown, "<h2>heading</h2>\n"),
        (
            notify_email_markdown,
            (
                '<h2 style="Margin: 0 0 20px 0; padding: 0; font-size: 27px; '
                'line-height: 35px; font-weight: bold; color: #0B0C0C;">'
                "heading"
                "</h2>"
            ),
        ),
        (
            notify_plain_text_email_markdown,
            (
                "\n"
                "\n"
                "\nheading"
                "\n-----------------------------------------------------------------"
            ),
        ),
    ],
)
def test_level_1_header(markdown_function, heading, expected):
    assert markdown_function(heading) == expected


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (notify_letter_preview_markdown, "<p>inset text</p>"),
        (
            notify_email_markdown,
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">inset text</p>',
        ),
        (
            notify_plain_text_email_markdown,
            ("\n" "\ninset text"),
        ),
    ],
)
def test_level_2_header(markdown_function, expected):
    assert markdown_function("## inset text") == (expected)


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (
        #    notify_letter_preview_markdown,
        #    ("<p>a</p>" '<div class="page-break">&nbsp;</div>' "<p>b</p>"),
        # ),
        (
            notify_email_markdown,
            (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">a</p>'
                '<hr style="border: 0; height: 1px; background: #B1B4B6; Margin: 30px 0 30px 0;">'
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">b</p>'
            ),
        ),
        (
            notify_plain_text_email_markdown,
            (
                "\n"
                "\na"
                "\n"
                "\n================================================================="
                "\n"
                "\nb"
            ),
        ),
    ],
)
def test_hrule(markdown_function, expected):
    assert markdown_function("a\n\n***\n\nb") == expected
    assert markdown_function("a\n\n---\n\nb") == expected


# TODO broke on mistune upgrade 0.8.4->3.1.3
# @pytest.mark.parametrize(
#     ("markdown_function", "expected"),
#     [
#         # (
#         #    notify_letter_preview_markdown,
#         #    ("<ol>\n" "<li>one</li>\n" "<li>two</li>\n" "<li>three</li>\n" "</ol>\n"),
#         # ),
#         (
#             notify_email_markdown,
#             (
#                 '<table role="presentation" style="padding: 0 0 20px 0;">'
#                 "<tr>"
#                 '<td style="font-family: Helvetica, Arial, sans-serif;">'
#                 '<ol style="Margin: 0 0 0 20px; padding: 0; list-style-type: decimal;">'
#                 '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
#                 'line-height: 25px; color: #0B0C0C;">one</li>'
#                 '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
#                 'line-height: 25px; color: #0B0C0C;">two</li>'
#                 '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
#                 'line-height: 25px; color: #0B0C0C;">three</li>'
#                 "</ol>"
#                 "</td>"
#                 "</tr>"
#                 "</table>"
#             ),
#         ),
#         (
#             notify_plain_text_email_markdown,
#             ("\n" "\n1. one" "\n2. two" "\n3. three"),
#         ),
#     ],
# )
# def test_ordered_list(markdown_function, expected):
#     assert markdown_function("1. one\n" "2. two\n" "3. three\n") == expected
#     assert markdown_function("1.one\n" "2.two\n" "3.three\n") == expected


@pytest.mark.parametrize(
    "markdown",
    [
        # TODO these broke on mistune upgrade from 0.8.4 to 3.1.3
        # ("*one\n" "*two\n" "*three\n"),  # no space
        # ("* one\n" "* two\n" "* three\n"),  # single space
        # ("*  one\n" "*  two\n" "*  three\n"),  # two spaces
        # ("- one\n" "- two\n" "- three\n"),  # dash as bullet
        pytest.param(
            ("+ one\n" "+ two\n" "+ three\n"),  # plus as bullet
            marks=pytest.mark.xfail(raises=AssertionError),
        ),
        # ("• one\n" "• two\n" "• three\n"),  # bullet as bullet
    ],
)
@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (
        #    notify_letter_preview_markdown,
        #    ("<ul>\n" "<li>one</li>\n" "<li>two</li>\n" "<li>three</li>\n" "</ul>\n"),
        # ),
        (
            notify_email_markdown,
            (
                '<table role="presentation" style="padding: 0 0 20px 0;">'
                "<tr>"
                '<td style="font-family: Helvetica, Arial, sans-serif;">'
                '<ul style="Margin: 0 0 0 20px; padding: 0; list-style-type: disc;">'
                '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
                'line-height: 25px; color: #0B0C0C;">one</li>'
                '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
                'line-height: 25px; color: #0B0C0C;">two</li>'
                '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
                'line-height: 25px; color: #0B0C0C;">three</li>'
                "</ul>"
                "</td>"
                "</tr>"
                "</table>"
            ),
        ),
        (
            notify_plain_text_email_markdown,
            ("\n" "\n• one" "\n• two" "\n• three"),
        ),
    ],
)
def test_unordered_list(markdown, markdown_function, expected):
    assert markdown_function(markdown) == expected


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (
        #    notify_letter_preview_markdown,
        #    "<p>+ one</p><p>+ two</p><p>+ three</p>",
        # ),
        (
            notify_email_markdown,
            (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; '
                'line-height: 25px; color: #0B0C0C;">+ one<br />+ two<br />+ three</p>'
            ),
        ),
        (
            notify_plain_text_email_markdown,
            ("\n\n+ one" "\n+ two" "\n+ three"),
        ),
    ],
)
def test_pluses_dont_render_as_lists(markdown_function, expected):
    assert markdown_function("+ one\n" "+ two\n" "+ three\n") == expected


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (
        #    notify_letter_preview_markdown,
        #    ("<p>" "line one<br>" "line two" "</p>" "<p>" "new paragraph" "</p>"),
        # ),
        (
            notify_email_markdown,
            (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">line one<br />'
                "line two</p>"
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">new paragraph</p>'
            ),
        ),
        (
            notify_plain_text_email_markdown,
            ("\n" "\nline one" "\nline two" "\n" "\nnew paragraph"),
        ),
    ],
)
def test_paragraphs(markdown_function, expected):
    assert markdown_function("line one\n" "line two\n" "\n" "new paragraph") == expected


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (notify_letter_preview_markdown, ("<p>before</p>" "<p>after</p>")),
        (
            notify_email_markdown,
            (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">before</p>'
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">after</p>'
            ),
        ),
        (
            notify_plain_text_email_markdown,
            ("\n" "\nbefore" "\n" "\nafter"),
        ),
    ],
)
def test_multiple_newlines_get_truncated(markdown_function, expected):
    assert markdown_function("before\n\n\n\n\n\nafter") == expected


# This worked with mistune 0.8.4 but mistune 3.1.3 dropped table support
# @pytest.mark.parametrize(
#     "markdown_function",
#     [
#         #notify_letter_preview_markdown,
#         notify_email_markdown,
#         notify_plain_text_email_markdown,
#     ],
# )
# def test_table(markdown_function):
#     assert markdown_function("col | col\n" "----|----\n" "val | val\n") == ("")

# TODO broke on mistune upgrad 0.8.4->3.1.3
# @pytest.mark.parametrize(
#     ("markdown_function", "link", "expected"),
#     [
#         # (
#         #    notify_letter_preview_markdown,
#         #    "http://example.com",
#         #    "<p><strong>example.com</strong></p>",
#         # ),
#         (
#             notify_email_markdown,
#             "http://example.com",
#             (
#                 '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
#                 '<a style="word-wrap: break-word; color: #1D70B8;" href="http://example.com">http://example.com</a>'
#                 "</p>"
#             ),
#         ),
#         (
#             notify_email_markdown,
#             """https://example.com"onclick="alert('hi')""",
#             (
#                 '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
#                 '<a style="word-wrap: break-word; color: #1D70B8;" '
#                 'href="https://example.com%22onclick=%22alert%28%27hi">'
#                 'https://example.com"onclick="alert(\'hi'
#                 "</a>')"
#                 "</p>"
#             ),
#         ),
#         (
#             notify_plain_text_email_markdown,
#             "http://example.com",
#             ("\n" "\nhttp://example.com"),
#         ),
#     ],
# )
# def test_autolink(markdown_function, link, expected):
#     assert markdown_function(link) == expected


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (notify_letter_preview_markdown, "<p>variable called `thing`</p>"),
        (
            notify_email_markdown,
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">variable called `thing`</p>',  # noqa E501
        ),
        (
            notify_plain_text_email_markdown,
            "\n\nvariable called `thing`",
        ),
    ],
)
def test_codespan(markdown_function, expected):
    assert markdown_function("variable called `thing`") == expected


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (notify_letter_preview_markdown, "<p>something **important**</p>"),
        (
            notify_email_markdown,
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">something **important**</p>',  # noqa E501
        ),
        (
            notify_plain_text_email_markdown,
            "\n\nsomething **important**",
        ),
    ],
)
def test_double_emphasis(markdown_function, expected):
    assert markdown_function("something __important__") == expected


@pytest.mark.parametrize(
    ("markdown_function", "text", "expected"),
    [
        # (
        #    notify_letter_preview_markdown,
        #    "something *important*",
        #    "<p>something *important*</p>",
        # ),
        (
            notify_email_markdown,
            "something *important*",
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">something *important*</p>',  # noqa E501
        ),
        (
            notify_plain_text_email_markdown,
            "something *important*",
            "\n\nsomething *important*",
        ),
        (
            notify_plain_text_email_markdown,
            "something _important_",
            "\n\nsomething *important*",
        ),
        (
            notify_plain_text_email_markdown,
            "before*after",
            "\n\nbefore*after",
        ),
        (
            notify_plain_text_email_markdown,
            "before_after",
            "\n\nbefore_after",
        ),
    ],
)
def test_emphasis(markdown_function, text, expected):
    assert markdown_function(text) == expected


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        (
            notify_email_markdown,
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">foo ****** bar</p>',
        ),
        (
            notify_plain_text_email_markdown,
            "\n\nfoo ****** bar",
        ),
    ],
)
def test_nested_emphasis(markdown_function, expected):
    assert markdown_function("foo ****** bar") == expected


# TODO broke in mistune upgrade 0.8.4->3.1.3
# @pytest.mark.parametrize(
#     "markdown_function",
#     [
#         # notify_letter_preview_markdown,
#         notify_email_markdown,
#         notify_plain_text_email_markdown,
#     ],
# )
# def test_image(markdown_function):
#     assert markdown_function("![alt text](http://example.com/image.png)") == ("")


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (
        #    notify_letter_preview_markdown,
        #    ("<p>Example: <strong>example.com</strong></p>"),
        # ),
        (
            notify_email_markdown,
            (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; '
                'color: #0B0C0C;">'
                '<a style="word-wrap: break-word; color: #1D70B8;" href="http://example.com">Example</a>'
                "</p>"
            ),
        ),
        (
            notify_plain_text_email_markdown,
            ("\n" "\nExample: http://example.com"),
        ),
    ],
)
def test_link(markdown_function, expected):
    assert markdown_function("[Example](http://example.com)") == expected


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (
        #    notify_letter_preview_markdown,
        #    ("<p>Example: <strong>example.com</strong></p>"),
        # ),
        (
            notify_email_markdown,
            (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; '
                'color: #0B0C0C;">'
                '<a style="word-wrap: break-word; color: #1D70B8;" href="http://example.com" title="An example URL">'
                "Example"
                "</a>"
                "</p>"
            ),
        ),
        (
            notify_plain_text_email_markdown,
            ("\n" "\nExample (An example URL): http://example.com"),
        ),
    ],
)
def test_link_with_title(markdown_function, expected):
    assert (
        markdown_function('[Example](http://example.com "An example URL")') == expected
    )


@pytest.mark.parametrize(
    ("markdown_function", "expected"),
    [
        # (notify_letter_preview_markdown, "<p>~~Strike~~</p>"),
        (
            notify_email_markdown,
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">~~Strike~~</p>',
        ),
        (notify_plain_text_email_markdown, "\n\n~~Strike~~"),
    ],
)
def test_strikethrough(markdown_function, expected):
    assert markdown_function("~~Strike~~") == expected


def test_footnotes():
    # Can’t work out how to test this
    pass
