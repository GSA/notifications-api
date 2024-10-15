class Pagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = (total + per_page - 1) // per_page

    def has_next(self):
        return self.page < self.pages

    def has_prev(self):
        return self.page > 1
