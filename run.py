# flake8: noqa: E402
import eventlet
eventlet.monkey_patch()

from flask import Flask
from app import create_app, socketio


def build_application():
    application = Flask("app")
    create_app(application)
    return application


if __name__ == "__main__":
    application = build_application()
    socketio.run(application, host="0.0.0.0", port=6011, debug=True, use_reloader=True)
