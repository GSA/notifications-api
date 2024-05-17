import re
import unicodedata


def make_string_safe(string, whitespace):
    # strips accents, diacritics etc
    string = "".join(
        c
        for c in unicodedata.normalize("NFD", string)
        if unicodedata.category(c) != "Mn"
    )
    string = "".join(
        word.lower() if word.isalnum() or word == whitespace else ""
        for word in re.sub(r"\s+", whitespace, string.strip())
    )
    string = re.sub(r"\.{2,}", ".", string)
    return string.strip(".")


def make_string_safe_for_email_local_part(string):
    return make_string_safe(string, whitespace=".")


def make_string_safe_for_id(string):
    return make_string_safe(string, whitespace="-")
