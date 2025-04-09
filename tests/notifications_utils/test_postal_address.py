import pytest

from notifications_utils.countries import Country
from notifications_utils.countries.data import Postage
from notifications_utils.insensitive_dict import InsensitiveDict
from notifications_utils.postal_address import (
    PostalAddress,
    format_postcode_for_printing,
    is_a_real_uk_postcode,
    normalise_postcode,
)


def test_raw_address():
    raw_address = "a\n\n\tb\r       c         "
    assert PostalAddress(raw_address).raw_address == raw_address


@pytest.mark.parametrize(
    ("address", "expected_country"),
    [
        (
            """
        123 Example Street
        City of Town
        SW1A 1AA
        """,
            Country("United Kingdom"),
        ),
        (
            """
        123 Example Street
        City of Town
        SW1A 1AA
        United Kingdom
        """,
            Country("United Kingdom"),
        ),
        (
            """
        123 Example Street
        City of Town
        Wales
        """,
            Country("United Kingdom"),
        ),
        (
            """
        123 Example Straße
        Deutschland
        """,
            Country("Germany"),
        ),
    ],
)
def test_country(address, expected_country):
    assert PostalAddress(address).country == expected_country


@pytest.mark.parametrize(
    ("address", "enough_lines_expected"),
    [
        (
            "",
            False,
        ),
        (
            """
        123 Example Street
        City of Town
        SW1A 1AA
        """,
            True,
        ),
        (
            """
        123 Example Street
        City of Town
        United Kingdom
        """,
            False,
        ),
        (
            """
        123 Example Street


        City of Town
        """,
            False,
        ),
        (
            """
        1
        2
        3
        4
        5
        6
        7
        8
        """,
            True,
        ),
    ],
)
def test_has_enough_lines(address, enough_lines_expected):
    assert PostalAddress(address).has_enough_lines is enough_lines_expected


@pytest.mark.parametrize(
    ("address", "too_many_lines_expected"),
    [
        (
            "",
            False,
        ),
        (
            """
        Line 1
        Line 2
        Line 3
        Line 4
        Line 5
        Line 6
        Line 7
        """,
            False,
        ),
        (
            """
        Line 1

        Line 2

        Line 3

        Line 4

        Line 5

        Line 6

        Line 7
        """,
            False,
        ),
        (
            """
        Line 1
        Line 2
        Line 3
        Line 4
        Line 5
        Line 6
        Line 7
        Scotland
        """,
            False,
        ),
        (
            """
        Line 1
        Line 2
        Line 3
        Line 4
        Line 5
        Line 6
        Line 7
        Line 8
        """,
            True,
        ),
    ],
)
def test_has_too_many_lines(address, too_many_lines_expected):
    assert PostalAddress(address).has_too_many_lines is too_many_lines_expected


@pytest.mark.parametrize(
    ("address", "expected_postcode"),
    [
        (
            "",
            None,
        ),
        (
            """
        123 Example Street
        City of Town
        SW1A 1AA
        """,
            "SW1A 1AA",
        ),
        (
            """
        123 Example Street
        City of Town
        S W1 A 1 AA
        """,
            "SW1A 1AA",
        ),
        (
            """
        123 Example Straße
        Deutschland
        """,
            None,
        ),
        (
            """
        123 Example Straße
        SW1A 1AA
        Deutschland
        """,
            None,
        ),
    ],
)
def test_postcode(address, expected_postcode):
    assert PostalAddress(address).has_valid_postcode is bool(expected_postcode)
    assert PostalAddress(address).postcode == expected_postcode


@pytest.mark.parametrize(
    ("address", "expected_result"),
    [
        (
            "",
            False,
        ),
        (
            """
        1[23 Example Street)
        C@ity of Town
        SW1A 1AA
        """,
            False,
        ),
        (
            """
        [123 Example Street
        (ity of Town
        ]S W1 A 1 AA
        """,
            True,
        ),
        (
            r"""
        123 Example Straße
        SW1A 1AA
        \Deutschland
        """,
            True,
        ),
        (
            r"""
        >123 Example Straße
        SW1A 1AA
        Deutschland
        """,
            True,
        ),
        (
            """
        ~123 Example Street
        City of Town
        SW1 A 1 AA
        """,
            True,
        ),
    ],
)
def test_has_invalid_characters(address, expected_result):
    assert PostalAddress(address).has_invalid_characters is expected_result


@pytest.mark.parametrize(
    ("address", "expected_international"),
    [
        (
            "",
            False,
        ),
        (
            """
        123 Example Street
        City of Town
        SW1A 1AA
        """,
            False,
        ),
        (
            """
        123 Example Street
        City of Town
        United Kingdom
        """,
            False,
        ),
        (
            """
        123 Example Street
        City of Town
        Guernsey
        """,
            False,
        ),
        (
            """
        123 Example Straße
        Deutschland
        """,
            True,
        ),
    ],
)
def test_international(address, expected_international):
    assert PostalAddress(address).international is expected_international


