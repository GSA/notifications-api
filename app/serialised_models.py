from abc import ABC, abstractmethod


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
