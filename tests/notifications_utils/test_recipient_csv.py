import itertools
import string
import unicodedata
from functools import partial
from random import choice, randrange
from unittest.mock import Mock

import pytest
from ordered_set import OrderedSet

from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.formatters import strip_and_remove_obscure_whitespace
from notifications_utils.recipients import (
    Cell,
    RecipientCSV,
    Row,
    first_column_headings,
)
from notifications_utils.template import EmailPreviewTemplate, SMSMessageTemplate


def _sample_template(template_type, content="foo"):
    return {
        "email": EmailPreviewTemplate(
            {"content": content, "subject": "bar", "template_type": "email"}
        ),
        "sms": SMSMessageTemplate({"content": content, "template_type": "sms"}),
    }.get(template_type)


def _index_rows(rows):
    return set(row.index for row in rows)


@pytest.mark.parametrize(
    ("template_type", "expected"),
    [
        ("email", ["email address"]),
        ("sms", ["phone number"]),
    ],
)
def test_recipient_column_headers(template_type, expected):
    recipients = RecipientCSV("", template=_sample_template(template_type))
    assert (
        (recipients.recipient_column_headers)
        == (first_column_headings[template_type])
        == (expected)
    )


@pytest.mark.parametrize(
    ("file_contents", "template_type", "expected"),
    [
        (
            "",
            "sms",
            [],
        ),
        (
            "phone number",
            "sms",
            [],
        ),
        (
            """
                phone number,name
                +44 123, test1
                +44 456,test2
            """,
            "sms",
            [
                [("phone number", "+44 123"), ("name", "test1")],
                [("phone number", "+44 456"), ("name", "test2")],
            ],
        ),
        (
            """
                phone number,name
                +44 123,
                +44 456
            """,
            "sms",
            [
                [("phone number", "+44 123"), ("name", None)],
                [("phone number", "+44 456"), ("name", None)],
            ],
        ),
        (
            """
                email address,name
                test@example.com,test1
                test2@example.com, test2
            """,
            "email",
            [
                [("email address", "test@example.com"), ("name", "test1")],
                [("email address", "test2@example.com"), ("name", "test2")],
            ],
        ),
        (
            """
                email address
                test@example.com,test1,red
                test2@example.com, test2,blue
            """,
            "email",
            [
                [("email address", "test@example.com"), (None, ["test1", "red"])],
                [("email address", "test2@example.com"), (None, ["test2", "blue"])],
            ],
        ),
        (
            """
                email address,name
                test@example.com,"test1"
                test2@example.com,"   test2    "
                test3@example.com," test3"
            """,
            "email",
            [
                [("email address", "test@example.com"), ("name", "test1")],
                [("email address", "test2@example.com"), ("name", "test2")],
                [("email address", "test3@example.com"), ("name", "test3")],
            ],
        ),
        (
            """
                email address,date,name
                test@example.com,"Nov 28, 2016",test1
                test2@example.com,"Nov 29, 2016",test2
            """,
            "email",
            [
                [
                    ("email address", "test@example.com"),
                    ("date", "Nov 28, 2016"),
                    ("name", "test1"),
                ],
                [
                    ("email address", "test2@example.com"),
                    ("date", "Nov 29, 2016"),
                    ("name", "test2"),
                ],
            ],
        ),
        (
            """
                phone number, list, list, list
                07900900001, cat, rat, gnat
                07900900002, dog, hog, frog
                07900900003, elephant
            """,
            "sms",
            [
                [("phone number", "07900900001"), ("list", ["cat", "rat", "gnat"])],
                [("phone number", "07900900002"), ("list", ["dog", "hog", "frog"])],
                [("phone number", "07900900003"), ("list", ["elephant", None, None])],
            ],
        ),
    ],
)
def test_get_rows(file_contents, template_type, expected):
    rows = list(
        RecipientCSV(file_contents, template=_sample_template(template_type)).rows
    )
    if not expected:
        assert rows == expected
    for index, row in enumerate(expected):
        assert len(rows[index].items()) == len(row)
        for key, value in row:
            assert rows[index].get(key).data == value


