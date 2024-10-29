class Pagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = (total + per_page - 1) // per_page
        self.prev_num = page - 1 if page > 1 else None
        self.next_num = page + 1 if page < self.pages else None

    def has_next(self):
        return self.page < self.pages

    def has_prev(self):
        return self.page > 1
