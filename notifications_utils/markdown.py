import re
from itertools import count

import mistune
from ordered_set import OrderedSet

from notifications_utils import MAGIC_SEQUENCE, magic_sequence_regex
from notifications_utils.formatters import create_sanitised_html_for_url

LINK_STYLE = "word-wrap: break-word; color: #1D70B8;"

mistune._block_quote_leading_pattern = re.compile(r"^ *\^ ?", flags=re.M)
mistune.BlockGrammar.block_quote = re.compile(r"^( *\^[^\n]+(\n[^\n]+)*\n*)+")
mistune.BlockGrammar.list_block = re.compile(
    r"^( *)([•*-]|\d+\.)[\s\S]+?"
    r"(?:"
    r"\n+(?=\1?(?:[-*_] *){3,}(?:\n+|$))"  # hrule
    r"|\n+(?=%s)"  # def links
    r"|\n+(?=%s)"  # def footnotes
    r"|\n{2,}"
    r"(?! )"
    r"(?!\1(?:[•*-]|\d+\.) )\n*"
    r"|"
    r"\s*$)"
    % (
        mistune._pure_pattern(mistune.BlockGrammar.def_links),
        mistune._pure_pattern(mistune.BlockGrammar.def_footnotes),
    )
)
mistune.BlockGrammar.list_item = re.compile(
    r"^(( *)(?:[•*-]|\d+\.)[^\n]*" r"(?:\n(?!\2(?:[•*-]|\d+\.))[^\n]*)*)", flags=re.M
)
mistune.BlockGrammar.list_bullet = re.compile(r"^ *(?:[•*-]|\d+\.)")
mistune.InlineGrammar.url = re.compile(r"""^(https?:\/\/[^\s<]+[^<.,:"')\]\s])""")

mistune.InlineLexer.default_rules = list(
    OrderedSet(mistune.InlineLexer.default_rules)
    - set(
        (
            "emphasis",
            "double_emphasis",
            "strikethrough",
            "code",
        )
    )
)
mistune.InlineLexer.inline_html_rules = list(
    set(mistune.InlineLexer.inline_html_rules)
    - set(
        (
            "emphasis",
            "double_emphasis",
            "strikethrough",
            "code",
        )
    )
)


class NotifyLetterMarkdownPreviewRenderer(mistune.Renderer):
    # TODO if we start removing the dead code detected by
    # the vulture tool (such as the parameter 'language' here)
    # it will break all the tests.  Need to do some massive
    # cleanup apparently, although it's not clear why vulture
    # only recently started detecting this.
    def block_code(self, code, language=None):  # noqa
        return code

    def block_quote(self, text):
        return text

    def header(self, text, level, raw=None):  # noqa
        if level == 1:
            return super().header(text, 2)
        return self.paragraph(text)

    def hrule(self):
        return '<div class="page-break">&nbsp;</div>'

    def paragraph(self, text):
        if text.strip():
            return "<p>{}</p>".format(text)
        return ""

    def table(self, header, body):
        return ""

    def autolink(self, link, is_email=False):
        return "<strong>{}</strong>".format(
            link.replace("http://", "").replace("https://", "")
        )

    def image(self, src, title, alt_text):  # noqa
        return ""

    def linebreak(self):
        return "<br>"

    def newline(self):
        return self.linebreak()

    def list_item(self, text):
        return "<li>{}</li>\n".format(text.strip())

    def link(self, link, title, content):
        return "{}: {}".format(content, self.autolink(link))

    def footnote_ref(self, key, index):
        return ""

    def footnote_item(self, key, text):
        return text

    def footnotes(self, text):
        return text