def test_get_rows_does_no_error_checking_of_rows_or_cells(mocker):
    has_error_mock = mocker.patch.object(Row, "has_error")
    has_bad_recipient_mock = mocker.patch.object(Row, "has_bad_recipient")
    has_missing_data_mock = mocker.patch.object(Row, "has_missing_data")
    cell_recipient_error_mock = mocker.patch.object(Cell, "recipient_error")

    recipients = RecipientCSV(
        """
            email address, name
            a@b.com,
            a@b.com, My Name
            a@b.com,


        """,
        template=_sample_template("email", "hello ((name))"),
        max_errors_shown=3,
    )

    rows = recipients.get_rows()
    for _ in range(3):
        assert next(rows).recipient == "a@b.com"

    assert has_error_mock.called is False
    assert has_bad_recipient_mock.called is False
    assert has_missing_data_mock.called is False
    assert cell_recipient_error_mock.called is False


def test_get_rows_only_iterates_over_file_once(mocker):
    row_mock = mocker.patch("notifications_utils.recipients.Row")

    recipients = RecipientCSV(
        """
            email address, name
            a@b.com,
            a@b.com, My Name
            a@b.com,


        """,
        template=_sample_template("email", "hello ((name))"),
    )

    rows = recipients.get_rows()
    for _ in range(3):
        next(rows)

    assert row_mock.call_count == 3
    assert recipients.rows_as_list is None


@pytest.mark.parametrize(
    ("file_contents", "template_type", "expected"),
    [
        (
            """
                phone number,name
                2348675309, test1
                +1234-867-5301,test2
                ,
            """,
            "sms",
            [
                {"index": 0, "message_too_long": False},
                {"index": 1, "message_too_long": False},
            ],
        ),
        (
            """
                email address,name,colour
                test@example.com,test1,blue
                test2@example.com, test2,red
            """,
            "email",
            [
                {"index": 0, "message_too_long": False},
                {"index": 1, "message_too_long": False},
            ],
        ),
    ],
)
def test_get_annotated_rows(file_contents, template_type, expected):
    recipients = RecipientCSV(
        file_contents,
        template=_sample_template(template_type, "hello ((name))"),
        max_initial_rows_shown=1,
    )
    for index, expected_row in enumerate(expected):
        annotated_row = list(recipients.rows)[index]
        assert annotated_row.index == expected_row["index"]
        assert annotated_row.message_too_long == expected_row["message_too_long"]
    assert len(list(recipients.rows)) == 2
    assert len(list(recipients.initial_rows)) == 1
    assert not recipients.has_errors


def test_get_rows_with_errors():
    recipients = RecipientCSV(
        """
            email address, name
            a@b.com,
            a@b.com,
            a@b.com,
            a@b.com,
            a@b.com,
            a@b.com,


        """,
        template=_sample_template("email", "hello ((name))"),
        max_errors_shown=3,
    )
    assert len(list(recipients.rows_with_errors)) == 6
    assert len(list(recipients.initial_rows_with_errors)) == 3
    assert recipients.has_errors


@pytest.mark.parametrize(
    ("template_type", "row_count", "header", "filler", "row_with_error"),
    [
        (
            "email",
            500,
            "email address\n",
            "test@example.com\n",
            "test at example dot com",
        ),
        ("sms", 500, "phone number\n", "2348675309\n", "12345"),
    ],
)
def test_big_list_validates_right_through(
    template_type, row_count, header, filler, row_with_error
):
    big_csv = RecipientCSV(
        header + (filler * (row_count - 1) + row_with_error),
        template=_sample_template(template_type),
        max_errors_shown=100,
        max_initial_rows_shown=3,
    )
    assert len(list(big_csv.rows)) == row_count
    assert _index_rows(big_csv.rows_with_bad_recipients) == {row_count - 1}  # 0 indexed
    assert _index_rows(big_csv.rows_with_errors) == {row_count - 1}
    assert len(list(big_csv.initial_rows_with_errors)) == 1
    assert big_csv.has_errors


