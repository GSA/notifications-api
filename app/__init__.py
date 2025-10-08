import logging as real_logging
import os
import secrets
import string
import time
import uuid
from contextlib import contextmanager
from threading import Lock
from time import monotonic

from celery import Celery, Task, current_task
from flask import (
    current_app,
    g,
    has_request_context,
    jsonify,
    make_response,
    request,
)
from flask.ctx import has_app_context
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy as _SQLAlchemy
from sqlalchemy import event
from werkzeug.exceptions import HTTPException as WerkzeugHTTPException
from werkzeug.local import LocalProxy

from app import config
from app.clients import NotificationProviderClients
from app.clients.cloudwatch.aws_cloudwatch import AwsCloudwatchClient
from app.clients.document_download import DocumentDownloadClient
from app.clients.email.aws_ses import AwsSesClient
from app.clients.email.aws_ses_stub import AwsSesStubClient
from app.clients.sms.aws_sns import AwsSnsClient
from notifications_utils import logging, request_helper
from notifications_utils.clients.encryption.encryption_client import Encryption
from notifications_utils.clients.redis.redis_client import RedisClient
from notifications_utils.clients.zendesk.zendesk_client import ZendeskClient

job_cache = {}
job_cache_lock = Lock()


class NotifyCelery(Celery):
    def init_app(self, app):
        self.task_cls = make_task(app)

        # Configure Celery app with options from the main app config.
        self.config_from_object(app.config["CELERY"])
        self.conf.worker_hijack_root_logger = False
        logger = real_logging.getLogger("celery")
        logger.propagate = False

    def send_task(self, name, args=None, kwargs=None, **other_kwargs):
        other_kwargs["headers"] = other_kwargs.get("headers") or {}

        if has_request_context() and hasattr(request, "request_id"):
            other_kwargs["headers"]["notify_request_id"] = request.request_id

        elif has_app_context() and "request_id" in g:
            other_kwargs["headers"]["notify_request_id"] = g.request_id

        return super().send_task(name, args, kwargs, **other_kwargs)


class SQLAlchemy(_SQLAlchemy):
    """We need to subclass SQLAlchemy in order to override create_engine options"""

    def apply_driver_hacks(self, app, info, options):
        sa_url, options = super().apply_driver_hacks(app, info, options)

        if "connect_args" not in options:
            options["connect_args"] = {}
        options["connect_args"]["options"] = "-c statement_timeout={}".format(
            int(app.config["SQLALCHEMY_STATEMENT_TIMEOUT"]) * 1000
        )

        return (sa_url, options)


# no monkey patching issue here.  All the real work to set the db up
# is done in db.init_app() which is called in create_app.  But we need
# to instantiate the db object here, because it's used in models.py
db = SQLAlchemy(
    engine_options={
        "pool_size": config.Config.SQLALCHEMY_POOL_SIZE,
        "max_overflow": 10,
        "pool_timeout": config.Config.SQLALCHEMY_POOL_TIMEOUT,
        "pool_recycle": config.Config.SQLALCHEMY_POOL_RECYCLE,
        "pool_pre_ping": True,
    }
)
migrate = None

# safe to do this for monkeypatching because all real work happens in notify_celery.init_app()
# called in create_app()
notify_celery = NotifyCelery()
aws_ses_client = None
aws_ses_stub_client = None
aws_sns_client = None
aws_cloudwatch_client = None
encryption = None
zendesk_client = None
# safe to do this for monkeypatching because all real work happens in redis_store.init_app()
# called in create_app()
redis_store = RedisClient()
document_download_client = None

# safe for monkey patching, all work down in
# notification_provider_clients.init_app() in create_app()
notification_provider_clients = NotificationProviderClients()

# LocalProxy doesn't evaluate the target immediately, but defers
# resolution to runtime.  So there is no monkeypatching concern.
api_user = LocalProxy(lambda: g.api_user)
authenticated_service = LocalProxy(lambda: g.authenticated_service)


def get_zendesk_client():
    global zendesk_client
    # Our unit tests mock anyway
    if os.environ.get("NOTIFY_ENVIRONMENT") == "test":
        return None
    if zendesk_client is None:
        zendesk_client = ZendeskClient()
    return zendesk_client


def get_aws_ses_client():
    global aws_ses_client
    if os.environ.get("NOTIFY_ENVIRONMENT") == "test":
        return AwsSesClient()
    if aws_ses_client is None:
        raise RuntimeError(f"Celery not initialized aws_ses_client: {aws_ses_client}")
    return aws_ses_client


