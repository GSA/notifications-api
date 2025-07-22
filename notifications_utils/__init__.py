import truststore

truststore.inject_into_ssl()  # noqa

import re  # noqa
from datetime import datetime, timezone  # noqa

SMS_CHAR_COUNT_LIMIT = 918  # 153 * 6, no network issues but check with providers before upping this further
LETTER_MAX_PAGE_COUNT = 10
DAILY_MESSAGE_LIMIT = 10000

# regexes for use in recipients.validate_email_address.
# Valid characters taken from https://en.wikipedia.org/wiki/Email_address#Local-part
# Note: Normal apostrophe eg `Firstname-o'surname@domain.com` is allowed.
# hostname_part regex: xn in regex signifies possible punycode conversions, which would start `xn--`;
# the hyphens are matched for later in the regex.
hostname_part = re.compile(r"^(xn|[a-z0-9]+)(-?-[a-z0-9]+)*$", re.IGNORECASE)
tld_part = re.compile(r"^([a-z]{2,63}|xn--([a-z0-9]+-)*[a-z0-9]+)$", re.IGNORECASE)
VALID_LOCAL_CHARS = r"a-zA-Z0-9.!#$%&'*+/=?^_`{|}~\-"
EMAIL_REGEX_PATTERN = r"^[{}]+@([^.@][^@\s]+)$".format(VALID_LOCAL_CHARS)
email_with_smart_quotes_regex = re.compile(
    # matches wider than an email - everything between an at sign and the nearest whitespace
    r"(^|\s)\S+@\S+(\s|$)",
    flags=re.MULTILINE,
)

# The magic sequence is a ‘unique’ series of characters which we temporarily insert
# and then later remove when performing tricky formatting operations
MAGIC_SEQUENCE = "🇬🇧🐦✉️"
magic_sequence_regex = re.compile(MAGIC_SEQUENCE)


def aware_utcnow():
    return datetime.now(timezone.utc)


def naive_utcnow():
    return aware_utcnow().replace(tzinfo=None)


def utc_now():
    return naive_utcnow()