@pytest.mark.parametrize(
    ("template_type", "row_count", "header", "filler"),
    [
        ("email", 50, "email address\n", "test@example.com\n"),
        ("sms", 50, "phone number\n", "07900900123\n"),
    ],
)
def test_check_if_message_too_long_for_sms_but_not_email_in_CSV(
    mocker, template_type, row_count, header, filler
):
    # we do not validate email size for CSVs to avoid performance issues
    RecipientCSV(
        header + filler * row_count,
        template=_sample_template(template_type),
        max_errors_shown=100,
        max_initial_rows_shown=3,
    )
    is_message_too_long = mocker.patch(
        "notifications_utils.template.Template.is_message_too_long", side_effect=False
    )
    if template_type == "email":
        is_message_too_long.assert_not_called
    else:
        is_message_too_long.called


def test_overly_big_list_stops_processing_rows_beyond_max(mocker):
    mock_strip_and_remove_obscure_whitespace = mocker.patch(
        "notifications_utils.recipients.strip_and_remove_obscure_whitespace",
        wraps=strip_and_remove_obscure_whitespace,
    )
    mock_insert_or_append_to_dict = mocker.patch(
        "notifications_utils.recipients.insert_or_append_to_dict"
    )

    big_csv = RecipientCSV(
        "phonenumber,name\n" + ("2348675309,example\n" * 123),
        template=_sample_template("sms", content="hello ((name))"),
    )
    big_csv.max_rows = 10

    # Our CSV has lots of rows…
    assert big_csv.too_many_rows
    assert len(big_csv) == 123

    # …but we’ve only called the expensive whitespace function on each
    # of the 2 cells in the first 10 rows
    assert len(mock_strip_and_remove_obscure_whitespace.call_args_list) == 20

    # …and we’ve only called the function which builds the internal data
    # structure once for each of the first 10 rows
    assert len(mock_insert_or_append_to_dict.call_args_list) == 10


def test_file_with_lots_of_empty_columns():
    process = Mock()

    lots_of_commas = "," * 10_000

    for row in RecipientCSV(
        f"phone_number{lots_of_commas}\n" + (f"07900900900{lots_of_commas}\n" * 100),
        template=_sample_template("sms"),
    ):
        assert [(key, cell.data) for key, cell in row.items()] == [
            # Note that we haven’t stored any of the empty cells
            ("phonenumber", "07900900900")
        ]
        process()

    assert process.call_count == 100


def test_empty_column_names():
    recipient_csv = RecipientCSV(
        """
            phone_number,,,name
            07900900123,foo,bar,baz
        """,
        template=_sample_template("sms"),
    )

    assert recipient_csv[0]["phone_number"].data == "07900900123"
    assert recipient_csv[0][""].data == ["foo", "bar"]
    assert recipient_csv[0]["name"].data == "baz"


@pytest.mark.parametrize(
    ("file_contents", "template", "expected_recipients", "expected_personalisation"),
    [
        (
            """
                phone number,name, date
                +44 123,test1,today
                +44456,    ,tomorrow
                ,,
                , ,
            """,
            _sample_template("sms", "hello ((name))"),
            ["+44 123", "+44456"],
            [{"name": "test1"}, {"name": None}],
        ),
        (
            """
                email address,name,colour
                test@example.com,test1,red
                testatexampledotcom,test2,blue
            """,
            _sample_template("email", "((colour))"),
            ["test@example.com", "testatexampledotcom"],
            [{"colour": "red"}, {"colour": "blue"}],
        ),
        (
            """
                email address
                test@example.com,test1,red
                testatexampledotcom,test2,blue
            """,
            _sample_template("email"),
            ["test@example.com", "testatexampledotcom"],
            [],
        ),
    ],
)
def test_get_recipient(
    file_contents, template, expected_recipients, expected_personalisation
):
    recipients = RecipientCSV(file_contents, template=template)

    for index, row in enumerate(expected_personalisation):
        for key, value in row.items():
            assert recipients[index].recipient == expected_recipients[index]
            assert recipients[index].personalisation.get(key) == value


