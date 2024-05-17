import pytest

from notifications_utils.countries import Country, CountryMapping, CountryNotFoundError
from notifications_utils.countries.data import (
    _EUROPEAN_ISLANDS_LIST,
    _UK_ISLANDS_LIST,
    ADDITIONAL_SYNONYMS,
    COUNTRIES_AND_TERRITORIES,
    ROYAL_MAIL_EUROPEAN,
    UK,
    UK_ISLANDS,
    WELSH_NAMES,
    Postage,
)

from .country_synonyms import ALL as ALL_SYNONYMS
from .country_synonyms import CROWDSOURCED_MISTAKES


def test_constants():
    assert UK == "United Kingdom"
    assert UK_ISLANDS == [
        ("Alderney", UK),
        ("Brecqhou", UK),
        ("Guernsey", UK),
        ("Herm", UK),
        ("Isle of Man", UK),
        ("Jersey", UK),
        ("Jethou", UK),
        ("Sark", UK),
    ]
    assert Postage.EUROPE == "europe"
    assert Postage.REST_OF_WORLD == "rest-of-world"
    assert Postage.UK == "united-kingdom"


@pytest.mark.parametrize(("synonym", "canonical"), ADDITIONAL_SYNONYMS)
def test_hand_crafted_synonyms_map_to_canonical_countries(synonym, canonical):
    exceptions_to_canonical_countries = [
        "Easter Island",
        "South Georgia and the South Sandwich Islands",
    ]

    synonyms = dict(COUNTRIES_AND_TERRITORIES).keys()
    canonical_names = list(dict(COUNTRIES_AND_TERRITORIES).values())

    assert canonical in (
        canonical_names
        + _EUROPEAN_ISLANDS_LIST
        + _UK_ISLANDS_LIST
        + exceptions_to_canonical_countries
    )

    assert synonym not in {CountryMapping.make_key(synonym_) for synonym_ in synonyms}
    assert Country(synonym).canonical_name == canonical


@pytest.mark.parametrize(("welsh_name", "canonical"), WELSH_NAMES)
def test_welsh_names_map_to_canonical_countries(welsh_name, canonical):
    assert Country(canonical).canonical_name == canonical
    assert Country(welsh_name).canonical_name == canonical


def test_all_synonyms():
    for search, expected in ALL_SYNONYMS:
        assert Country(search).canonical_name == expected


def test_crowdsourced_test_data():
    for search, expected_country, expected_postage in CROWDSOURCED_MISTAKES:
        if expected_country or expected_postage:
            assert Country(search).canonical_name == expected_country
            assert Country(search).postage_zone == expected_postage


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("u.s.a", "United States"),
        ("america", "United States"),
        ("United States America", "United States"),
        ("ROI", "Ireland"),
        ("Irish Republic", "Ireland"),
        ("Rep of Ireland", "Ireland"),
        ("RepOfIreland", "Ireland"),
        ("deutschland", "Germany"),
        ("UK", "United Kingdom"),
        ("England", "United Kingdom"),
        ("Northern Ireland", "United Kingdom"),
        ("Scotland", "United Kingdom"),
        ("Wales", "United Kingdom"),
        ("N. Ireland", "United Kingdom"),
        ("GB", "United Kingdom"),
        ("NIR", "United Kingdom"),
        ("SCT", "United Kingdom"),
        ("WLS", "United Kingdom"),
        ("gambia", "The Gambia"),
        ("Jersey", "United Kingdom"),
        ("Guernsey", "United Kingdom"),
        ("Lubnān", "Lebanon"),
        ("Lubnan", "Lebanon"),
        ("ESPAÑA", "Spain"),
        ("ESPANA", "Spain"),
        ("the democratic people's republic of korea", "North Korea"),
        ("the democratic peoples republic of korea", "North Korea"),
        ("ALAND", "Åland Islands"),
        ("Sao Tome + Principe", "Sao Tome and Principe"),
        ("Sao Tome & Principe", "Sao Tome and Principe"),
        ("Antigua, and Barbuda", "Antigua and Barbuda"),
        ("Azores", "Azores"),
        ("Autonomous Region of the Azores", "Azores"),
        ("Canary Islands", "Canary Islands"),
        ("Islas Canarias", "Canary Islands"),
        ("Canaries", "Canary Islands"),
        ("Madeira", "Madeira"),
        ("Autonomous Region of Madeira", "Madeira"),
        ("Região Autónoma da Madeira", "Madeira"),
        ("Balearic Islands", "Balearic Islands"),
        ("Islas Baleares", "Balearic Islands"),
        ("Illes Balears", "Balearic Islands"),
        ("Corsica", "Corsica"),
        ("Corse", "Corsica"),
    ],
)
def test_hand_crafted_synonyms(search, expected):
    assert Country(search).canonical_name == expected


def test_auto_checking_for_country_starting_with_the():
    canonical_names = dict(COUNTRIES_AND_TERRITORIES).values()
    synonyms = dict(COUNTRIES_AND_TERRITORIES).keys()
    assert "The Gambia" in canonical_names
    assert "Gambia" not in synonyms
    assert Country("Gambia").canonical_name == "The Gambia"


@pytest.mark.parametrize(
    ("search", "expected_error_message"),
    [
        ("Qumran", "Not a known country or territory (Qumran)"),
        ("Kumrahn", "Not a known country or territory (Kumrahn)"),
    ],
)
def test_non_existant_countries(search, expected_error_message):
    with pytest.raises(KeyError) as error:
        Country(search)
    assert str(error.value) == repr(expected_error_message)
    assert isinstance(error.value, CountryNotFoundError)


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("u.s.a", "rest-of-world"),
        ("Rep of Ireland", "europe"),
        ("deutschland", "europe"),
        ("UK", "united-kingdom"),
        ("Jersey", "united-kingdom"),
        ("Guernsey", "united-kingdom"),
        ("isle-of-man", "united-kingdom"),
        ("ESPAÑA", "europe"),
    ],
)
def test_get_postage(search, expected):
    assert Country(search).postage_zone == expected


def test_euro_postage_zone():
    for search in ROYAL_MAIL_EUROPEAN:
        assert Country(search).postage_zone == Postage.EUROPE
