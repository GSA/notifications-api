##!/usr/bin/env python

from __future__ import print_function

import truststore

truststore.inject_into_ssl()  # noqa

from flask import Flask  # noqa
from werkzeug.serving import WSGIRequestHandler  # noqa

from app import create_app, socketio  # noqa

WSGIRequestHandler.version_string = lambda self: "SecureServer"

application = Flask("app")

create_app(application)