@pytest.mark.parametrize(
    ("file_contents", "template", "expected_recipients", "expected_personalisation"),
    [
        (
            """
                email address,test
                test@example.com,test1,red
                testatexampledotcom,test2,blue
            """,
            _sample_template("email", "((test))"),
            [(0, "test@example.com"), (1, "testatexampledotcom")],
            [
                {"emailaddress": "test@example.com", "test": "test1"},
                {"emailaddress": "testatexampledotcom", "test": "test2"},
            ],
        )
    ],
)
def test_get_recipient_respects_order(
    file_contents, template, expected_recipients, expected_personalisation
):
    recipients = RecipientCSV(file_contents, template=template)

    for row, email in expected_recipients:
        assert (
            recipients[row].index,
            recipients[row].recipient,
            recipients[row].personalisation,
        ) == (
            row,
            email,
            expected_personalisation[row],
        )


@pytest.mark.parametrize(
    ("file_contents", "template_type", "expected", "expected_missing"),
    [
        ("", "sms", [], set(["phone number", "name"])),
        (
            """
                phone number,name
                2348675309,test1
                2348675309,test1
                2348675309,test1
            """,
            "sms",
            ["phone number", "name"],
            set(),
        ),
        (
            """
                email address,name,colour
            """,
            "email",
            ["email address", "name", "colour"],
            set(),
        ),
        (
            """
                email address,colour
            """,
            "email",
            ["email address", "colour"],
            set(["name"]),
        ),
        (
            """
                phone number,list,list,name,list
            """,
            "sms",
            ["phone number", "list", "name"],
            set(),
        ),
    ],
)
def test_column_headers(file_contents, template_type, expected, expected_missing):
    recipients = RecipientCSV(
        file_contents, template=_sample_template(template_type, "((name))")
    )
    assert recipients.column_headers == expected
    assert recipients.missing_column_headers == expected_missing
    assert recipients.has_errors == bool(expected_missing)


@pytest.mark.parametrize(
    "content",
    [
        "hello",
        "hello ((name))",
    ],
)
@pytest.mark.parametrize(
    ("file_contents", "template_type"),
    [
        pytest.param("", "sms", marks=pytest.mark.xfail),
        pytest.param("name", "sms", marks=pytest.mark.xfail),
        pytest.param("email address", "sms", marks=pytest.mark.xfail),
        ("phone number", "sms"),
        ("phone number,name", "sms"),
        ("email address", "email"),
        ("email address,name", "email"),
        ("PHONENUMBER", "sms"),
        ("email_address", "email"),
    ],
)
def test_recipient_column(content, file_contents, template_type):
    assert RecipientCSV(
        file_contents, template=_sample_template(template_type, content)
    ).has_recipient_columns


@pytest.mark.parametrize(
    (
        "file_contents",
        "template_type",
        "rows_with_bad_recipients",
        "rows_with_missing_data",
    ),
    [
        (
            """
                phone number,name,date
                2348675309,test1,test1
                2348675309,test1
                +44 123,test1,test1
                2348675309,test1,test1
                2348675309,test1
                +1644000000,test1,test1
                ,test1,test1
            """,
            "sms",
            {2, 5},
            {1, 4, 6},
        ),
        (
            """
                phone number,name
                2348675309,test1,test2
            """,
            "sms",
            set(),
            set(),
        ),
        (
            """
            """,
            "sms",
            set(),
            set(),
        ),
    ],
)
@pytest.mark.parametrize(
    "partial_instance",
    [
        partial(RecipientCSV),
        partial(RecipientCSV, allow_international_sms=False),
    ],
)
def test_bad_or_missing_data(
    file_contents,
    template_type,
    rows_with_bad_recipients,
    rows_with_missing_data,
    partial_instance,
):
    recipients = partial_instance(
        file_contents, template=_sample_template(template_type, "((date))")
    )
    assert _index_rows(recipients.rows_with_bad_recipients) == rows_with_bad_recipients
    assert _index_rows(recipients.rows_with_missing_data) == rows_with_missing_data
    if rows_with_bad_recipients or rows_with_missing_data:
        assert recipients.has_errors is True


