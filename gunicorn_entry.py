from gevent import monkey

monkey.patch_all()

from application import application as flask_app  # noqa
from app import socketio  # noqa

application = socketio
