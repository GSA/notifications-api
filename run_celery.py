#!/usr/bin/env python
from gevent import monkey

monkey.patch_all()

from flask import Flask  # noqa

# notify_celery is referenced from manifest_delivery_base.yml, and cannot be removed
from app import create_app, notify_celery  # noqa

application = Flask("delivery")
create_app(application)
application.app_context().push()