@pytest.mark.parametrize(
    ("address", "expected_normalised", "expected_as_single_line"),
    [
        (
            "",
            "",
            "",
        ),
        (
            """
        123 Example    St  .
        City    of Town

        S W1 A 1 AA
        """,
            ("123 Example St.\n" "City of Town\n" "SW1A 1AA"),
            ("123 Example St., City of Town, SW1A 1AA"),
        ),
        (
            (
                "123 Example St. \t  ,    \n"
                ", , ,  ,   ,     ,        ,\n"
                "City of Town, Region,\n"
                "SW1A 1AA,,\n"
            ),
            ("123 Example St.\n" "City of Town, Region\n" "SW1A 1AA"),
            ("123 Example St., City of Town, Region, SW1A 1AA"),
        ),
        (
            """
          123  Example Straße
        Deutschland


        """,
            ("123 Example Straße\n" "Germany"),
            ("123 Example Straße, Germany"),
        ),
    ],
)
def test_normalised(address, expected_normalised, expected_as_single_line):
    assert PostalAddress(address).normalised == expected_normalised
    assert PostalAddress(address).as_single_line == expected_as_single_line


@pytest.mark.parametrize(
    ("address", "expected_postage"),
    [
        (
            "",
            Postage.UK,
        ),
        (
            """
        123 Example Street
        City of Town
        SW1A 1AA
        """,
            Postage.UK,
        ),
        (
            """
        123 Example Street
        City of Town
        Scotland
        """,
            Postage.UK,
        ),
        (
            """
        123 Example Straße
        Deutschland
        """,
            Postage.EUROPE,
        ),
        (
            """
        123 Rue Example
        Côte d'Ivoire
        """,
            Postage.REST_OF_WORLD,
        ),
    ],
)
def test_postage(address, expected_postage):
    assert PostalAddress(address).postage == expected_postage


@pytest.mark.parametrize(
    "personalisation",
    [
        {
            "address_line_1": "123 Example Street",
            "address_line_3": "City of Town",
            "address_line_4": "",
            "postcode": "SW1A1AA",
            "ignore me": "ignore me",
        },
        {
            "address_line_1": "123 Example Street",
            "address_line_3": "City of Town",
            "address_line_4": "SW1A1AA",
        },
        {
            "address_line_2": "123 Example Street",
            "address_line_5": "City of Town",
            "address_line_7": "SW1A1AA",
        },
        {
            "address_line_1": "123 Example Street",
            "address_line_3": "City of Town",
            "address_line_7": "SW1A1AA",
            "postcode": "ignored if address line 7 provided",
        },
        InsensitiveDict(
            {
                "address line 1": "123 Example Street",
                "ADDRESS_LINE_2": "City of Town",
                "Address-Line-7": "Sw1a  1aa",
            }
        ),
    ],
)
def test_from_personalisation(personalisation):
    assert PostalAddress.from_personalisation(personalisation).normalised == (
        "123 Example Street\n" "City of Town\n" "SW1A 1AA"
    )


def test_from_personalisation_handles_int():
    personalisation = {
        "address_line_1": 123,
        "address_line_2": "Example Street",
        "address_line_3": "City of Town",
        "address_line_4": "SW1A1AA",
    }
    assert PostalAddress.from_personalisation(personalisation).normalised == (
        "123\n" "Example Street\n" "City of Town\n" "SW1A 1AA"
    )


@pytest.mark.parametrize(
    ("address", "expected_personalisation"),
    [
        (
            "",
            {
                "address_line_1": "",
                "address_line_2": "",
                "address_line_3": "",
                "address_line_4": "",
                "address_line_5": "",
                "address_line_6": "",
                "address_line_7": "",
                "postcode": "",
            },
        ),
        (
            """
        123 Example Street
        City of Town
        SW1A1AA
        """,
            {
                "address_line_1": "123 Example Street",
                "address_line_2": "City of Town",
                "address_line_3": "",
                "address_line_4": "",
                "address_line_5": "",
                "address_line_6": "",
                "address_line_7": "SW1A 1AA",
                "postcode": "SW1A 1AA",
            },
        ),
        (
            """
        One
        Two
        Three
        Four
        Five
        Six
        Seven
        Eight
        """,
            {
                "address_line_1": "One",
                "address_line_2": "Two",
                "address_line_3": "Three",
                "address_line_4": "Four",
                "address_line_5": "Five",
                "address_line_6": "Six",
                "address_line_7": "Eight",
                "postcode": "Eight",
            },
        ),
    ],
)
def test_as_personalisation(address, expected_personalisation):
    assert PostalAddress(address).as_personalisation == expected_personalisation


@pytest.mark.parametrize(
    ("address", "expected_bool"),
    [
        ("", False),
        (" ", False),
        ("\n\n  \n", False),
        ("a", True),
    ],
)
def test_bool(address, expected_bool):
    assert bool(PostalAddress(address)) is expected_bool


@pytest.mark.parametrize(
    ("postcode", "normalised_postcode"),
    [
        ("SW1 3EF", "SW13EF"),
        ("SW13EF", "SW13EF"),
        ("sw13ef", "SW13EF"),
        ("Sw13ef", "SW13EF"),
        ("sw1 3ef", "SW13EF"),
        (" SW1    3EF  ", "SW13EF"),
    ],
)
def test_normalise_postcode(postcode, normalised_postcode):
    assert normalise_postcode(postcode) == normalised_postcode


