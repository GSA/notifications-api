class Take(str):
    def then(self, func, *args, **kwargs):
        return self.__class__(func(self, *args, **kwargs))
