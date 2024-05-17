import pytest
import requests_mock
from flask import Flask

from notifications_utils import request_helper


class FakeService:
    id = "1234"


@pytest.fixture()
def app():
    flask_app = Flask(__name__)
    ctx = flask_app.app_context()
    ctx.push()

    yield flask_app

    ctx.pop()


@pytest.fixture()
def celery_app(mocker):
    app = Flask(__name__)
    app.config["CELERY"] = {"broker_url": "foo"}
    app.config["NOTIFY_TRACE_ID_HEADER"] = "Ex-Notify-Request-Id"
    request_helper.init_app(app)

    ctx = app.app_context()
    ctx.push()

    yield app
    ctx.pop()


@pytest.fixture(scope="session")
def sample_service():
    return FakeService()


@pytest.fixture()
def rmock():
    with requests_mock.mock() as rmock:
        yield rmock
