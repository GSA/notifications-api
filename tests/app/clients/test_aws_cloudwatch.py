import pytest
from flask import current_app

from app import aws_cloudwatch_client
from app.utils import utc_now


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
                    '"providerResponse":"Invalid phone number"}}',
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
                    '"providerResponse":"Phone accepted msg"}}',
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


def test_check_sms_success(notify_api, mocker):
    aws_cloudwatch_client.init_app(current_app)
    boto_mock = mocker.patch.object(aws_cloudwatch_client, "_client", create=True)
    boto_mock.filter_log_events.side_effect = side_effect
    mocker.patch.dict(
        "os.environ",
        {"SES_DOMAIN_ARN": "arn:aws:ses:us-west-2:12345:identity/ses-xxx.xxx.xxx.xxx"},
    )

    message_id = "succeed"
    notification_id = "ccc"
    created_at = utc_now()
    with notify_api.app_context():
        aws_cloudwatch_client.check_sms(message_id, notification_id, created_at)

    # We check the 'success' log group first and if we find the message_id, we are done, so there is only 1 call
    assert boto_mock.filter_log_events.call_count == 1
    mock_call = str(boto_mock.filter_log_events.mock_calls[0])
    assert "Failure" not in mock_call
    assert "succeed" in mock_call
    assert "notification.messageId" in mock_call


def test_check_sms_failure(notify_api, mocker):
    aws_cloudwatch_client.init_app(current_app)
    boto_mock = mocker.patch.object(aws_cloudwatch_client, "_client", create=True)
    boto_mock.filter_log_events.side_effect = side_effect
    mocker.patch.dict(
        "os.environ",
        {"SES_DOMAIN_ARN": "arn:aws:ses:us-west-2:12345:identity/ses-xxx.xxx.xxx.xxx"},
    )
    message_id = "fail"
    notification_id = "bbb"
    created_at = utc_now()
    with notify_api.app_context():
        aws_cloudwatch_client.check_sms(message_id, notification_id, created_at)

    # We check the 'success' log group and find nothing, so we then check the 'fail' log group -- two calls.
    assert boto_mock.filter_log_events.call_count == 2
    mock_call = str(boto_mock.filter_log_events.mock_calls[1])
    assert "Failure" in mock_call
    assert "fail" in mock_call
    assert "notification.messageId" in mock_call


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
