import json
import os


def _load_data(filename):
    with open(os.path.join(os.path.dirname(__file__), "_data", filename)) as contents:
        if filename.endswith(".json"):
            return json.load(contents)
        return [line.strip() for line in contents.readlines()]


def find_canonical(item, graph, key):
    if item["meta"]["canonical"]:
        return key, item["names"]["en-GB"]
    return find_canonical(
        graph[item["edges"]["from"][0]],
        graph,
        key,
    )


# Copied from
# https://github.com/alphagov/govuk-country-and-territory-autocomplete
# /blob/b61091a502983fd2a77b3cdb5f94a604412eb093
# /dist/location-autocomplete-graph.json
_graph = _load_data("location-autocomplete-graph.json")

UK = "United Kingdom"

ENDED_COUNTRIES = _load_data("ended-countries.json")
ADDITIONAL_SYNONYMS = list(_load_data("synonyms.json").items())
WELSH_NAMES = list(_load_data("welsh-names.json").items())
_UK_ISLANDS_LIST = _load_data("uk-islands.txt")
_EUROPEAN_ISLANDS_LIST = _load_data("european-islands.txt")

CURRENT_AND_ENDED_COUNTRIES_AND_TERRITORIES = [
    find_canonical(item, _graph, item["names"]["en-GB"]) for item in _graph.values()
]

COUNTRIES_AND_TERRITORIES = []

for synonym, canonical in CURRENT_AND_ENDED_COUNTRIES_AND_TERRITORIES:
    if canonical in _UK_ISLANDS_LIST:
        COUNTRIES_AND_TERRITORIES.append((synonym, UK))
    elif canonical in ENDED_COUNTRIES:
        succeeding_country = ENDED_COUNTRIES[canonical]
        if succeeding_country:
            COUNTRIES_AND_TERRITORIES.append((synonym, succeeding_country))
            COUNTRIES_AND_TERRITORIES.append((canonical, succeeding_country))
    else:
        COUNTRIES_AND_TERRITORIES.append((synonym, canonical))

UK_ISLANDS = [(synonym, UK) for synonym in _UK_ISLANDS_LIST]

EUROPEAN_ISLANDS = [(synonym, synonym) for synonym in _EUROPEAN_ISLANDS_LIST]

# Copied from https://www.royalmail.com/international-zones#europe
# Modified to use the canonical names for countries where incorrect
ROYAL_MAIL_EUROPEAN = _load_data("europe.txt")


class Postage:
    UK = "united-kingdom"
    FIRST = "first"
    SECOND = "second"
    EUROPE = "europe"
    REST_OF_WORLD = "rest-of-world"
