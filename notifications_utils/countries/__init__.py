from functools import lru_cache

from notifications_utils.insensitive_dict import InsensitiveDict
from notifications_utils.sanitise_text import SanitiseASCII

from .data import (
    ADDITIONAL_SYNONYMS,
    COUNTRIES_AND_TERRITORIES,
    EUROPEAN_ISLANDS,
    ROYAL_MAIL_EUROPEAN,
    UK,
    UK_ISLANDS,
    WELSH_NAMES,
    Postage,
)


class CountryMapping(InsensitiveDict):
    @staticmethod
    @lru_cache(maxsize=2048, typed=False)
    def make_key(original_key):
        original_key = original_key.replace("&", "and")
        original_key = original_key.replace("+", "and")

        normalised = "".join(
            character.lower()
            for character in original_key
            if character not in " _-'’,.()"
        )

        if "?" in SanitiseASCII.encode(normalised):
            return normalised

        return SanitiseASCII.encode(normalised)

    def __contains__(self, key):
        if any(c.isdigit() for c in key):
            # A string with a digit can’t be a country and is probably a
            # postcode, so let’s do a little optimisation, skip the
            # expensive string manipulation to normalise the key and say
            # that there’s no matching country
            return False
        return super().__contains__(key)

    def __getitem__(self, key):
        for key_ in (key, f"the {key}", f"yr {key}", f"y {key}"):
            if key_ in self:
                return super().__getitem__(key_)

        raise CountryNotFoundError(f"Not a known country or territory ({key})")


countries = CountryMapping(
    dict(
        COUNTRIES_AND_TERRITORIES
        + UK_ISLANDS
        + EUROPEAN_ISLANDS
        + WELSH_NAMES
        + ADDITIONAL_SYNONYMS
    )
)


class Country:
    def __init__(self, given_name):
        self.canonical_name = countries[given_name]

    def __eq__(self, other):
        return self.canonical_name == other.canonical_name

    @property
    def postage_zone(self):
        if self.canonical_name == UK:
            return Postage.UK
        if self.canonical_name in ROYAL_MAIL_EUROPEAN:
            return Postage.EUROPE
        return Postage.REST_OF_WORLD


class CountryNotFoundError(KeyError):
    pass