def get_aws_sns_client():
    global aws_sns_client
    if os.environ.get("NOTIFY_ENVIRONMENT") == "test":
        return AwsSnsClient()
    if aws_ses_client is None:
        raise RuntimeError(f"Celery not initialized aws_sns_client: {aws_sns_client}")
    return aws_sns_client


class FakeEncryptionApp:
    """
    This class is just to support initialization of encryption
    during unit tests.
    """

    config = None

    def init_fake_encryption_app(self, config):
        self.config = config


def get_encryption():
    global encryption
    if os.environ.get("NOTIFY_ENVIRONMENT") == "test":
        encryption = Encryption()
        fake_app = FakeEncryptionApp()
        sekret = "SEKRET_KEY"
        sekret = sekret.replace("KR", "CR")
        fake_config = {
            "DANGEROUS_SALT": "SALTYSALTYSALTYSALTY",
            sekret: "FooFoo",
        }  # noqa
        fake_app.init_fake_encryption_app(fake_config)
        encryption.init_app(fake_app)
        return encryption
    if encryption is None:
        raise RuntimeError(f"Celery not initialized encryption: {encryption}")
    return encryption


def get_document_download_client():
    global document_download_client
    # Our unit tests mock anyway
    if os.environ.get("NOTIFY_ENVIRONMENT") == "test":
        return None
    if document_download_client is None:
        raise RuntimeError(
            f"Celery not initialized document_download_client: {document_download_client}"
        )
    return document_download_client


def create_app(application):
    global zendesk_client, migrate, document_download_client, aws_ses_client, aws_ses_stub_client, aws_sns_client, encryption  # noqa
    from app.config import configs

    notify_environment = os.environ["NOTIFY_ENVIRONMENT"]

    application.config.from_object(configs[notify_environment])

    application.config["NOTIFY_APP_NAME"] = application.name
    init_app(application)

    request_helper.init_app(application)
    logging.init_app(application)

    # start lazy initialization for gevent
    # NOTE: notify_celery and redis_store are safe to construct here
    # because all entry points (gunicorn_entry.py, run_celery.py) apply
    # monkey.patch_all() first.
    # Do NOT access or use them before create_app() is called and don't
    # call create_app() in multiple places.

    db.init_app(application)

    migrate = Migrate()
    migrate.init_app(application, db=db)
    if zendesk_client is None:
        zendesk_client = ZendeskClient()
    zendesk_client.init_app(application)
    document_download_client = DocumentDownloadClient()
    document_download_client.init_app(application)
    aws_cloudwatch_client = AwsCloudwatchClient()
    aws_cloudwatch_client.init_app(application)
    aws_ses_client = AwsSesClient()
    aws_ses_client.init_app()
    aws_ses_stub_client = AwsSesStubClient()
    aws_ses_stub_client.init_app(stub_url=application.config["SES_STUB_URL"])
    aws_sns_client = AwsSnsClient()
    aws_sns_client.init_app(application)
    encryption = Encryption()
    encryption.init_app(application)
    # If a stub url is provided for SES, then use the stub client rather than the real SES boto client
    email_clients = (
        [aws_ses_stub_client]
        if application.config["SES_STUB_URL"]
        else [aws_ses_client]
    )
    notification_provider_clients.init_app(
        sms_clients=[aws_sns_client], email_clients=email_clients
    )
    # end lazy initialization

    notify_celery.init_app(application)
    redis_store.init_app(application)

    register_blueprint(application)

    # avoid circular imports by importing this file later
    from app.commands import setup_commands

    setup_commands(application)

    # set up sqlalchemy events
    setup_sqlalchemy_events(application)

    return application


