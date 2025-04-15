import re
import string
import urllib
from html import _replace_charref, escape

import bleach
import smartypants
from markupsafe import Markup

from notifications_utils.sanitise_text import SanitiseSMS

from . import email_with_smart_quotes_regex

OBSCURE_ZERO_WIDTH_WHITESPACE = (
    "\u180e"  # Mongolian vowel separator
    "\u200b"  # zero width space
    "\u200c"  # zero width non-joiner
    "\u200d"  # zero width joiner
    "\u2060"  # word joiner
    "\ufeff"  # zero width non-breaking space
)

OBSCURE_FULL_WIDTH_WHITESPACE = "\u00a0"  # non breaking space

ALL_WHITESPACE = (
    string.whitespace + OBSCURE_ZERO_WIDTH_WHITESPACE + OBSCURE_FULL_WIDTH_WHITESPACE
)

govuk_not_a_link = re.compile(r"(^|\s)(#|\*|\^)?(GOV)\.(UK)(?!\/|\?|#)", re.IGNORECASE)

smartypants.tags_to_skip = smartypants.tags_to_skip + ["a"]

whitespace_before_punctuation = re.compile(r"[ \t]+([,\.])")

hyphens_surrounded_by_spaces = re.compile(
    r"\s+[-–—]{1,3}\s+"
)  # check three different unicode hyphens

multiple_newlines = re.compile(r"((\n)\2{2,})")

HTML_ENTITY_MAPPING = (
    ("&nbsp;", "👾🐦🥴"),
    ("&amp;", "➕🐦🥴"),
    ("&lpar;", "◀️🐦🥴"),
    ("&rpar;", "▶️🐦🥴"),
)

url = re.compile(
    r"(?i)"  # case insensitive
    r"\b(?<![\@\.])"  # match must not start with @ or . (like @test.example.com)
    r"(https?:\/\/)?"  # optional http:// or https://
    r"([\w\-]+\.{1})+"  # one or more (sub)domains
    r"([a-z]{2,63})"  # top-level domain
    r"(?!\@)\b"  # match must not end with @ (like firstname.lastname@)
    r"([/\?#][^<\s]*)?"  # start of path, query or fragment
)

more_than_two_newlines_in_a_row = re.compile(r"\n{3,}")


def unlink_govuk_escaped(message):
    return re.sub(
        govuk_not_a_link,
        r"\1\2\3" + ".\u200b" + r"\4",  # Unicode zero-width space
        message,
    )


def nl2br(value):
    return re.sub(r"\n|\r", "<br>", value.strip())


def add_prefix(body, prefix=None):
    if prefix:
        return "{}: {}".format(prefix.strip(), body)
    return body


def make_link_from_url(linked_part, *, classes=""):
    """
    Takes something which looks like a URL, works out which trailing characters shouldn’t
    be considered part of the link and returns an HTML <a> tag

    input: `http://example.com/foo_(bar)).`
    output: `<a href="http://example.com/foo_(bar)">http://example.com/foo_(bar)</a>).`
    """
    CORRESPONDING_OPENING_CHARACTER_MAP = {
        ")": "(",
        "]": "[",
        ".": None,
        ",": None,
        ":": None,
    }

    trailing_characters = ""

    while (
        last_character := linked_part[-1]
    ) in CORRESPONDING_OPENING_CHARACTER_MAP.keys():
        corresponding_opening_character = CORRESPONDING_OPENING_CHARACTER_MAP[
            last_character
        ]

        if corresponding_opening_character:
            count_opening_characters = linked_part.count(
                corresponding_opening_character
            )
            count_closing_characters = linked_part.count(last_character)
            if count_opening_characters >= count_closing_characters:
                break

        trailing_characters = linked_part[-1] + trailing_characters
        linked_part = linked_part[:-1]

    return f"{create_sanitised_html_for_url(linked_part, classes=classes)}{trailing_characters}"


def autolink_urls(value, *, classes=""):
    return Markup(
        url.sub(
            lambda match: make_link_from_url(
                match.group(0),
                classes=classes,
            ),
            value,
        )
    )


def create_sanitised_html_for_url(link, *, classes="", style=""):
    """
    takes a link and returns an a tag to that link.  does the quote/unquote dance to ensure that " quotes are escaped
    correctly to prevent xss

    input: `http://foo.com/"bar"?x=1#2`
    output: `<a style=... href="http://foo.com/%22bar%22?x=1#2">http://foo.com/"bar"?x=1#2</a>`
    """
    link_text = link

    if not link.lower().startswith("http"):
        link = f"http://{link}"

    class_attribute = f'class="{classes}" ' if classes else ""
    style_attribute = f'style="{style}" ' if style else ""

    return ('<a {}{}href="{}">{}</a>').format(
        class_attribute,
        style_attribute,
        urllib.parse.quote(urllib.parse.unquote(link), safe=":/?#=&;"),
        link_text,
    )


