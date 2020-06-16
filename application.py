##!/usr/bin/env python
from __future__ import print_function

from flask import Flask
import psycogreen.eventlet

from app import create_app

psycogreen.eventlet.patch_psycopg()

application = Flask('app')

create_app(application)
