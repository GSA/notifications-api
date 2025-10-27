import csv
import re
import sys
from collections import namedtuple
from contextlib import suppress
from functools import lru_cache
from io import StringIO
from itertools import islice

import phonenumbers
from flask import current_app
from ordered_set import OrderedSet
from phonenumbers.phonenumberutil import NumberParseException

from notifications_utils.formatters import (
    strip_all_whitespace,
    strip_and_remove_obscure_whitespace,
)
from notifications_utils.insensitive_dict import InsensitiveDict
from notifications_utils.international_billing_rates import INTERNATIONAL_BILLING_RATES
from notifications_utils.postal_address import (
    address_line_7_key,
    address_lines_1_to_6_and_postcode_keys,
    address_lines_1_to_7_keys,
)
from notifications_utils.template import Template

from . import EMAIL_REGEX_PATTERN, hostname_part, tld_part

us_prefix = "1"

first_column_headings = {
    "email": ["email address"],
    "sms": ["phone number"],
    "letter": [
        line.replace("_", " ")
        for line in address_lines_1_to_6_and_postcode_keys + [address_line_7_key]
    ],
}

address_columns = InsensitiveDict.from_keys(first_column_headings["letter"])


class RecipientCSV:
    max_rows = 100_000

    def __init__(
        self,
        file_data,
        template,
        max_errors_shown=20,
        max_initial_rows_shown=10,
        guestlist=None,
        remaining_messages=sys.maxsize,
        allow_international_sms=False,
        allow_international_letters=False,
        should_validate=True,
    ):
        self.file_data = strip_all_whitespace(file_data, extra_characters=",")
        self.max_errors_shown = max_errors_shown
        self.max_initial_rows_shown = max_initial_rows_shown
        self.guestlist = guestlist
        self.template = template
        self.allow_international_sms = allow_international_sms
        self.allow_international_letters = allow_international_letters
        self.remaining_messages = remaining_messages
        self.rows_as_list = None
        self.should_validate = should_validate

    def __len__(self):
        if not hasattr(self, "_len"):
            self._len = len(self.rows)
        return self._len

    def __getitem__(self, requested_index):
        return self.rows[requested_index]

    @property
    def guestlist(self):
        return self._guestlist

    @guestlist.setter
    def guestlist(self, value):
        try:
            self._guestlist = list(value)
        except TypeError:
            self._guestlist = []

    @property
    def template(self):
        return self._template

    @template.setter
    def template(self, value):
        if not isinstance(value, Template):
            raise TypeError(
                "template must be an instance of "
                "notifications_utils.template.Template"
            )
        self._template = value
        self.template_type = self._template.template_type
        self.recipient_column_headers = first_column_headings[self.template_type]
        self.placeholders = self._template.placeholders

    @property
    def placeholders(self):
        return self._placeholders

    @placeholders.setter
    def placeholders(self, value):
        try:
            self._placeholders = list(value) + self.recipient_column_headers
        except TypeError:
            current_app.logger.exception(
                f"TypeError setting the placeholders to {value}"
            )
            self._placeholders = self.recipient_column_headers
        self.placeholders_as_column_keys = [
            InsensitiveDict.make_key(placeholder) for placeholder in self._placeholders
        ]
        self.recipient_column_headers_as_column_keys = [
            InsensitiveDict.make_key(placeholder)
            for placeholder in self.recipient_column_headers
        ]

    @property
    def has_errors(self):
        return bool(
            self.missing_column_headers
            or self.duplicate_recipient_column_headers
            or self.more_rows_than_can_send
            or self.too_many_rows
            or (not self.allowed_to_send_to)
            or any(self.rows_with_errors)
        )  # `or` is 3x faster than using `any()` here

    @property
    def allowed_to_send_to(self):
        if self.template_type == "letter":
            return True
        if not self.guestlist:
            return True
        return all(
            allowed_to_send_to(row.recipient, self.guestlist) for row in self.rows
        )

    @property
    def rows(self):
        if self.rows_as_list is None:
            self.rows_as_list = list(self.get_rows())
        return self.rows_as_list

    @property
    def _rows(self):
        return csv.reader(
            StringIO(self.file_data.strip()),
            quoting=csv.QUOTE_MINIMAL,
            skipinitialspace=True,
        )

    def get_rows(self):
        column_headers = self._raw_column_headers  # this is for caching
        length_of_column_headers = len(column_headers)

        rows_as_lists_of_columns = self._rows

        next(rows_as_lists_of_columns, None)  # skip the header row

        for index, row in enumerate(rows_as_lists_of_columns):
            if index >= self.max_rows:
                yield None
                continue

            output_dict = {}

            for column_name, column_value in zip(column_headers, row):
                column_value = strip_and_remove_obscure_whitespace(column_value)

                if (
                    InsensitiveDict.make_key(column_name)
                    in self.recipient_column_headers_as_column_keys
                ):
                    output_dict[column_name] = column_value or None
                else:
                    insert_or_append_to_dict(
                        output_dict, column_name, column_value or None
                    )

            length_of_row = len(row)

            if length_of_column_headers < length_of_row:
                output_dict[None] = row[length_of_column_headers:]
            elif length_of_column_headers > length_of_row:
                for key in column_headers[length_of_row:]:
                    insert_or_append_to_dict(output_dict, key, None)

            yield Row(
                output_dict,
                index=index,
                error_fn=self._get_error_for_field,
                recipient_column_headers=self.recipient_column_headers,
                placeholders=self.placeholders_as_column_keys,
                template=self.template,
                allow_international_letters=self.allow_international_letters,
                validate_row=self.should_validate,
            )

    @property
    def more_rows_than_can_send(self):
        return len(self) > self.remaining_messages

    @property
    def too_many_rows(self):
        return len(self) > self.max_rows

    @property
    def initial_rows(self):
        return islice(self.rows, self.max_initial_rows_shown)

    @property
    def displayed_rows(self):
        if any(self.rows_with_errors) and not self.missing_column_headers:
            return self.initial_rows_with_errors
        return self.initial_rows

    def _filter_rows(self, attr):
        return (row for row in self.rows if row and getattr(row, attr))

    @property
    def rows_with_errors(self):
        return self._filter_rows("has_error")

    @property
    def rows_with_bad_recipients(self):
        return self._filter_rows("has_bad_recipient")

    @property
    def rows_with_missing_data(self):
        return self._filter_rows("has_missing_data")

    @property
    def rows_with_message_too_long(self):
        return self._filter_rows("message_too_long")

    @property
    def rows_with_empty_message(self):
        return self._filter_rows("message_empty")

    @property
    def initial_rows_with_errors(self):
        return islice(self.rows_with_errors, self.max_errors_shown)

    @property
    def _raw_column_headers(self):
        for row in self._rows:
            return row
        return []

    @property
    def column_headers(self):
        return list(OrderedSet(self._raw_column_headers))

    @property
    def column_headers_as_column_keys(self):
        return InsensitiveDict.from_keys(self.column_headers).keys()

    @property
    def missing_column_headers(self):
        return set(
            key
            for key in self.placeholders
            if (
                InsensitiveDict.make_key(key) not in self.column_headers_as_column_keys
                and not self.is_address_column(key)
            )
        )

    @property
    def duplicate_recipient_column_headers(self):
        raw_recipient_column_headers = [
            InsensitiveDict.make_key(column_header)
            for column_header in self._raw_column_headers
            if InsensitiveDict.make_key(column_header)
            in self.recipient_column_headers_as_column_keys
        ]

        return OrderedSet(
            (
                column_header
                for column_header in self._raw_column_headers
                if raw_recipient_column_headers.count(
                    InsensitiveDict.make_key(column_header)
                )
                > 1
            )
        )

    def is_address_column(self, key):
        return self.template_type == "letter" and key in address_columns

    @property
    def count_of_required_recipient_columns(self):
        return 3 if self.template_type == "letter" else 1

    @property
    def has_recipient_columns(self):
        if self.template_type == "letter":
            sets_to_check = [
                InsensitiveDict.from_keys(
                    address_lines_1_to_6_and_postcode_keys
                ).keys(),
                InsensitiveDict.from_keys(address_lines_1_to_7_keys).keys(),
            ]
        else:
            sets_to_check = [
                self.recipient_column_headers_as_column_keys,
            ]

        for set_to_check in sets_to_check:
            if (
                len(
                    # Work out which columns are shared between the possible
                    # letter address columns and the columns in the user’s
                    # spreadsheet (`&` means set intersection)
                    set_to_check
                    & self.column_headers_as_column_keys
                )
                >= self.count_of_required_recipient_columns
            ):
                return True

        return False

    def _get_error_for_field(self, key, value):  # noqa: C901
        if self.is_address_column(key):
            return

        if (
            InsensitiveDict.make_key(key)
            in self.recipient_column_headers_as_column_keys
        ):
            if value in [None, ""] or isinstance(value, list):
                if self.duplicate_recipient_column_headers:
                    return None
                else:
                    return Cell.missing_field_error

            try:
                if self.template_type == "email":
                    validate_email_address(value)
                if self.template_type == "sms":
                    validate_phone_number(
                        value, international=self.allow_international_sms
                    )
            except (InvalidEmailError, InvalidPhoneError) as error:
                current_app.logger.exception(f"Email or phone error for {value}")
                return str(error)

        if InsensitiveDict.make_key(key) not in self.placeholders_as_column_keys:
            return

        if value in [None, ""]:
            return Cell.missing_field_error


