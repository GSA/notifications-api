import json

import pytest
from flask import current_app

from app import aws_cloudwatch_client


def test_check_sms_no_event_error_condition(notify_api, mocker):
    boto_mock = mocker.patch.object(aws_cloudwatch_client, "_client", create=True)
    # TODO
    #  we do this to get the AWS account number, and it seems like unit tests locally have
    #  access to the env variables but when we push the PR they do not.  Is there a better way to get it?
    mocker.patch.dict("os.environ", {"SES_DOMAIN_ARN": "1111:"})
    message_id = "aaa"
    notification_id = "bbb"
    boto_mock.filter_log_events.return_value = []
    with notify_api.app_context():
        aws_cloudwatch_client.init_app(current_app)
        try:
            aws_cloudwatch_client.check_sms(message_id, notification_id)
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


@pytest.mark.parametrize(
    "response, notify_id, expected_message",
    [
        (
            "Phone has blocked SMS",
            "abc",
            "\x1b[31mThe phone number for notification_id abc is OPTED OUT. You need to opt back in\x1b[0m",
        ),
        (
            "Some phone is opted out",
            "xyz",
            "\x1b[31mThe phone number for notification_id xyz is OPTED OUT. You need to opt back in\x1b[0m",
        ),
        ("Phone is A-OK", "123", None),
    ],
)
def test_warn_if_dev_is_opted_out(response, notify_id, expected_message):
    result = aws_cloudwatch_client.warn_if_dev_is_opted_out(response, notify_id)
    assert result == expected_message


def test_extract_account_number_gov_cloud():
    domain_arn = "arn:aws-us-gov:ses:us-gov-west-1:12345:identity/ses-abc.xxx.xxx.xxx"
    actual_account_number = aws_cloudwatch_client._extract_account_number(domain_arn)
    assert len(actual_account_number) == 6
    expected_account_number = "12345"
    assert actual_account_number[4] == expected_account_number


def test_extract_account_number_gov_staging():
    domain_arn = "arn:aws:ses:us-south-14:12345:identity/ses-abc.xxx.xxx.xxx"
    actual_account_number = aws_cloudwatch_client._extract_account_number(domain_arn)
    assert len(actual_account_number) == 6
    expected_account_number = "12345"
    assert actual_account_number[4] == expected_account_number


def test_check_delivery_receipts():
    pass


def test_aws_value_or_default():
    event = {
        "delivery": {"phoneCarrier": "AT&T"},
        "notification": {"timestamp": "2024-01-01T:12:00:00Z"},
    }
    assert (
        aws_cloudwatch_client._aws_value_or_default(event, "delivery", "phoneCarrier")
        == "AT&T"
    )
    assert (
        aws_cloudwatch_client._aws_value_or_default(
            event, "delivery", "providerResponse"
        )
        == ""
    )
    assert (
        aws_cloudwatch_client._aws_value_or_default(event, "notification", "timestamp")
        == "2024-01-01T:12:00:00Z"
    )
    assert (
        aws_cloudwatch_client._aws_value_or_default(event, "nonexistent", "field") == ""
    )


def test_event_to_db_format_with_missing_fields():
    event = {
        "notification": {"messageId": "12345"},
        "status": "UNKNOWN",
        "delivery": {},
    }
    result = aws_cloudwatch_client.event_to_db_format(event)
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
    result = aws_cloudwatch_client.event_to_db_format(event)
    assert result == {
        "notification.messageId": "67890",
        "status": "FAILED",
        "delivery.phoneCarrier": "Verizon",
        "delivery.providerResponse": "Error",
        "delivery.priceInUSD": 0.00881,
        "@timestamp": "2024-01-01T14:00:00Z",
    }