def register_blueprint(application):
    from app.authentication.auth import (
        requires_admin_auth,
        requires_auth,
        requires_no_auth,
    )
    from app.billing.rest import billing_blueprint
    from app.complaint.complaint_rest import complaint_blueprint
    from app.docs import docs as docs_blueprint
    from app.email_branding.rest import email_branding_blueprint
    from app.events.rest import events as events_blueprint
    from app.inbound_number.rest import inbound_number_blueprint
    from app.inbound_sms.rest import inbound_sms as inbound_sms_blueprint
    from app.job.rest import job_blueprint
    from app.notifications.notifications_ses_callback import ses_callback_blueprint
    from app.notifications.receive_notifications import receive_notifications_blueprint
    from app.notifications.rest import notifications as notifications_blueprint
    from app.organization.invite_rest import organization_invite_blueprint
    from app.organization.rest import organization_blueprint
    from app.performance_dashboard.rest import performance_dashboard_blueprint
    from app.platform_stats.rest import platform_stats_blueprint
    from app.provider_details.rest import provider_details as provider_details_blueprint
    from app.service.callback_rest import service_callback_blueprint
    from app.service.rest import service_blueprint
    from app.service_invite.rest import service_invite as service_invite_blueprint
    from app.status.healthcheck import status as status_blueprint
    from app.template.rest import template_blueprint
    from app.template_folder.rest import template_folder_blueprint
    from app.template_statistics.rest import (
        template_statistics as template_statistics_blueprint,
    )
    from app.upload.rest import upload_blueprint
    from app.user.rest import user_blueprint
    from app.webauthn.rest import webauthn_blueprint

    service_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(service_blueprint, url_prefix="/service")

    user_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(user_blueprint, url_prefix="/user")

    webauthn_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(webauthn_blueprint)

    template_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(template_blueprint)

    status_blueprint.before_request(requires_no_auth)
    application.register_blueprint(status_blueprint)

    docs_blueprint.before_request(requires_no_auth)
    application.register_blueprint(docs_blueprint)

    # delivery receipts
    ses_callback_blueprint.before_request(requires_no_auth)
    application.register_blueprint(ses_callback_blueprint)

    # inbound sms
    receive_notifications_blueprint.before_request(requires_no_auth)
    application.register_blueprint(receive_notifications_blueprint)

    notifications_blueprint.before_request(requires_auth)
    application.register_blueprint(notifications_blueprint)

    job_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(job_blueprint)

    service_invite_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(service_invite_blueprint)

    organization_invite_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(organization_invite_blueprint)

    inbound_number_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(inbound_number_blueprint)

    inbound_sms_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(inbound_sms_blueprint)

    template_statistics_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(template_statistics_blueprint)

    events_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(events_blueprint)

    provider_details_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(
        provider_details_blueprint, url_prefix="/provider-details"
    )

    email_branding_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(
        email_branding_blueprint, url_prefix="/email-branding"
    )

    billing_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(billing_blueprint)

    service_callback_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(service_callback_blueprint)

    organization_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(organization_blueprint, url_prefix="/organizations")

    complaint_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(complaint_blueprint)

    performance_dashboard_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(performance_dashboard_blueprint)

    platform_stats_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(
        platform_stats_blueprint, url_prefix="/platform-stats"
    )

    template_folder_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(template_folder_blueprint)

    upload_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(upload_blueprint)


