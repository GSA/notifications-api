from gevent import monkey

monkey.patch_all()

from application import application  # noqa