# TODO, original test for number one had {0, 1, 2}, but it has morphed to {0, 1}
# Is +447900123 legit or not?  What changed?
@pytest.mark.parametrize(
    ("file_contents", "rows_with_bad_recipients"),
    [
        (
            """
            phone number
            +800000000000
            1234
            +447900123
        """,
            {0, 1},
        ),
        (
            """
            phone number, country
            1-202-234-0104, USA
            +12022340104, USA
            +23051234567, Mauritius
        """,
            set(),
        ),
    ],
)
def test_international_recipients(file_contents, rows_with_bad_recipients):
    recipients = RecipientCSV(
        file_contents,
        template=_sample_template("sms"),
        allow_international_sms=True,
    )
    assert _index_rows(recipients.rows_with_bad_recipients) == rows_with_bad_recipients


def test_errors_when_too_many_rows():
    recipients = RecipientCSV(
        "email address\n" + ("a@b.com\n" * 101),
        template=_sample_template("email"),
    )

    # Confirm the normal max_row limit
    assert recipients.max_rows == 100_000
    # Override to make this test faster
    recipients.max_rows = 100

    assert recipients.too_many_rows is True
    assert recipients.has_errors is True
    assert recipients.rows[99]["email_address"].data == "a@b.com"
    # We stop processing subsequent rows
    assert recipients.rows[100] is None


@pytest.mark.parametrize(
    ("file_contents", "template_type", "guestlist", "count_of_rows_with_errors"),
    [
        (
            """
                phone number
                2348675309
                2348675301
                2348675302
                2348675303
            """,
            "sms",
            ["+12348675309"],  # Same as first phone number but in different format
            3,
        ),
        (
            """
                phone number
                12348675309
                2348675301
                2348675302
            """,
            "sms",
            [
                "2348675309",
                "12348675301",
                "2348675302",
                "2341231234",
                "test@example.com",
            ],
            0,
        ),
        (
            """
                email address
                IN_GUESTLIST@EXAMPLE.COM
                not_in_guestlist@example.com
            """,
            "email",
            [
                "in_guestlist@example.com",
                "2348675309",
            ],  # Email case differs to the one in the CSV
            1,
        ),
    ],
)
def test_recipient_guestlist(
    file_contents, template_type, guestlist, count_of_rows_with_errors
):
    recipients = RecipientCSV(
        file_contents, template=_sample_template(template_type), guestlist=guestlist
    )

    if count_of_rows_with_errors:
        assert not recipients.allowed_to_send_to
    else:
        assert recipients.allowed_to_send_to

    # Make sure the guestlist isn’t emptied by reading it. If it’s an iterator then
    # there’s a risk that it gets emptied after being read once
    recipients.guestlist = (
        str(fake_number) for fake_number in range(7700900888, 7700900898)
    )
    list(recipients.guestlist)
    assert not recipients.allowed_to_send_to
    assert recipients.has_errors

    # An empty guestlist is treated as no guestlist at all
    recipients.guestlist = []
    assert recipients.allowed_to_send_to
    recipients.guestlist = itertools.chain()
    assert recipients.allowed_to_send_to


