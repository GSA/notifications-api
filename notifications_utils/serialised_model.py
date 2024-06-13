from abc import ABC, abstractmethod


class SerialisedModel(ABC):
    """
    A SerialisedModel takes a dictionary, typically created by
    serialising a database object. It then takes the value of specified
    keys from the dictionary and adds them to itself as properties, so
    that it can be interacted with like any other object. It is cleaner
    and safer than dealing with dictionaries directly because it
    guarantees that:
    - all of the ALLOWED_PROPERTIES are present in the underlying
      dictionary
    - any other abritrary properties of the underlying dictionary can’t
      be accessed

    If you are adding a new field to a model, you should ensure that
    all sources of the cache data are updated to return that new field,
    then clear the cache, before adding that field to the
    ALLOWED_PROPERTIES list.
    """

    @property
    @abstractmethod
    def ALLOWED_PROPERTIES(self):
        pass

    def __init__(self, _dict):
        for property in self.ALLOWED_PROPERTIES:
            setattr(self, property, _dict[property])


class SerialisedModelCollection(ABC):
    """
    A SerialisedModelCollection takes a list of dictionaries, typically
    created by serialising database objects. When iterated over it
    returns a model instance for each of the items in the list.
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

    def __len__(self):
        return len(self.items)

    def __add__(self, other):
        return list(self) + list(other)

    def __radd__(self, other):
        return list(other) + list(self)
