from abc import ABC, abstractmethod
from collections import defaultdict
from functools import partial
from threading import RLock

import cachetools

caches = defaultdict(partial(cachetools.TTLCache, maxsize=1024, ttl=2))
locks = defaultdict(RLock)


class CacheMixin:

    @classmethod
    def cache(cls, func):

        @cachetools.cached(cache=caches[cls.__name__], lock=locks[cls.__name__])
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper


class SerialisedModel(ABC, CacheMixin):

    """
    A SerialisedModel takes a dictionary, typically created by
    serialising a database object. It then takes the value of specified
    keys from the dictionary and adds them to itself as properties, so
    that it can be interacted with like a normal database model object,
    but with no risk that it will actually go back to the database.
    """

    @property
    @abstractmethod
    def ALLOWED_PROPERTIES(self):
        pass

    def __init__(self, _dict):
        for property in self.ALLOWED_PROPERTIES:
            setattr(self, property, _dict[property])

    def __dir__(self):
        return super().__dir__() + list(sorted(self.ALLOWED_PROPERTIES))


class SerialisedModelCollection(ABC, CacheMixin):

    """
    A SerialisedModelCollection takes a list of dictionaries, typically
    created by serialising database objects. When iterated over it
    returns a SerialisedModel instance for each of the items in the list.
    """

    @property
    @abstractmethod
    def model(self):
        pass

    def __init__(self, items):
        self.items = items

    def __bool__(self):
        return bool(self.items)

    def __getitem__(self, index):
        return self.model(self.items[index])


class SerialisedTemplate(SerialisedModel):
    ALLOWED_PROPERTIES = {
        'archived',
        'content',
        'id',
        'postage',
        'process_type',
        'reply_to_text',
        'subject',
        'template_type',
        'version',
    }


class SerialisedService(SerialisedModel):
    ALLOWED_PROPERTIES = {
        'id',
        'active',
        'contact_link',
        'email_from',
        'permissions',
        'research_mode',
        'restricted',
    }


class SerialisedAPIKey(SerialisedModel):
    ALLOWED_PROPERTIES = {
        'id',
        'secret',
        'expiry_date',
        'key_type',
    }


class SerialisedAPIKeyCollection(SerialisedModelCollection):
    model = SerialisedAPIKey
