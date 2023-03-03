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
from tests.conftest import Matcher

dvla_response_file_matcher = Matcher(
    'dvla_response_file',
    lambda x: 'NOTIFY-20180125140000-RSP.TXT' < x <= 'NOTIFY-20180125140030-RSP.TXT'
)


@pytest.mark.skip(reason="Re-enable when SMS receipts exist")
def test_make_sns_callback(notify_api, rmock):
    endpoint = "http://localhost:6011/notifications/sms/sns"
    rmock.request(
        "POST",
        endpoint,
        json={"status": "success"},
        status_code=200)
    send_sms_response("sns", "1234", "2028675309")

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    assert json.loads(rmock.request_history[0].text)['MSISDN'] == '2028675309'


@pytest.mark.skip(reason="Re-enable when SMS receipts exist")
def test_callback_logs_on_api_call_failure(notify_api, rmock, mocker):
    endpoint = "http://localhost:6011/notifications/sms/sns"
    rmock.request(
        "POST",
        endpoint,
        json={"error": "something went wrong"},
        status_code=500)
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.error')

    with pytest.raises(HTTPError):
        send_sms_response("mmg", "1234", "07700900001")

    assert rmock.called
    assert rmock.request_history[0].url == endpoint
    mock_logger.assert_called_once_with(
        'API POST request on http://localhost:6011/notifications/sms/mmg failed with status 500'
    )


def test_make_ses_callback(notify_api, mocker):
    mock_task = mocker.patch('app.celery.research_mode_tasks.process_ses_results')
    some_ref = str(uuid.uuid4())

    send_email_response(reference=some_ref, to="test@test.com")

    mock_task.apply_async.assert_called_once_with(ANY, queue=QueueNames.RESEARCH_MODE)
    assert mock_task.apply_async.call_args[0][0][0] == ses_notification_callback(some_ref)


@pytest.mark.skip(reason="Re-enable when SNS delivery receipts exist")
def test_delievered_sns_callback():
    phone_number = "2028675309"
    data = json.loads(sns_callback("1234", phone_number))
    assert data['MSISDN'] == phone_number
    assert data['status'] == "3"
    assert data['reference'] == "sns_reference"
    assert data['CID'] == "1234"


@pytest.mark.skip(reason="Re-enable when SNS delivery receipts exist")
def test_perm_failure_sns_callback():
    phone_number = "2028675302"
    data = json.loads(sns_callback("1234", phone_number))
    assert data['MSISDN'] == phone_number
    assert data['status'] == "5"
    assert data['reference'] == "sns_reference"
    assert data['CID'] == "1234"


@pytest.mark.skip(reason="Re-enable when SNS delivery receipts exist")
def test_temp_failure_sns_callback():
    phone_number = "2028675303"
    data = json.loads(sns_callback("1234", phone_number))
    assert data['MSISDN'] == phone_number
    assert data['status'] == "4"
    assert data['reference'] == "sns_reference"
    assert data['CID'] == "1234"
