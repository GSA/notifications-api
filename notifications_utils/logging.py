import logging
import logging.handlers
import re
import sys
from itertools import product
from typing import Any, override

from flask import g, request
from flask.ctx import has_app_context, has_request_context
from flask.logging import default_handler
from pythonjsonlogger.jsonlogger import JsonFormatter as BaseJSONFormatter

LOG_FORMAT = (
    "%(asctime)s %(app_name)s %(name)s %(levelname)s "
    '%(request_id)s %(service_id)s "%(message)s" [in %(pathname)s:%(lineno)d]'
)
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

logger = logging.getLogger(__name__)

_phone_regex = re.compile("(?:\\+ *)?\\d[\\d\\- ]{7,}\\d")
_email_regex = re.compile(r"[\w\.-]+@[\w\.-]+")  # ['alice@google.com', 'bob@abc.com']


def _scrub(msg: Any) -> Any:
    # Sometimes just an exception object is passed in for the message, skip those.
    if not isinstance(msg, str):
        return msg
    phones = _phone_regex.findall(msg)

    phones = [phone.replace("-", "").replace(" ", "") for phone in phones]
    for phone in phones:
        msg = msg.replace(phone, "1XXXXXXXXXX")

    emails = _email_regex.findall(msg)
    for email in emails:
        # do something with each found email string
        masked_email = "XXXXX@XXXXXXX"
        msg = msg.replace(email, masked_email)
    return msg


class PIIFilter(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        record.msg = _scrub(record.msg)
        return record


class PIIFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.msg = _scrub(record.msg)
        return super().format(record)


def init_app(app):
    app.config.setdefault("NOTIFY_LOG_LEVEL", "INFO")
    app.config.setdefault("NOTIFY_APP_NAME", "none")

    app.logger.removeHandler(default_handler)

    handlers = get_handlers(app)
    loglevel = logging.getLevelName(app.config["NOTIFY_LOG_LEVEL"])
    loggers = [
        app.logger,
        logging.getLogger("utils"),
        logging.getLogger("notifications_python_client"),
        logging.getLogger("werkzeug"),
    ]
    for logger_instance, handler in product(loggers, handlers):
        logger_instance.addHandler(handler)
        logger_instance.setLevel(loglevel)
        logger_instance.propagate = False
    warning_loggers = [logging.getLogger("boto3"), logging.getLogger("s3transfer")]
    for logger_instance, handler in product(warning_loggers, handlers):
        logger_instance.addHandler(handler)
        logger_instance.setLevel(logging.WARNING)
        logger_instance.propagate = False

    # Suppress specific loggers to prevent leaking sensitive info
    logging.getLogger("boto3").setLevel(logging.ERROR)
    logging.getLogger("botocore").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)

    app.logger.info("Logging configured")


def get_handlers(app):
    handlers = []
    standard_formatter = PIIFormatter(LOG_FORMAT, TIME_FORMAT)
    json_formatter = JSONFormatter(LOG_FORMAT, TIME_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    if not app.debug:
        handlers.append(configure_handler(stream_handler, app, json_formatter))
    else:
        # turn off 200 OK static logs in development
        def is_200_static_log(log):
            msg = log.getMessage()
            return not ("GET /static/" in msg and " 200 " in msg)

        logging.getLogger("werkzeug").addFilter(is_200_static_log)

        # human readable stdout logs
        handlers.append(configure_handler(stream_handler, app, standard_formatter))

    return handlers


def configure_handler(handler, app, formatter):
    handler.setLevel(logging.getLevelName(app.config["NOTIFY_LOG_LEVEL"]))
    handler.setFormatter(formatter)
    handler.addFilter(AppNameFilter(app.config["NOTIFY_APP_NAME"]))
    handler.addFilter(RequestIdFilter())
    handler.addFilter(ServiceIdFilter())
    handler.addFilter(PIIFilter())

    return handler


class AppNameFilter(logging.Filter):
    def __init__(self, app_name):
        self.app_name = app_name

    def filter(self, record):
        record.app_name = self.app_name

        return record


class RequestIdFilter(logging.Filter):
    @property
    def request_id(self):
        default = "no-request-id"
        if has_request_context() and hasattr(request, "request_id"):
            return request.request_id or default
        elif has_app_context() and "request_id" in g:
            return g.request_id or default
        else:
            return default

    def filter(self, record):
        record.request_id = self.request_id

        return record


class ServiceIdFilter(logging.Filter):
    @property
    def service_id(self):
        default = "no-service-id"
        if has_app_context() and "service_id" in g:
            return g.service_id or default
        else:
            return default

    def filter(self, record):
        record.service_id = self.service_id

        return record


class JSONFormatter(BaseJSONFormatter):
    def process_log_record(self, log_record):
        rename_map = {
            "asctime": "time",
            "request_id": "requestId",
            "app_name": "application",
            "service_id": "service_id",
        }
        for key, newkey in rename_map.items():
            log_record[newkey] = log_record.pop(key)
        log_record["logType"] = "application"
        try:
            log_record["message"] = log_record["message"].format(**log_record)
            log_record["message"] = _scrub(log_record["message"])  # PII Scrubbing
        except KeyError as e:
            # We get occasional log messages that are nested dictionaries,
            # for example, delivery receipts, where the formatting fails
            # This is not a huge problem, don't dump stack traces into the logs
            # for it.
            logger.debug(f"failed to format log message: {e}")
        except IndexError as e:
            logger.debug(f"failed to format log message: {e}")
        return log_record
