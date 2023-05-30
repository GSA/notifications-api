import uuid
from unittest.mock import ANY

import pytest
from flask import json

from app.celery.research_mode_tasks import (
    HTTPError,
    send_email_response,
    send_sms_response,
    ses_notification_callback,
    sns_callback,
)
from app.config import QueueNames
from app.models import NOTIFICATION_DELIVERED, NOTIFICATION_FAILED, Notification
from tests.conftest import Matcher

dvla_response_file_matcher = Matcher(
    'dvla_response_file',
    lambda x: 'NOTIFY-20180125140000-RSP.TXT' < x <= 'NOTIFY-20180125140030-RSP.TXT'
)


def test_make_sns_callback(notify_api, rmock, mocker):
    endpoint = "http://localhost:6011/notifications/sms/sns"
    get_notification_by_id = mocker.patch('app.celery.research_mode_tasks.get_notification_by_id')
    n = Notification()
    n.id = 1234
    n.status = NOTIFICATION_DELIVERED
    get_notification_by_id.return_value = n
    rmock.request(
        "POST",
        endpoint,
        json={"status": "success"},
        status_code=200)
    send_sms_response("sns", "1234")

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert json.loads(rmock.request_history[0].text)['status'] == 'delivered'


def test_callback_logs_on_api_call_failure(notify_api, rmock, mocker):
    endpoint = "http://localhost:6011/notifications/sms/sns"
    get_notification_by_id = mocker.patch('app.celery.research_mode_tasks.get_notification_by_id')
    n = Notification()
    n.id = 1234
    n.status = NOTIFICATION_FAILED
    get_notification_by_id.return_value = n

    rmock.request(
        "POST",
        endpoint,
        json={"error": "something went wrong"},
        status_code=500)
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.error')

    with pytest.raises(HTTPError):
        send_sms_response("sns", "1234")

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    mock_logger.assert_called_once_with(
        'API POST request on http://localhost:6011/notifications/sms/sns failed with status 500'
    )


def test_make_ses_callback(notify_api, mocker):
    mock_task = mocker.patch('app.celery.research_mode_tasks.process_ses_results')
    some_ref = str(uuid.uuid4())

    send_email_response(reference=some_ref, to="test@test.com")

    mock_task.apply_async.assert_called_once_with(ANY, queue=QueueNames.RESEARCH_MODE)
    assert mock_task.apply_async.call_args[0][0][0] == ses_notification_callback(some_ref)


def test_delivered_sns_callback(mocker):
    get_notification_by_id = mocker.patch('app.celery.research_mode_tasks.get_notification_by_id')
    n = Notification()
    n.id = 1234
    n.status = NOTIFICATION_DELIVERED
    get_notification_by_id.return_value = n

    data = json.loads(sns_callback("1234"))
    assert data['status'] == "delivered"
    assert data['CID'] == "1234"
