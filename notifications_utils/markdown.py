import html
import re

import mistune
from flask import current_app

from notifications_utils.formatters import create_sanitised_html_for_url

LINK_STYLE = "word-wrap: break-word; color: #1D70B8;"


def escape_plus_lists(markdown_text):
    return re.sub(r"(?m)^(\+)(?=\s)", r"\\\1", markdown_text)


def autolinkify(text):
    # url_pattern = re.compile(r"""(?<!\]\()(?<!["'])\b(https?://[^\s<>()]+)""")
    url_pattern = re.compile(
        r"""(?<!\]\()
        (?<!href=["'])
        \b(https?://[^\s<>"')\]]+)""",
        re.VERBOSE,
    )

    def replacer(match):
        url = match.group(0)
        return f"[{url}]({url})"

    return url_pattern.sub(replacer, text)


class EmailRenderer(mistune.HTMLRenderer):

    def table(self, header, body):
        return ""

    def table_row(self, content):
        return ""

    def table_cell(self, content, **kwargs):
        return ""

    def heading(self, text, level):
        if level == 1:
            return (
                '<h2 style="Margin: 0 0 20px 0; padding: 0; '
                'font-size: 27px; line-height: 35px; font-weight: bold; color: #0B0C0C;">'
                f"{text}</h2>"
            )
        return self.paragraph(text)

    def paragraph(self, text):
        if text.strip():
            text = html.unescape(text)
            return (
                '<p style="Margin: 0 0 20px 0; font-size: 19px; '
                'line-height: 25px; color: #0B0C0C;">' + text + "</p>"
            )

    def emphasis(self, text):
        return f"*{text}*"

    def strong(self, text):
        return f"**{text}**"

    def block_code(self, code, info=None):
        return code.strip()

    def block_quote(self, text):
        return (
            '<blockquote style="Margin: 0 0 20px 0; border-left: 10px solid #B1B4B6; '
            'padding: 15 px 0 0.1px 15 px; font-size: 19px; line-height: 25px;">'
            f"{text}</blockquote>"
        )

    def thematic_break(self):
        return '<hr style="border: 0; height: 1px; background: #B1B4B6; Margin: 30px 0 30px 0;">'

    def codespan(self, text):
        return f"`{text}`"

    def linebreak(self):
        return "<br />"

    def newline(self):
        return self.linebreak()

    def list(self, text, ordered, level=None, **kwargs):
        tag = "ol" if ordered else "ul"
        style = "list-style-type: decimal;" if ordered else "list-style-type: disc;"
        return (
            '<table role="presentation" style="padding 0 0 20px 0;">'
            '<tr><td style="font-family: Helvetica, Arial, sans-serif;">'
            f'<{tag} style="Margin: 0 0 0 20px; padding: 0; {style}">{text}</{tag}>'
            "</td></tr></table>"
        )

    def list_item(self, text, level=None):
        return (
            '<li style="Margin: 5px 0 5px; padding: 0 0 0 5px; font-size: 19px;'
            'line-height: 25px; color: #0B0C0C;">' + text.strip() + "</li>"
        )

    def link(self, link=None, text=None, title=None, url=None, **kwargs):

        href = html.escape(
            url or (link if link and link.startswith("http://", "https://") else "")
        )
        display_text = text or link or href or ""
        title_attr = f' title="{title}"' if title else ""
        return f'<a style="{LINK_STYLE}" href="{href}"{title_attr}>{display_text}</a>'

    def autolink(self, link, is_email=False):  # noqa

        return create_sanitised_html_for_url(link, style=LINK_STYLE)

    def image(self, src, alt="", title=None, url=None):  # noqa
        current_app.logger.debug(f"src={src} alt={alt} title={title} url={url}")
        return ""

    def strikethrough(self, text):
        return (
            '<p style="Margin: 0 0 20px 0; font-size: 19px; line-height: 25px; color: #0B0C0C;">'
            f"~~{text}~~"
            "</p>"
        )


class PlainTextRenderer(mistune.HTMLRenderer):
    COLUMN_WIDTH = 65

    def heading(self, text, level):
        if level == 1:
            return f"\n\n\n{text}\n{'-' * self.COLUMN_WIDTH}"
        return self.paragraph(text)

    def paragraph(self, text):
        if text.strip():
            return f"\n\n{text}"
        return ""

    def thematic_break(self):
        return f"\n\n{'=' * self.COLUMN_WIDTH}"

    def block_quote(self, text):
        return text

    def block_code(self, code, info=None):
        return code.strip()

    def linebreak(self):
        return "\n"

    def list(self, text, ordered, level=None, **kwargs):

        if ordered is True:
            text = text.replace("•", "1.", 1)
            text = text.replace("•", "2.", 1)
            text = text.replace("•", "3.", 1)

        # print(f"LIST ordered={ordered} text={text}")
        return f"\n{text}"

    def list_item(self, text, ordered=None, level=None):
        # print(f"LIST ITEM = {text} ordered={ordered} level {level}")
        return f"\n• {text.strip()}"

    def link(self, link=None, text=None, title=None, url=None, **kwargs):
        display_text = text or link or url or ""
        href = url or link or ""
        output = display_text
        if title:
            output += f" ({title})"
        if href:
            output += f": {href}"
        return output

    def autolink(self, link, is_email=False):
        return link

    def image(self, src, alt="", title=None, url=None):
        return ""

    def emphasis(self, text):
        return f"*{text}*"

    def strong(self, text):
        return f"**{text}**"

    def codespan(self, text):
        return f"`{text}`"

    def strikethrough(self, text):
        return f"~~{text}~~"


class PreheaderRenderer(PlainTextRenderer):

    def heading(self, text, level):
        return html.unescape(self.paragraph(text))

    def thematic_break(self):
        return ""

    def link(self, link, text=None, title=None, url=None):
        return text or link

    def image(self, src, alt="", title=None, url=None):
        current_app.logger.debug("src={src} alt={alt} title={title} url={url}")
        return ""


_notify_email_markdown = mistune.create_markdown(
    renderer=EmailRenderer(), hard_wrap=True
)
notify_email_preheader_markdown = mistune.create_markdown(renderer=PreheaderRenderer())
_notify_plain_text_email_markdown = mistune.create_markdown(
    renderer=PlainTextRenderer()
)


def notify_email_markdown(text):
    text = escape_plus_lists(text)
    return _notify_email_markdown(autolinkify(text))


def notify_plain_text_email_markdown(text):
    text = escape_plus_lists(text)
    return _notify_plain_text_email_markdown(text)