class Row(InsensitiveDict):
    message_too_long = False
    message_empty = False

    def __init__(
        self,
        row_dict,
        *,
        index,
        error_fn,
        recipient_column_headers,
        placeholders,
        template,
        allow_international_letters,
        validate_row=True,
    ):
        # If we don't need to validate, then:
        # by not setting template we avoid the template level validation (used to check message length)
        # by not setting error_fn, we avoid the Cell.__init__ validation (used to check phone nums are valid,
        # placeholders are present, etc)
        if not validate_row:
            template = None
            error_fn = None

        self.index = index
        self.recipient_column_headers = recipient_column_headers
        self.placeholders = placeholders
        self.allow_international_letters = allow_international_letters

        if template:
            template.values = row_dict
            self.template_type = template.template_type
            # we do not validate email size for CSVs to avoid performance issues
            if self.template_type == "email":
                self.message_too_long = False
            else:
                self.message_too_long = template.is_message_too_long()
            self.message_empty = template.is_message_empty()

        super().__init__(
            {
                key: Cell(key, value, error_fn, self.placeholders)
                for key, value in row_dict.items()
            }
        )

    def __getitem__(self, key):
        return super().__getitem__(key) if key in self else Cell()

    def get(self, key, default=None):
        if key not in self and default is not None:
            return default
        return self[key]

    @property
    def has_error(self):
        return self.has_error_spanning_multiple_cells or any(
            cell.error for cell in self.values()
        )

    @property
    def has_bad_recipient(self):
        if self.template_type == "letter":
            return self.has_bad_postal_address
        return self.get(self.recipient_column_headers[0]).recipient_error

    @property
    def has_bad_postal_address(self):
        return self.template_type == "letter" and not self.as_postal_address.valid

    @property
    def has_error_spanning_multiple_cells(self):
        return (
            self.message_too_long or self.message_empty or self.has_bad_postal_address
        )

    @property
    def has_missing_data(self):
        return any(cell.error == Cell.missing_field_error for cell in self.values())

    @property
    def recipient(self):
        columns = [self.get(column).data for column in self.recipient_column_headers]
        return columns[0] if len(columns) == 1 else columns

    @property
    def as_postal_address(self):
        from notifications_utils.postal_address import PostalAddress

        return PostalAddress.from_personalisation(
            self.recipient_and_personalisation,
            allow_international_letters=self.allow_international_letters,
        )

    @property
    def personalisation(self):
        return InsensitiveDict(
            {key: cell.data for key, cell in self.items() if key in self.placeholders}
        )

    @property
    def recipient_and_personalisation(self):
        return InsensitiveDict({key: cell.data for key, cell in self.items()})