class NotifyEmailMarkdownRenderer(NotifyLetterMarkdownPreviewRenderer):
    def header(self, text, level, raw=None):  # noqa
        if level == 1:
            return (
                '<h2 style="Margin: 0 0 20px 0; padding: 0; '
                'font-size: 27px; line-height: 35px; font-weight: bold; color: #0B0C0C;">'
                "{}"
                "</h2>"
            ).format(text)
        return self.paragraph(text)

    def hrule(self):
        return '<hr style="border: 0; height: 1px; background: #B1B4B6; Margin: 30px 0 30px 0;">'

    def linebreak(self):
        return "<br />"

    def list(self, body, ordered=True):
        return (
            (
                '<table role="presentation" style="padding: 0 0 20px 0;">'
                "<tr>"
                '<td style="font-family: Helvetica, Arial, sans-serif;">'
                '<ol style="Margin: 0 0 0 20px; padding: 0; list-style-type: decimal;">'
                "{}"
                "</ol>"
                "</td>"
                "</tr>"
                "</table>"
            ).format(body)
            if ordered
            else (
                '<table role="presentation" style="padding: 0 0 20px 0;">'
                "<tr>"
                '<td style="font-family: Helvetica, Arial, sans-serif;">'
                '<ul style="Margin: 0 0 0 20px; padding: 0; list-style-type: disc;">'
                "{}"
                "</ul>"
                "</td>"
                "</tr>"
                "</table>"
            ).format(body)
        )

    def list_item(self, text):
        return (
            '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
            'line-height: 25px; color: #0B0C0C;">'
            "{}"
            "</li>"
        ).format(text.strip())

    def paragraph(self, text):
        if text.strip():
            return (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">{}</p>'
            ).format(text)
        return ""

    def block_quote(self, text):
        return (
            "<blockquote "
            'style="Margin: 0 0 20px 0; border-left: 10px solid #B1B4B6;'
            'padding: 15px 0 0.1px 15px; font-size: 19px; line-height: 25px;"'
            ">"
            "{}"
            "</blockquote>"
        ).format(text)

    def link(self, link, title, content):
        return ('<a style="{}"{}{}>{}</a>').format(
            LINK_STYLE,
            ' href="{}"'.format(link),
            ' title="{}"'.format(title) if title else "",
            content,
        )

    def autolink(self, link, is_email=False):
        if is_email:
            return link
        return create_sanitised_html_for_url(link, style=LINK_STYLE)


class NotifyPlainTextEmailMarkdownRenderer(NotifyEmailMarkdownRenderer):
    COLUMN_WIDTH = 65

    def header(self, text, level, raw=None):  # noqa
        if level == 1:
            return "".join(
                (
                    self.linebreak() * 3,
                    text,
                    self.linebreak(),
                    "-" * self.COLUMN_WIDTH,
                )
            )
        return self.paragraph(text)

    def hrule(self):
        return self.paragraph("=" * self.COLUMN_WIDTH)

    def linebreak(self):
        return "\n"

    def list(self, body, ordered=True):
        def _get_list_marker():
            decimal = count(1)
            return lambda _: "{}.".format(next(decimal)) if ordered else "•"

        return "".join(
            (
                self.linebreak(),
                re.sub(
                    magic_sequence_regex,
                    _get_list_marker(),
                    body,
                ),
            )
        )

    def list_item(self, text):
        return "".join(
            (
                self.linebreak(),
                MAGIC_SEQUENCE,
                " ",
                text.strip(),
            )
        )

    def paragraph(self, text):
        if text.strip():
            return "".join(
                (
                    self.linebreak() * 2,
                    text,
                )
            )
        return ""

    def block_quote(self, text):
        return text

    def link(self, link, title, content):
        return "".join(
            (
                content,
                " ({})".format(title) if title else "",
                ": ",
                link,
            )
        )

    def autolink(self, link, is_email=False):  # noqa
        return link


class NotifyEmailPreheaderMarkdownRenderer(NotifyPlainTextEmailMarkdownRenderer):
    def header(self, text, level, raw=None):  # noqa
        return self.paragraph(text)

    def hrule(self):
        return ""

    def link(self, link, title, content):
        return "".join(
            (
                content,
                " ({})".format(title) if title else "",
            )
        )


notify_email_markdown = mistune.Markdown(
    renderer=NotifyEmailMarkdownRenderer(),
    hard_wrap=True,
    use_xhtml=False,
)
notify_plain_text_email_markdown = mistune.Markdown(
    renderer=NotifyPlainTextEmailMarkdownRenderer(),
    hard_wrap=True,
)
notify_email_preheader_markdown = mistune.Markdown(
    renderer=NotifyEmailPreheaderMarkdownRenderer(),
    hard_wrap=True,
)
notify_letter_preview_markdown = mistune.Markdown(
    renderer=NotifyLetterMarkdownPreviewRenderer(),
    hard_wrap=True,
    use_xhtml=False,
)
