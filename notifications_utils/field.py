import re

from markupsafe import Markup
from ordered_set import OrderedSet

from notifications_utils.formatters import (
    escape_html,
    strip_and_remove_obscure_whitespace,
    strip_html,
    unescaped_formatted_list,
)
from notifications_utils.insensitive_dict import InsensitiveDict


class Placeholder:
    def __init__(self, body):
        # body shouldn’t include leading/trailing brackets, like (( and ))
        self.body = body.lstrip("(").rstrip(")")

    @classmethod
    def from_match(cls, match):
        return cls(match.group(0))

    def is_conditional(self):
        return "??" in self.body

    @property
    def name(self):
        # for non conditionals, name equals body
        return self.body.split("??")[0]

    @property
    def conditional_text(self):
        if self.is_conditional():
            # ((a?? b??c)) returns " b??c"
            return "??".join(self.body.split("??")[1:])
        else:
            raise ValueError("{} not conditional".format(self))

    def get_conditional_body(self, show_conditional):
        # note: unsanitised/converted
        if self.is_conditional():
            return self.conditional_text if str2bool(show_conditional) else ""
        else:
            raise ValueError("{} not conditional".format(self))

    def __repr__(self):
        return "Placeholder({})".format(self.body)


class Field:
    """
    An instance of Field represents a string of text which may contain
    placeholders.

    If values are provided the field replaces the placeholders with the
    corresponding values. If a value for a placeholder is missing then
    the field will highlight the placeholder by wrapping it in some HTML.

    A template can have several fields, for example an email template
    has a field for the body and a field for the subject.
    """

    placeholder_pattern = re.compile(
        r"\({2}"  # opening ((
        r"([^()]+)"  # body of placeholder - potentially standard or conditional.
        r"\){2}"  # closing ))
    )
    placeholder_tag = "<span class='placeholder'>(({}))</span>"
    conditional_placeholder_tag = (
        "<span class='placeholder-conditional'>(({}??</span>{}))"
    )
    placeholder_tag_no_brackets = "<span class='placeholder-no-brackets'>{}</span>"
    placeholder_tag_redacted = "<span class='placeholder-redacted'>hidden</span>"

    def __init__(
        self,
        content,
        values=None,
        with_brackets=True,
        html="strip",
        markdown_lists=False,
        redact_missing_personalisation=False,
    ):
        self.content = content
        self.values = values
        self.markdown_lists = markdown_lists
        if not with_brackets:
            self.placeholder_tag = self.placeholder_tag_no_brackets
        self.sanitizer = {
            "strip": strip_html,
            "escape": escape_html,
            "passthrough": str,
        }[html]
        self.redact_missing_personalisation = redact_missing_personalisation

    def __str__(self):
        if self.values:
            return self.replaced
        return self.formatted

    def __repr__(self):
        return '{}("{}", {})'.format(
            self.__class__.__name__, self.content, self.values
        )  # TODO: more real

    def splitlines(self):
        return str(self).splitlines()

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, value):
        self._values = InsensitiveDict(value) if value else {}

    def format_match(self, match):
        placeholder = Placeholder.from_match(match)

        if self.redact_missing_personalisation:
            return self.placeholder_tag_redacted

        if placeholder.is_conditional():
            return self.conditional_placeholder_tag.format(
                placeholder.name, placeholder.conditional_text
            )

        return self.placeholder_tag.format(placeholder.name)

    def replace_match(self, match):
        placeholder = Placeholder.from_match(match)
        replacement = self.values.get(placeholder.name)

        if placeholder.is_conditional() and replacement is not None:
            return placeholder.get_conditional_body(replacement)

        replaced_value = self.get_replacement(placeholder)
        if replaced_value is not None:
            return self.get_replacement(placeholder)

        return self.format_match(match)

    def get_replacement(self, placeholder):
        replacement = self.values.get(placeholder.name)
        if replacement is None:
            return None

        if isinstance(replacement, list):
            vals = (
                strip_and_remove_obscure_whitespace(str(val))
                for val in replacement
                if val is not None
            )
            vals = list(filter(None, vals))
            if not vals:
                return ""
            return self.sanitizer(self.get_replacement_as_list(vals))

        return self.sanitizer(str(replacement))

    def get_replacement_as_list(self, replacement):
        if self.markdown_lists:
            return "\n\n" + "\n".join("* {}".format(item) for item in replacement)
        return unescaped_formatted_list(replacement, before_each="", after_each="")

    @property
    def _raw_formatted(self):
        return re.sub(
            self.placeholder_pattern, self.format_match, self.sanitizer(self.content)
        )

    @property
    def formatted(self):
        return Markup(self._raw_formatted)

    @property
    def placeholders(self):
        if not getattr(self, "content", ""):
            return set()
        return OrderedSet(
            Placeholder(body).name
            for body in re.findall(self.placeholder_pattern, self.content)
        )

    @property
    def replaced(self):
        return re.sub(
            self.placeholder_pattern, self.replace_match, self.sanitizer(self.content)
        )


class PlainTextField(Field):
    """
    Use this where no HTML should be rendered in the outputted content,
    even when no values have been passed in
    """

    placeholder_tag = "(({}))"
    conditional_placeholder_tag = "(({}??{}))"
    placeholder_tag_no_brackets = "{}"
    placeholder_tag_redacted = "[hidden]"


def str2bool(value):
    if not value:
        return False
    return str(value).lower() in ("yes", "y", "true", "t", "1", "include", "show")