class Cell:
    missing_field_error = "Missing"

    def __init__(self, key=None, value=None, error_fn=None, placeholders=None):
        self.data = value
        self.error = error_fn(key, value) if error_fn else None
        self.ignore = InsensitiveDict.make_key(key) not in (placeholders or [])

    def __eq__(self, other):
        if not other.__class__ == self.__class__:
            return False
        return all(
            (
                self.data == other.data,
                self.error == other.error,
                self.ignore == other.ignore,
            )
        )

    @property
    def recipient_error(self):
        return self.error not in {None, self.missing_field_error}


class InvalidEmailError(Exception):
    def __init__(self, message=None):
        super().__init__(message or "Not a valid email address")


class InvalidPhoneError(InvalidEmailError):
    pass


class InvalidAddressError(InvalidEmailError):
    pass


def normalize_phone_number(phonenumber):
    if isinstance(phonenumber, str):
        phonenumber = phonenumbers.parse(phonenumber, "US")
    return phonenumbers.format_number(phonenumber, phonenumbers.PhoneNumberFormat.E164)


def is_us_phone_number(number):
    try:
        return _get_country_code(number) == us_prefix
    except NumberParseException:
        return False


international_phone_info = namedtuple(
    "PhoneNumber",
    [
        "international",
        "country_prefix",
        "billable_units",
    ],
)


