from ordered_set import OrderedSet

from notifications_utils.insensitive_dict import InsensitiveDict


class TemplateChange:
    def __init__(self, old_template, new_template):
        self.old_placeholders = InsensitiveDict.from_keys(old_template.placeholders)
        self.new_placeholders = InsensitiveDict.from_keys(new_template.placeholders)

    @property
    def has_different_placeholders(self):
        return bool(self.new_placeholders.keys() ^ self.old_placeholders.keys())

    @property
    def placeholders_added(self):
        return OrderedSet(
            [
                self.new_placeholders.get(key)
                for key in self.new_placeholders.keys() - self.old_placeholders.keys()
            ]
        )

    @property
    def placeholders_removed(self):
        return OrderedSet(
            [
                self.old_placeholders.get(key)
                for key in self.old_placeholders.keys() - self.new_placeholders.keys()
            ]
        )
