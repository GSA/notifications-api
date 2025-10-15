import json

# import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from flask import current_app

from app.clients.cloudwatch.aws_cloudwatch import AwsCloudwatchClient


def test_check_sms_no_event_error_condition(notify_api, mocker):
    client = AwsCloudwatchClient()

    boto_mock = mocker.patch.object(client, "_client", create=True)
    # TODO
    #  we do this to get the AWS account number, and it seems like unit tests locally have
    #  access to the env variables but when we push the PR they do not.  Is there a better way to get it?
    mocker.patch.dict("os.environ", {"SES_DOMAIN_ARN": "1111:"})
    message_id = "aaa"
    notification_id = "bbb"
    boto_mock.filter_log_events.return_value = []
    with notify_api.app_context():
        client.init_app(current_app)
        try:
            client.check_sms(message_id, notification_id)
            assert 1 == 0
        except Exception:
            assert 1 == 1


def side_effect(filterPattern, logGroupName, startTime, endTime):
    if "Failure" in logGroupName and "fail" in filterPattern:
        return {
            "events": [
                {
                    "logStreamName": "89db9712-c6d1-49f9-be7c-4caa7ed9efb1",
                    "message": '{"delivery":{"destination":"+1661","phoneCarrier":"ATT Mobility", '
                    '"providerResponse":"Invalid phone number", "priceInUSD": "0.00881"}}',
                    "eventId": "37535432778099870001723210579798865345508698025292922880",
                }
            ]
        }

    elif "succeed" in filterPattern:
        return {
            "events": [
                {
                    "logStreamName": "89db9712-c6d1-49f9-be7c-4caa7ed9efb1",
                    "timestamp": 1683147017911,
                    "message": '{"delivery":{"destination":"+1661","phoneCarrier":"ATT Mobility",'
                    '"providerResponse":"Phone accepted msg", "priceInUSD": "0.00881"}}',
                    "ingestionTime": 1683147018026,
                    "eventId": "37535432778099870001723210579798865345508698025292922880",
                }
            ]
        }
    else:
        return {"events": []}


def test_extract_account_number_gov_cloud():
    domain_arn = "arn:aws-us-gov:ses:us-gov-west-1:12345:identity/ses-abc.xxx.xxx.xxx"
    client = AwsCloudwatchClient()
    client.init_app(current_app)
    actual_account_number = client._extract_account_number(domain_arn)
    assert len(actual_account_number) == 6
    expected_account_number = "12345"
    assert actual_account_number[4] == expected_account_number


def test_extract_account_number_gov_staging():
    domain_arn = "arn:aws:ses:us-south-14:12345:identity/ses-abc.xxx.xxx.xxx"
    client = AwsCloudwatchClient()
    client.init_app(current_app)
    actual_account_number = client._extract_account_number(domain_arn)
    assert len(actual_account_number) == 6
    expected_account_number = "12345"
    assert actual_account_number[4] == expected_account_number


def test_event_to_db_format_with_missing_fields():
    client = AwsCloudwatchClient()
    client.init_app(current_app)

    event = {
        "notification": {"messageId": "12345"},
        "status": "UNKNOWN",
        "delivery": {},
    }
    result = client.event_to_db_format(event)
    assert result == {
        "notification.messageId": "12345",
        "status": "UNKNOWN",
        "delivery.phoneCarrier": "",
        "delivery.providerResponse": "",
        "delivery.priceInUSD": 0.0,
        "@timestamp": "",
    }


def test_event_to_db_format_with_string_input():
    event = json.dumps(
        {
            "notification": {"messageId": "67890", "timestamp": "2024-01-01T14:00:00Z"},
            "status": "FAILED",
            "delivery": {
                "phoneCarrier": "Verizon",
                "providerResponse": "Error",
                "priceInUSD": "0.00881",
            },
        }
    )
    client = AwsCloudwatchClient()
    client.init_app(current_app)

    result = client.event_to_db_format(event)
    assert result == {
        "notification.messageId": "67890",
        "status": "FAILED",
        "delivery.phoneCarrier": "Verizon",
        "delivery.providerResponse": "Error",
        "delivery.priceInUSD": 0.00881,
        "@timestamp": "2024-01-01T14:00:00Z",
    }


