from abc import ABC, abstractmethod


class JSONModel(ABC):

    @property
    @abstractmethod
    def ALLOWED_PROPERTIES(self):
        pass

    def __init__(self, _dict):
        self._dict = _dict
        for property in self.ALLOWED_PROPERTIES:
            setattr(self, property, _dict[property])

    def __dir__(self):
        return super().__dir__() + list(sorted(self.ALLOWED_PROPERTIES))


class TemplateJSONModel(JSONModel):
    ALLOWED_PROPERTIES = {
        'archived',
        'id',
        'postage',
        'process_type',
        'reply_to_text',
        'template_type',
        'version',
    }