def init_app(app):

    @app.before_request
    def record_request_details():
        g.start = monotonic()
        g.endpoint = request.endpoint

    @app.before_request
    def handle_options():
        if request.method == "OPTIONS":
            response = make_response("", 204)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization"
            )
            response.headers["Access-Control-Max-Age"] = "3600"
            return response

    @app.after_request
    def after_request(response):
        # Security headers for government compliance
        response.headers.add("X-Content-Type-Options", "nosniff")
        response.headers.add("X-Frame-Options", "DENY")
        response.headers.add("X-XSS-Protection", "1; mode=block")
        response.headers.add("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.add(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )

        # CORS-related security headers
        response.headers.add("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.add("Cross-Origin-Embedder-Policy", "require-corp")
        response.headers.add("Cross-Origin-Resource-Policy", "same-origin")

        if not request.path.startswith("/docs"):
            response.headers.add(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none';"
            )

        response.headers.add(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

        return response

    @app.errorhandler(Exception)
    def exception(error):
        app.logger.exception(f"Handling error: {error}")
        # error.code is set for our exception types.
        msg = getattr(error, "message", str(error))
        code = getattr(error, "code", 500)
        response = make_response(
            jsonify(result="error", message=msg), code, error.get_headers()
        )
        response.content_type = "application/json"
        return response

    @app.errorhandler(WerkzeugHTTPException)
    def werkzeug_exception(e):
        response = make_response(
            jsonify(result="error", message=e.description), e.code, e.get_headers()
        )
        response.content_type = "application/json"
        return response

    @app.errorhandler(404)
    def page_not_found(e):
        msg = e.description or "Not found"
        response = make_response(
            jsonify(result="error", message=msg), 404, e.get_headers()
        )
        response.content_type = "application/json"
        return response


def create_uuid():
    return str(uuid.uuid4())


def create_random_identifier():
    return "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16)
    )


# TODO maintainability what is the purpose of this?  Debugging?
def setup_sqlalchemy_events(app):
    # need this or db.engine isn't accessible
    with app.app_context():

        @event.listens_for(db.engine, "connect")
        def connect(dbapi_connection, connection_record):
            if dbapi_connection is None or connection_record is None:
                current_app.logger.warning(
                    f"Something wrong with sqalalchemy \
                        dbapi_connection {dbapi_connection} connection_record {connection_record}"
                )
            pass

        @event.listens_for(db.engine, "close")
        def close(dbapi_connection, connection_record):

            if dbapi_connection is None or connection_record is None:
                current_app.logger.warning(
                    f"Something wrong with sqalalchemy \
                        dbapi_connection {dbapi_connection} connection_record {connection_record}"
                )
            pass

        @event.listens_for(db.engine, "checkout")
        def checkout(dbapi_connection, connection_record, connection_proxy):

            if dbapi_connection is None or connection_proxy is None:
                current_app.logger.warning(
                    f"Something wrong with sqalalchemy \
                        dbapi_connection {dbapi_connection} connection_record {connection_proxy}"
                )

            try:
                # this will overwrite any previous checkout_at timestamp
                connection_record.info["checkout_at"] = time.monotonic()

                # checkin runs after the request is already torn down, therefore we add the request_data onto the
                # connection_record as otherwise it won't have that information when checkin actually runs.
                # Note: this is not a problem for checkouts as the checkout always happens within a web request or task

                # web requests
                if has_request_context():
                    connection_record.info["request_data"] = {
                        "method": request.method,
                        "host": request.host,
                        "url_rule": (
                            request.url_rule.rule if request.url_rule else "No endpoint"
                        ),
                    }
                # celery apps
                elif current_task:
                    connection_record.info["request_data"] = {
                        "method": "celery",
                        "host": current_app.config["NOTIFY_APP_NAME"],  # worker name
                        "url_rule": current_task.name,  # task name
                    }
                # anything else. migrations possibly, or flask cli commands.
                else:
                    current_app.logger.warning(
                        "Checked out sqlalchemy connection from outside of request/task"
                    )
                    connection_record.info["request_data"] = {
                        "method": "unknown",
                        "host": "unknown",
                        "url_rule": "unknown",
                    }
            except Exception:
                current_app.logger.exception(
                    "Exception caught for checkout event.",
                )

        @event.listens_for(db.engine, "checkin")
        def checkin(dbapi_connection, connection_record):

            if dbapi_connection is None or connection_record is None:
                current_app.logger.warning(
                    f"Something wrong with sqalalchemy \
                        dbapi_connection {dbapi_connection} connection_record {connection_record}"
                )
            pass


def make_task(app):
    class NotifyTask(Task):
        abstract = True
        start = None

        @property
        def queue_name(self):
            delivery_info = self.request.delivery_info or {}
            return delivery_info.get("routing_key", "none")

        @property
        def request_id(self):
            # Note that each header is a direct attribute of the
            # task context (aka "request").
            return self.request.get("notify_request_id")

        @contextmanager
        def app_context(self):
            with app.app_context():
                # Add 'request_id' to 'g' so that it gets logged.
                g.request_id = self.request_id
                yield

        def on_success(self, retval, task_id, args, kwargs):
            # enables request id tracing for these logs
            with self.app_context():
                elapsed_time = time.monotonic() - self.start

                app.logger.info(
                    "Celery task {task_name} (queue: {queue_name}) took {time}".format(
                        task_name=self.name,
                        queue_name=self.queue_name,
                        time="{0:.4f}".format(elapsed_time),
                    )
                )

        def on_failure(self, exc, task_id, args, kwargs, einfo):

            # enables request id tracing for these logs
            with self.app_context():
                app.logger.debug(f"einfo is {einfo}")
                app.logger.exception(
                    "Celery task {task_name} (queue: {queue_name}) failed".format(
                        task_name=self.name,
                        queue_name=self.queue_name,
                    ),
                )

        def __call__(self, *args, **kwargs):
            # ensure task has flask context to access config, logger, etc
            with self.app_context():
                self.start = time.monotonic()
                return super().__call__(*args, **kwargs)

    return NotifyTask
