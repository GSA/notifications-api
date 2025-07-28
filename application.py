##!/usr/bin/env python

from __future__ import print_function

from gevent import monkey

monkey.patch_all()  # this has to be called before other imports or monkey patching doesn't happen


from flask import Flask  # noqa
from werkzeug.serving import WSGIRequestHandler  # noqa

from app import create_app, socketio  # noqa

WSGIRequestHandler.version_string = lambda self: "SecureServer"

application = Flask("app")

create_app(application)
