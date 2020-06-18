from abc import ABC, abstractmethod
from collections import defaultdict
from functools import partial
from threading import RLock

import cachetools

from gds_metrics import Histogram

from app import db
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.api_key_dao import get_model_api_keys

caches = defaultdict(partial(cachetools.TTLCache, maxsize=1024, ttl=2))
locks = defaultdict(RLock)


AUTH_DB_CONNECTION_DURATION_SECONDS = Histogram(
    'auth_db_connection_duration_seconds',
    'Time taken to get DB connection and fetch service from database',
)


def cache(func):
    @cachetools.cached(
        cache=caches[func.__qualname__],
        lock=locks[func.__qualname__],
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


class SerialisedModel(ABC):

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


class SerialisedModelCollection(ABC):

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

    @classmethod
    @cache
    def from_template_id_and_service_id(cls, template_id, service_id):

        from app.dao.templates_dao import dao_get_template_by_id_and_service_id
        from app.schemas import template_schema

        fetched_template = dao_get_template_by_id_and_service_id(
            template_id=template_id,
            service_id=service_id
        )

        template_dict = template_schema.dump(fetched_template).data

        db.session.commit()
        return cls(template_dict)


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

    @classmethod
    @cache
    def from_id(cls, service_id):
        from app.schemas import service_schema
        with AUTH_DB_CONNECTION_DURATION_SECONDS.time():
            fetched = dao_fetch_service_by_id(service_id)
        return cls(service_schema.dump(fetched).data)


class SerialisedAPIKey(SerialisedModel):
    ALLOWED_PROPERTIES = {
        'id',
        'secret',
        'expiry_date',
        'key_type',
    }


class SerialisedAPIKeyCollection(SerialisedModelCollection):
    model = SerialisedAPIKey

    @classmethod
    @cache
    def from_service_id(cls, service_id):
        return cls([
            {k: getattr(key, k) for k in SerialisedAPIKey.ALLOWED_PROPERTIES}
            for key in get_model_api_keys(service_id)
        ])