def test_detects_rows_which_result_in_overly_long_messages():
    template = SMSMessageTemplate(
        {"content": "((placeholder))", "template_type": "sms"},
        sender=None,
        prefix=None,
    )
    recipients = RecipientCSV(
        """
            phone number,placeholder
            2348675309,1
            2348675301,{one_under}
            2348675302,{exactly}
            2348675303,{one_over}
        """.format(
            one_under="a" * (SMS_CHAR_COUNT_LIMIT - 1),
            exactly="a" * SMS_CHAR_COUNT_LIMIT,
            one_over="a" * (SMS_CHAR_COUNT_LIMIT + 1),
        ),
        template=template,
    )
    assert _index_rows(recipients.rows_with_errors) == {3}
    assert _index_rows(recipients.rows_with_message_too_long) == {3}
    assert recipients.has_errors
    assert recipients[0].has_error_spanning_multiple_cells is False
    assert recipients[1].has_error_spanning_multiple_cells is False
    assert recipients[2].has_error_spanning_multiple_cells is False
    assert recipients[3].has_error_spanning_multiple_cells is True


def test_detects_rows_which_result_in_empty_messages():
    template = SMSMessageTemplate(
        {"content": "((show??content))", "template_type": "sms"},
        sender=None,
        prefix=None,
    )
    recipients = RecipientCSV(
        """
            phone number,show
            2348675309,yes
            2348675301,no
            2348675302,yes
        """,
        template=template,
    )
    assert _index_rows(recipients.rows_with_errors) == {1}
    assert _index_rows(recipients.rows_with_empty_message) == {1}
    assert recipients.has_errors
    assert recipients[0].has_error_spanning_multiple_cells is False
    assert recipients[1].has_error_spanning_multiple_cells is True
    assert recipients[2].has_error_spanning_multiple_cells is False


@pytest.mark.parametrize(
    ("key", "expected"),
    sum(
        [
            [(key, expected) for key in group]
            for expected, group in [
                (
                    "2348675309",
                    (
                        "phone number",
                        "   PHONENUMBER",
                        "phone_number",
                        "phone-number",
                        "phoneNumber",
                    ),
                ),
                (
                    "Jo",
                    (
                        "FIRSTNAME",
                        "first name",
                        "first_name ",
                        "first-name",
                        "firstName",
                    ),
                ),
                (
                    "Bloggs",
                    (
                        "Last    Name",
                        "LASTNAME",
                        "    last_name",
                        "last-name",
                        "lastName   ",
                    ),
                ),
            ]
        ],
        [],
    ),
)
def test_ignores_spaces_and_case_in_placeholders(key, expected):
    recipients = RecipientCSV(
        """
            phone number,FIRSTNAME, Last Name
            2348675309, Jo, Bloggs
        """,
        template=_sample_template(
            "sms", content="((phone_number)) ((First Name)) ((lastname))"
        ),
    )
    first_row = recipients[0]
    assert first_row.get(key).data == expected
    assert first_row[key].data == expected
    assert first_row.recipient == "2348675309"
    assert len(first_row.items()) == 3
    assert not recipients.has_errors

    assert recipients.missing_column_headers == set()
    recipients.placeholders = {"one", "TWO", "Thirty_Three"}
    assert recipients.missing_column_headers == {"one", "TWO", "Thirty_Three"}
    assert recipients.has_errors