def get_international_phone_info(number):
    number = validate_phone_number(number, international=True)
    prefix = _get_country_code(number)

    return international_phone_info(
        international=(prefix != us_prefix),
        country_prefix=prefix,
        billable_units=get_billable_units_for_prefix(prefix),
    )


# NANP_COUNTRY_AREA_CODES are the list of area codes in the North American Numbering Plan
# that have their own entry in international_billing_rates.yml.
# Source: https://en.wikipedia.org/wiki/List_of_North_American_Numbering_Plan_area_codes
_NANP_COUNTRY_AREA_CODES = [
    "684",
    "242",
    "246",
    "264",
    "268",
    "284",
    "345",
    "441",
    "473",
    "649",
    "876",
    "664",
    "721",
    "758",
    "767",
    "784",
    "868",
    "869",
]


def _get_country_code(number):
    parsed = phonenumbers.parse(number, "US")
    country_code = str(parsed.country_code)
    if country_code == us_prefix:
        area_code = str(parsed.national_number)[:3]
        if area_code in _NANP_COUNTRY_AREA_CODES:
            return f"{country_code}{area_code}"
    return country_code


def get_billable_units_for_prefix(prefix):
    """Return the billable units for prefix. Hard-coded to 1 for now"""
    return 1
    # return INTERNATIONAL_BILLING_RATES[prefix]['billable_units']


def use_numeric_sender(number):
    prefix = _get_country_code(number)
    return (
        INTERNATIONAL_BILLING_RATES[(prefix or us_prefix)]["attributes"]["alpha"]
        == "NO"
    )


def validate_us_phone_number(number):
    try:
        parsed = phonenumbers.parse(number, "US")
        if not is_us_phone_number(number):
            raise InvalidPhoneError("Not a US number")
        if phonenumbers.is_valid_number(parsed):
            return normalize_phone_number(parsed)
        if len(str(parsed.national_number)) > 10:
            raise InvalidPhoneError("Too many digits")
        if len(str(parsed.national_number)) < 10:
            raise InvalidPhoneError("Not enough digits")
        if phonenumbers.is_possible_number(parsed):
            raise InvalidPhoneError("Phone number range is not in use")
        raise InvalidPhoneError("Phone number is not possible")
    except NumberParseException as exc:
        raise InvalidPhoneError(exc._msg) from exc


def show_mangled_number_clues(number):

    translator = {
        "1": "X",
        "2": "X",
        "3": "X",
        "4": "X",
        "5": "X",
        "6": "X",
        "7": "X",
        "8": "X",
        "9": "X",
        "0": "X",
    }
    for key in translator:
        number = number.replace(key, translator[key])

    return number