@pytest.fixture
def fake_event():
    return {
        "notification": {"messageId": "abc123", "timestamp": "2025-01-01T00:00:00"},
        "status": "DELIVERED",
        "delivery": {
            "phoneCarrier": "Verizon",
            "providerResponse": "Success",
            "priceInUSD": "0.006",
        },
    }


def test_warn_if_dev_is_opted_out():
    # os.environ["NOTIFIY_ENVIRONMENT"] = "development"
    client = AwsCloudwatchClient()
    logline = client.warn_if_dev_is_opted_out("Number is opted out", "notif123")
    assert "OPTED OUT" in logline
    assert "notif123" in logline
    no_warning = client.warn_if_dev_is_opted_out("All good", "notif456")
    assert no_warning is None
    # del os.environ["NOTIFY_ENVIRONMENT"]


def test_event_to_db_format(fake_event):
    client = AwsCloudwatchClient()
    result = client.event_to_db_format(fake_event)
    assert result["notification.messageId"] == "abc123"
    assert result["status"] == "DELIVERED"
    assert result["delivery.phoneCarrier"] == "Verizon"
    assert result["delivery.providerResponse"] == "Success"
    assert result["delivery.priceInUSD"] == 0.006


def test_event_to_db_format_with_str(fake_event):
    client = AwsCloudwatchClient()
    event_str = json.dumps(fake_event)
    result = client.event_to_db_format(event_str)
    assert result["delivery.priceInUSD"] == 0.006


def test_event_to_db_Format_missing_price(fake_event):
    client = AwsCloudwatchClient()
    fake_event["delivery"]["priceInUSD"] = ""
    result = client.event_to_db_format(fake_event)
    assert result["delivery.priceInUSD"] == 0.0


def test_aws_value_or_default():
    client = AwsCloudwatchClient()
    event = {"delivery": {"foo": "bar"}}
    assert client._aws_value_or_default(event, "delivery", "foo") == "bar"
    assert client._aws_value_or_default(event, "delivery", "missing") == ""
    assert client._aws_value_or_default(event, "nonexistent", "missing") == ""


def test_extract_account_number():
    client = AwsCloudwatchClient()
    arn = "arn:aws:ses:us-north-1:123456789012:identity/example.com"
    parts = client._extract_account_number(arn)
    assert parts[4] == "123456789012"


@patch("app.clients.cloudwatch.aws_cloudwatch.client")
def test_get_log_with_pagination(mock_client):
    client = AwsCloudwatchClient()
    client.init_app(current_app)
    client._client = mock_client
    mock_client.filter_log_events.side_effect = [
        {"events": [{"message": "msg1"}], "nextToken": "abc"},
        {"events": [{"message": "msg2"}]},
    ]

    start = datetime.utcnow() - timedelta(minutes=5)
    end = datetime.utcnow()

    logs = client._get_log("log-group", start, end)
    assert len(logs) == 2
    assert logs[0]["message"] == "msg1"
    assert logs[1]["message"] == "msg2"


# @patch("app.clients.cloudwatch.aws_cloudwatch.current_app")
def test_get_receipts():
    client = AwsCloudwatchClient()
    client._get_log = MagicMock(
        return_value=[
            {
                "message": json.dumps(
                    {
                        "notification": {"messageId": "abc", "timestamp": "t"},
                        "status": "DELIVERED",
                        "delivery": {
                            "phoneCarrier": "x",
                            "providerResponse": "V",
                            "priceInUSD": "0.1",
                        },
                    }
                )
            }
        ]
    )

    result = client._get_receipts("group", datetime.utcnow(), datetime.utcnow())
    assert len(result) == 1
    event = json.loads(list(result)[0])
    assert event["status"] == "DELIVERED"


# @patch("app.clients.cloudwatch.aws_cloudwatch.current_app")
@patch("app.clients.cloudwatch.aws_cloudwatch.cloud_config")
def test_check_delivery_receipts(mock_cloud_config):
    client = AwsCloudwatchClient()
    mock_cloud_config.sns_regions = "us-north-1"
    mock_cloud_config.ses_domain_arn = (
        "arn:aws:ses:us-north-1:123456789012:identity/example.com"
    )
    client._get_receipts = MagicMock(
        side_effect=[{"delivered1", "delivered2"}, {"failed1"}]
    )

    start = datetime.utcnow() - timedelta(minutes=10)
    end = datetime.utcnow()

    delivered, failed = client.check_delivery_receipts(start, end)

    assert delivered == {"delivered1", "delivered2"}
    assert failed == {"failed1"}