@pytest.mark.parametrize(
    ("character", "name"),
    [
        (" ", "SPACE"),
        # these ones don’t have unicode names
        ("\n", None),  # newline
        ("\r", None),  # carriage return
        ("\t", None),  # tab
        ("\u180E", "MONGOLIAN VOWEL SEPARATOR"),
        ("\u200B", "ZERO WIDTH SPACE"),
        ("\u200C", "ZERO WIDTH NON-JOINER"),
        ("\u200D", "ZERO WIDTH JOINER"),
        ("\u2060", "WORD JOINER"),
        ("\uFEFF", "ZERO WIDTH NO-BREAK SPACE"),
        # all the things
        (" \n\r\t\u000A\u000D\u180E\u200B\u200C\u200D\u2060\uFEFF", None),
    ],
)
def test_ignores_leading_whitespace_in_file(character, name):
    if name is not None:
        assert unicodedata.name(character) == name

    recipients = RecipientCSV(
        "{}emailaddress\ntest@example.com".format(character),
        template=_sample_template("email"),
    )
    first_row = recipients[0]

    assert recipients.column_headers == ["emailaddress"]
    assert recipients.recipient_column_headers == ["email address"]
    assert recipients.missing_column_headers == set()
    assert recipients.placeholders == ["email address"]

    assert first_row.get("email address").data == "test@example.com"
    assert first_row["email address"].data == "test@example.com"
    assert first_row.recipient == "test@example.com"

    assert not recipients.has_errors


def test_error_if_too_many_recipients():
    recipients = RecipientCSV(
        "phone number,\n2348675309,\n2348675309,\n2348675309,",
        template=_sample_template("sms"),
        remaining_messages=2,
    )
    assert recipients.has_errors
    assert recipients.more_rows_than_can_send


def test_dont_error_if_too_many_recipients_not_specified():
    recipients = RecipientCSV(
        "phone number,\n2348675309,\n2348675309,\n2348675309,",
        template=_sample_template("sms"),
    )
    assert not recipients.has_errors
    assert not recipients.more_rows_than_can_send


@pytest.mark.parametrize(
    ("index", "expected_row"),
    [
        (
            0,
            {
                "phone number": "07700 90000 1",
                "colour": "red",
            },
        ),
        (
            1,
            {
                "phone_number": "07700 90000 2",
                "COLOUR": "green",
            },
        ),
        (
            2,
            {"p h o n e  n u m b e r": "07700 90000 3", "   colour   ": "blue"},
        ),
        pytest.param(
            3,
            {"phone number": "foo"},
            marks=pytest.mark.xfail(raises=IndexError),
        ),
        (
            -1,
            {"p h o n e  n u m b e r": "07700 90000 3", "   colour   ": "blue"},
        ),
    ],
)
def test_recipients_can_be_accessed_by_index(index, expected_row):
    recipients = RecipientCSV(
        """
            phone number, colour
            07700 90000 1, red
            07700 90000 2, green
            07700 90000 3, blue
        """,
        template=_sample_template("sms"),
    )
    for key, value in expected_row.items():
        assert recipients[index][key].data == value


@pytest.mark.parametrize("international_sms", [True, False])
def test_multiple_sms_recipient_columns(international_sms):
    recipients = RecipientCSV(
        """
            phone number, phone number, phone_number, foo
            234-867-5301, 234-867-5302, 234-867-5309, bar
        """,
        template=_sample_template("sms"),
        allow_international_sms=international_sms,
    )
    assert recipients.column_headers == ["phone number", "phone_number", "foo"]
    assert (
        recipients.column_headers_as_column_keys == dict(phonenumber="", foo="").keys()
    )
    assert recipients.rows[0].get("phone number").data == ("234-867-5309")
    assert recipients.rows[0].get("phone_number").data == ("234-867-5309")
    assert recipients.rows[0].get("phone number").error is None
    assert recipients.duplicate_recipient_column_headers == OrderedSet(
        ["phone number", "phone_number"]
    )
    assert recipients.has_errors


