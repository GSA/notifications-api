##!/usr/bin/env python

from __future__ import print_function

from flask import Flask  # noqa
from flask_caching import Cache
from werkzeug.serving import WSGIRequestHandler  # noqa

from app import create_app, socketio  # noqa

WSGIRequestHandler.version_string = lambda self: "SecureServer"

application = Flask("app")

create_app(application)

rest_cache = Cache(config={"CACHE_TYPE": "SimpleCache"})
rest_cache.init_app(application)
