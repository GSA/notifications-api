import json
import logging as builtin_logging

from notifications_utils import logging


def test_get_handlers_sets_up_logging_appropriately_with_debug():
    class App:
        config = {"NOTIFY_APP_NAME": "bar", "NOTIFY_LOG_LEVEL": "ERROR"}
        debug = True

    app = App()

    handlers = logging.get_handlers(app)

    assert len(handlers) == 1
    assert isinstance(handlers[0], builtin_logging.StreamHandler)
    assert isinstance(handlers[0].formatter, builtin_logging.Formatter)


def test_get_handlers_sets_up_logging_appropriately_without_debug():
    class App:
        config = {"NOTIFY_APP_NAME": "bar", "NOTIFY_LOG_LEVEL": "ERROR"}
        debug = False

    app = App()

    handlers = logging.get_handlers(app)

    assert len(handlers) == 1
    assert isinstance(handlers[0], builtin_logging.StreamHandler)
    assert isinstance(handlers[0].formatter, logging.JSONFormatter)


def test_base_json_formatter_contains_service_id():
    record = builtin_logging.LogRecord(
        name="log thing",
        level="info",
        pathname="path",
        lineno=123,
        msg="message to log",
        exc_info=None,
        args=None,
    )

    service_id_filter = logging.ServiceIdFilter()
    assert (
        json.loads(logging.BaseJSONFormatter().format(record))["message"]
        == "message to log"
    )
    assert service_id_filter.filter(record).service_id == "notify-admin"


def test_pii_filter():
    record = builtin_logging.LogRecord(
        name="log thing",
        level="info",
        pathname="path",
        lineno=123,
        msg="phone1: 1555555555, phone2: 1555555554, email1: fake@fake.gov, email2: fake@fake2.fake.gov",
        exc_info=None,
        args=None,
    )
    pii_filter = logging.PIIFilter()
    clean_msg = "phone1: 1XXXXXXXXXX, phone2: 1XXXXXXXXXX, email1: XXXXX@XXXXXXX, email2: XXXXX@XXXXXXX"
    assert pii_filter.filter(record).msg == clean_msg


def test_process_log_record_successful(mocker):
    mock_warning = mocker.patch("notifications_utils.logging.logger.warning")
    log_record = {
        "asctime": "2024-10-27 15:00:00",
        "request_id": "12345",
        "app_name": "test_app",
        "service_id": "service_01",
        "message": "Request 12345 received by test_app",
    }
    expected_output = {
        "time": "2024-10-27 15:00:00",
        "requestId": "12345",
        "application": "test_app",
        "service_id": "service_01",
        "message": "Request 12345 received by test_app",
        "logType": "application",
    }
    json_formatter = logging.JSONFormatter()
    result = json_formatter.process_log_record(log_record)
    assert result == expected_output
    mock_warning.assert_not_called()