@pytest.mark.parametrize(
    "column_name",
    [
        "phone_number",
        "phonenumber",
        "phone number",
        "phone-number",
        "p h o n e  n u m b e r",
    ],
)
def test_multiple_sms_recipient_columns_with_missing_data(column_name):
    recipients = RecipientCSV(
        """
            names, phone number, {}
            "Joanna and Steve", 07900 900111
        """.format(
            column_name
        ),
        template=_sample_template("sms"),
        allow_international_sms=True,
    )
    expected_column_headers = ["names", "phone number"]
    if column_name != "phone number":
        expected_column_headers.append(column_name)
    assert recipients.column_headers == expected_column_headers
    assert (
        recipients.column_headers_as_column_keys
        == dict(phonenumber="", names="").keys()
    )
    # A piece of weirdness uncovered: since rows are created before spaces in column names are normalised, when
    # there are duplicate recipient columns and there is data for only one of the columns, if the columns have the same
    # spacing, phone number data will be a list of this one phone number and None, while if the spacing style differs
    # between two duplicate column names, the phone number data will be None. If there are no duplicate columns
    # then our code finds the phone number well regardless of the spacing, so this should not affect our users.
    phone_number_data = None
    if column_name == "phone number":
        phone_number_data = ["07900 900111", None]
    assert recipients.rows[0]["phonenumber"].data == phone_number_data
    assert recipients.rows[0].get("phone number").error is None
    expected_duplicated_columns = ["phone number"]
    if column_name != "phone number":
        expected_duplicated_columns.append(column_name)
    assert recipients.duplicate_recipient_column_headers == OrderedSet(
        expected_duplicated_columns
    )
    assert recipients.has_errors


def test_multiple_email_recipient_columns():
    recipients = RecipientCSV(
        """
            EMAILADDRESS, email_address, foo
            one@two.com,  two@three.com, bar
        """,
        template=_sample_template("email"),
    )
    assert recipients.rows[0].get("email address").data == ("two@three.com")
    assert recipients.rows[0].get("email address").error is None
    assert recipients.has_errors
    assert recipients.duplicate_recipient_column_headers == OrderedSet(
        ["EMAILADDRESS", "email_address"]
    )
    assert recipients.has_errors


def test_displayed_rows_when_some_rows_have_errors():
    recipients = RecipientCSV(
        """
            email address, name
            a@b.com,
            a@b.com,
            a@b.com, My Name
            a@b.com,
            a@b.com,
        """,
        template=_sample_template("email", "((name))"),
        max_errors_shown=3,
    )

    assert len(list(recipients.displayed_rows)) == 3


def test_displayed_rows_when_there_are_no_rows_with_errors():
    recipients = RecipientCSV(
        """
            email address, name
            a@b.com, My Name
            a@b.com, My Name
            a@b.com, My Name
            a@b.com, My Name
        """,
        template=_sample_template("email", "((name))"),
        max_errors_shown=3,
    )

    assert len(list(recipients.displayed_rows)) == 4


def test_multi_line_placeholders_work():
    recipients = RecipientCSV(
        """
            email address, data
            a@b.com, "a\nb\n\nc"
        """,
        template=_sample_template("email", "((data))"),
    )

    assert recipients.rows[0].personalisation["data"] == "a\nb\n\nc"


def test_email_validation_speed():
    email_addresses = "\n".join(
        (
            "{a}{b}@example-{n}.com,Example,Thursday".format(
                n=randrange(1000),
                a=choice(string.ascii_letters),
                b=choice(string.ascii_letters),
            )
            for i in range(1000)
        )
    )
    recipients = RecipientCSV(
        "email address,name,day\n" + email_addresses,
        template=_sample_template(
            "email",
            content=f"""
                hello ((name)) today is ((day))
                here’s the letter ‘a’ 1000 times:
                {'a' * 1000}
            """,
        ),
    )
    for row in recipients:
        assert not row.has_error


@pytest.mark.parametrize("should_validate", [True, False])
def test_recipient_csv_checks_should_validate_flag(should_validate):
    template = _sample_template("sms")
    template.is_message_empty = Mock(return_value=False)

    recipients = RecipientCSV(
        """phone number,name
        2348675309, test1
        +447700 900 460,test2""",
        template=template,
        should_validate=should_validate,
    )

    recipients._get_error_for_field = Mock(return_value=None)

    list(recipients.get_rows())

    assert template.is_message_empty.called is should_validate
    assert recipients._get_error_for_field.called is should_validate
