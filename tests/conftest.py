import os
from contextlib import contextmanager

import pytest
from alembic.command import upgrade
from alembic.config import Config
from flask import Flask
from sqlalchemy_utils import create_database, database_exists, drop_database

from app import create_app


@pytest.fixture(scope="session")
def notify_app():
    app = Flask("test")
    create_app(app)
    return app


@pytest.fixture(scope="session")
def notify_api(notify_app):
    for error_handlers in notify_app.error_handler_spec.values():
        error_handlers.pop(500, None)
        if None in error_handlers:
            error_handlers[None] = {
                exc_class: error_handler
                for exc_class, error_handler in error_handlers[None].items()
                if exc_class != Exception
            }
            if error_handlers[None] == []:
                error_handlers.pop(None)

    ctx = notify_app.app_context()
    ctx.push()

    yield notify_app

    ctx.pop()


@pytest.fixture(scope="session")
def client(notify_api):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def _notify_db(notify_api):
    """
    Manages the connection to the database. Generally this shouldn't be used, instead you should use the
    `notify_db_session` fixture which also cleans up any data you've got left over after your test run.
    """
    with notify_api.app_context() as app_context:
        db = app_context.app.extensions["sqlalchemy"]

        # Check if test_notification_api exists, if not, create
        if not database_exists(db.engine.url):
            create_database(db.engine.url)

        BASE_DIR = os.path.dirname(os.path.dirname(__file__))
        ALEMBIC_CONFIG = os.path.join(BASE_DIR, "migrations")
        config = Config(ALEMBIC_CONFIG + "/alembic.ini")
        config.set_main_option("script_location", ALEMBIC_CONFIG)
        config.set_main_option(
            "sqlalchemy.url", app_context.app.config["SQLALCHEMY_DATABASE_URI"]
        )

        # Run migrations on the test database.
        upgrade(config, "head")

        yield db

        db.session.remove()
        # Check if test_notification_api exists, if so, drop
        if database_exists(db.engine.url):
            drop_database(db.engine.url)
        db.engine.dispose()


@pytest.fixture(scope="function")
def sms_providers(_notify_db):
    pass
    # get_provider_details_by_identifier("sns").priority = 100


@pytest.fixture(scope="function")
def notify_db_session(_notify_db, sms_providers):
    """
    This fixture clears down all non static data after your test run. It yields the sqlalchemy session variable
    so you can manually add, commit, etc if needed.

    `notify_db_session.commit()`
    """
    yield _notify_db.session

    _notify_db.session.remove()
    with _notify_db.engine.begin() as connection:
        for tbl in reversed(_notify_db.metadata.sorted_tables):
            if tbl.name not in [
                "provider_details",
                "key_types",
                "branding_type",
                "job_status",
                "provider_details_history",
                "template_process_type",
                "notifications_all_time_view",
                "notification_status_types",
                "organization_types",
                "service_permission_types",
                "auth_type",
                "invite_status_type",
                "service_callback_type",
            ]:
                connection.execute(tbl.delete())
    _notify_db.session.commit()


@pytest.fixture
def os_environ():
    """
    clear os.environ, and restore it after the test runs
    """
    # for use whenever you expect code to edit environment variables
    old_env = os.environ.copy()
    os.environ.clear()

    yield

    # clear afterwards in case anything extra was added to the environment during the test
    os.environ.clear()
    for k, v in old_env.items():
        os.environ[k] = v


def pytest_generate_tests(metafunc):
    # Copied from https://gist.github.com/pfctdayelise/5719730
    idparametrize = metafunc.definition.get_closest_marker("idparametrize")
    if idparametrize:
        argnames, testdata = idparametrize.args
        ids, argvalues = zip(*sorted(testdata.items()))
        metafunc.parametrize(argnames, argvalues, ids=ids)


@contextmanager
def set_config(app, name, value):
    old_val = app.config.get(name)
    app.config[name] = value
    try:
        yield
    finally:
        app.config[name] = old_val


@contextmanager
def set_config_values(app, dict):
    old_values = {}

    for key in dict:
        old_values[key] = app.config.get(key)
        app.config[key] = dict[key]

    try:
        yield
    finally:
        for key in dict:
            app.config[key] = old_values[key]


class Matcher:
    def __init__(self, description, key):
        self.description = description
        self.key = key

    def __eq__(self, other):
        return self.key(other)

    def __repr__(self):
        return "<Matcher: {}>".format(self.description)