def validate_phone_number(number, international=False):
    if (not international) or is_us_phone_number(number):
        return validate_us_phone_number(number)

    try:
        parsed = phonenumbers.parse(number, None)
        number = f"{parsed.country_code}{parsed.national_number}"
        if len(number) < 8:
            raise InvalidPhoneError("Not enough digits")
        if len(number) > 15:
            raise InvalidPhoneError("Too many digits")
        return normalize_phone_number(parsed)
    except NumberParseException as exc:
        if exc._msg == "Could not interpret numbers after plus-sign.":
            raise InvalidPhoneError("Not a valid country prefix") from exc
        if not isinstance(number, str):
            raise InvalidPhoneError(f"Number must be string, not type {type(number)}")
        raise InvalidPhoneError(
            f"Invalid phone number looks like {show_mangled_number_clues(number)} {exc._msg}"
        )


validate_and_format_phone_number = validate_phone_number


def try_validate_and_format_phone_number(number, international=None, log_msg=None):
    """
    For use in places where you shouldn't error if the phone number is invalid - for example if firetext pass us
    something in
    """
    try:
        return validate_and_format_phone_number(number, international)
    except InvalidPhoneError as exc:
        if log_msg:
            current_app.logger.warning("{}: {}".format(log_msg, exc))
        return number


def _do_simple_email_checks(match, email_address):
    # not an email
    if not match:
        raise InvalidEmailError

    if len(email_address) > 320:
        raise InvalidEmailError

    # don't allow consecutive periods in either part
    if ".." in email_address:
        raise InvalidEmailError


def validate_email_address(email_address):  # noqa (C901 too complex)
    # almost exactly the same as by https://github.com/wtforms/wtforms/blob/master/wtforms/validators.py,
    # with minor tweaks for SES compatibility - to avoid complications we are a lot stricter with the local part
    # than neccessary - we don't allow any double quotes or semicolons to prevent SES Technical Failures
    email_address = strip_and_remove_obscure_whitespace(email_address)
    match = re.match(EMAIL_REGEX_PATTERN, email_address)

    _do_simple_email_checks(match, email_address)

    hostname = match.group(1)

    # idna = "Internationalized domain name" - this encode/decode cycle converts unicode into its accurate ascii
    # representation as the web uses. '例え.テスト'.encode('idna') == b'xn--r8jz45g.xn--zckzah'
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        current_app.logger.exception("UnicodeError validating email address")
        raise InvalidEmailError

    parts = hostname.split(".")

    if len(hostname) > 253 or len(parts) < 2:
        raise InvalidEmailError

    for part in parts:
        if not part or len(part) > 63 or not hostname_part.match(part):
            raise InvalidEmailError

    # if the part after the last . is not a valid TLD then bail out
    if not tld_part.match(parts[-1]):
        raise InvalidEmailError

    return email_address


def format_email_address(email_address):
    return strip_and_remove_obscure_whitespace(email_address.lower())


def validate_and_format_email_address(email_address):
    return format_email_address(validate_email_address(email_address))


@lru_cache(maxsize=32, typed=False)
def format_recipient(recipient):
    if not isinstance(recipient, str):
        return ""
    with suppress(InvalidPhoneError):
        return validate_and_format_phone_number(recipient, international=True)
    with suppress(InvalidEmailError):
        return validate_and_format_email_address(recipient)
    return recipient


def format_phone_number_human_readable(phone_number):
    try:
        phone_number = validate_phone_number(phone_number, international=True)
    except InvalidPhoneError:
        # if there was a validation error, we want to shortcut out here, but still display the number on the front end
        current_app.logger.exception(
            "InvalidPhoneError trying to format_phone_number_human_readable()"
        )
        return phone_number
    international_phone_info = get_international_phone_info(phone_number)

    return phonenumbers.format_number(
        phonenumbers.parse(phone_number, None),
        (
            phonenumbers.PhoneNumberFormat.INTERNATIONAL
            if international_phone_info.international
            else phonenumbers.PhoneNumberFormat.NATIONAL
        ),
    )


def allowed_to_send_to(recipient, allowlist):
    return format_recipient(recipient) in {format_recipient(x) for x in allowlist}


def insert_or_append_to_dict(dict_, key, value):
    if not (key or value):
        # We don’t care about completely empty values so it’s faster to
        # ignore them rather than working out how to store them
        return

    if dict_.get(key):
        if isinstance(dict_[key], list):
            dict_[key].append(value)
        else:
            dict_[key] = [dict_[key], value]
    else:
        dict_.update({key: value})