@pytest.mark.parametrize(
    ("postcode", "result"),
    [
        # real standard UK poscodes
        ("SW1 3EF", True),
        ("SW13EF", True),
        ("SE1 63EF", True),
        ("N5 1AA", True),
        ("SO14 6WB", True),
        ("so14 6wb", True),
        ("so14\u00a06wb", True),
        # invalida / incomplete postcodes
        ("N5", False),
        ("SO144 6WB", False),
        ("SO14 6WBA", False),
        ("", False),
        ("Bad postcode", False),
        # valid British Forces postcodes
        ("BFPO1234", True),
        ("BFPO C/O 1234", True),
        ("BFPO 1234", True),
        ("BFPO1", True),
        # invalid British Forces postcodes
        ("BFPO", False),
        ("BFPO12345", False),
        # Giro Bank valid postcode and invalid postcode
        ("GIR0AA", True),
        ("GIR0AB", False),
    ],
)
def test_if_postcode_is_a_real_uk_postcode(postcode, result):
    assert is_a_real_uk_postcode(postcode) is result


def test_if_postcode_is_a_real_uk_postcode_normalises_before_checking_postcode(mocker):
    normalise_postcode_mock = mocker.patch(
        "notifications_utils.postal_address.normalise_postcode"
    )
    normalise_postcode_mock.return_value = "SW11AA"
    assert is_a_real_uk_postcode("sw1  1aa") is True


@pytest.mark.parametrize(
    ("postcode", "postcode_with_space"),
    [
        ("SW13EF", "SW1 3EF"),
        ("SW1 3EF", "SW1 3EF"),
        ("N5 3EF", "N5 3EF"),
        ("N5     3EF", "N5 3EF"),
        ("N53EF   ", "N5 3EF"),
        ("n53Ef", "N5 3EF"),
        ("n5 \u00a0 \t 3Ef", "N5 3EF"),
        ("SO146WB", "SO14 6WB"),
        ("BFPO2", "BFPO 2"),
        ("BFPO232", "BFPO 232"),
        ("BFPO 2432", "BFPO 2432"),
        ("BFPO C/O 2", "BFPO C/O 2"),
        ("BFPO c/o 232", "BFPO C/O 232"),
        ("GIR0AA", "GIR 0AA"),
    ],
)
def test_format_postcode_for_printing(postcode, postcode_with_space):
    assert format_postcode_for_printing(postcode) == postcode_with_space


@pytest.mark.parametrize(
    ("address", "international", "expected_valid"),
    [
        (
            """
            UK address
            Service can’t send internationally
            SW1A 1AA
        """,
            False,
            True,
        ),
        (
            """
            UK address
            Service can send internationally
            SW1A 1AA
        """,
            True,
            True,
        ),
        (
            """
            Overseas address
            Service can’t send internationally
            Guinea-Bissau
        """,
            False,
            False,
        ),
        (
            """
            Overseas address
            Service can send internationally
            Guinea-Bissau
        """,
            True,
            True,
        ),
        (
            """
            Overly long address
            2
            3
            4
            5
            6
            7
            8
        """,
            True,
            False,
        ),
        (
            """
            Address too short
            2
        """,
            True,
            False,
        ),
        (
            """
            No postcode or country
            Service can’t send internationally
            3
        """,
            False,
            False,
        ),
        (
            """
            No postcode or country
            Service can send internationally
            3
        """,
            True,
            False,
        ),
        (
            """
            Postcode and country
            Service can’t send internationally
            SW1 1AA
            France
        """,
            False,
            False,
        ),
    ],
)
def test_valid_with_international_parameter(address, international, expected_valid):
    postal_address = PostalAddress(
        address,
        allow_international_letters=international,
    )
    assert postal_address.valid is expected_valid
    assert postal_address.has_valid_last_line is expected_valid


@pytest.mark.parametrize(
    "address",
    [
        """
        Too short, valid postcode
        SW1A 1AA
    """,
        """
        Too short, valid country
        Bhutan
    """,
        """
        Too long, valid postcode
        2
        3
        4
        5
        6
        7
        SW1A 1AA
    """,
        """
        Too long, valid country
        2
        3
        4
        5
        6
        7
        Bhutan
    """,
    ],
)
def test_valid_last_line_too_short_too_long(address):
    postal_address = PostalAddress(address, allow_international_letters=True)
    assert postal_address.valid is False
    assert postal_address.has_valid_last_line is True


def test_valid_with_invalid_characters():
    address = "Valid\nExcept\n[For one character\nBhutan\n"
    assert PostalAddress(address, allow_international_letters=True).valid is False


@pytest.mark.parametrize(
    ("international", "expected_valid"),
    [
        (False, False),
        (True, True),
    ],
)
def test_valid_from_personalisation_with_international_parameter(
    international, expected_valid
):
    assert (
        PostalAddress.from_personalisation(
            {"address_line_1": "A", "address_line_2": "B", "address_line_3": "Chad"},
            allow_international_letters=international,
        ).valid
        is expected_valid
    )