def prepend_subject(body, subject):
    return "# {}\n\n{}".format(subject, body)


def sms_encode(content):
    return SanitiseSMS.encode(content)


def strip_html(value):
    return bleach.clean(value, tags=[], strip=True)


"""
Re-implements html._charref but makes trailing semicolons non-optional
"""
_charref = re.compile(r"&(#[0-9]+;" r"|#[xX][0-9a-fA-F]+;" r"|[^\t\n\f <&#;]{1,32};)")


def unescape_strict(s):
    """
    Re-implements html.unescape to use our own definition of `_charref`
    """
    if "&" not in s:
        return s
    return _charref.sub(_replace_charref, s)


def escape_html(value):
    if not value:
        return value
    value = str(value)

    for entity, temporary_replacement in HTML_ENTITY_MAPPING:
        value = value.replace(entity, temporary_replacement)

    value = escape(unescape_strict(value), quote=False)

    for entity, temporary_replacement in HTML_ENTITY_MAPPING:
        value = value.replace(temporary_replacement, entity)

    return value


def url_encode_full_stops(value):
    return value.replace(".", "%2E")


def unescaped_formatted_list(
    items,
    conjunction="and",
    before_each="‘",
    after_each="’",
    separator=", ",
    prefix="",
    prefix_plural="",
):
    if prefix:
        prefix += " "
    if prefix_plural:
        prefix_plural += " "

    if len(items) == 1:
        return "{prefix}{before_each}{items[0]}{after_each}".format(**locals())
    elif items:
        formatted_items = [
            "{}{}{}".format(before_each, item, after_each) for item in items
        ]

        first_items = separator.join(formatted_items[:-1])
        last_item = formatted_items[-1]
        return ("{prefix_plural}{first_items} {conjunction} {last_item}").format(
            **locals()
        )


def formatted_list(
    items,
    conjunction="and",
    before_each="‘",
    after_each="’",
    separator=", ",
    prefix="",
    prefix_plural="",
):
    return Markup(
        unescaped_formatted_list(
            [escape_html(x) for x in items],
            conjunction,
            before_each,
            after_each,
            separator,
            prefix,
            prefix_plural,
        )
    )


def remove_whitespace_before_punctuation(value):
    return re.sub(whitespace_before_punctuation, lambda match: match.group(1), value)


def make_quotes_smart(value):
    return smartypants.smartypants(value, smartypants.Attr.q | smartypants.Attr.u)


def replace_hyphens_with_en_dashes(value):
    return re.sub(
        hyphens_surrounded_by_spaces,
        (" " "\u2013" " "),  # space  # en dash  # space
        value,
    )


def replace_hyphens_with_non_breaking_hyphens(value):
    return value.replace(
        "-",
        "\u2011",  # non-breaking hyphen
    )


def normalise_whitespace_and_newlines(value):
    return "\n".join(get_lines_with_normalised_whitespace(value))


def get_lines_with_normalised_whitespace(value):
    return [normalise_whitespace(line) for line in value.splitlines()]


def normalise_whitespace(value):
    # leading and trailing whitespace removed
    # inner whitespace with width becomes a single space
    # inner whitespace with zero width is removed
    # multiple space characters next to each other become just a single space character
    for character in OBSCURE_FULL_WIDTH_WHITESPACE:
        value = value.replace(character, " ")

    for character in OBSCURE_ZERO_WIDTH_WHITESPACE:
        value = value.replace(character, "")

    return " ".join(value.split())


def normalise_multiple_newlines(value):
    return more_than_two_newlines_in_a_row.sub("\n\n", value)


def strip_leading_whitespace(value):
    return value.lstrip()


def add_trailing_newline(value):
    return "{}\n".format(value)


def remove_smart_quotes_from_email_addresses(value):
    def remove_smart_quotes(match):
        value = match.group(0)
        for character in "‘’":
            value = value.replace(character, "'")
        return value

    return email_with_smart_quotes_regex.sub(
        remove_smart_quotes,
        value,
    )


def strip_all_whitespace(value, extra_characters=""):
    # Removes from the beginning and end of the string all whitespace characters and `extra_characters`
    if value is not None and hasattr(value, "strip"):
        return value.strip(ALL_WHITESPACE + extra_characters)
    return value


def strip_and_remove_obscure_whitespace(value):
    if value == "":
        # Return early to avoid making multiple, slow calls to
        # str.replace on an empty string
        return ""

    for character in OBSCURE_ZERO_WIDTH_WHITESPACE + OBSCURE_FULL_WIDTH_WHITESPACE:
        value = value.replace(character, "")

    return value.strip(string.whitespace)


def remove_whitespace(value):
    # Removes ALL whitespace, not just the obscure characters we normaly remove
    for character in ALL_WHITESPACE:
        value = value.replace(character, "")

    return value


def strip_unsupported_characters(value):
    return value.replace("\u2028", "")
