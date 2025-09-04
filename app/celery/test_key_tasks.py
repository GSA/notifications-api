import json

from flask import current_app
from requests import HTTPError, request

from app.celery.process_ses_receipts_tasks import process_ses_results
from app.config import QueueNames
from app.dao.notifications_dao import get_notification_by_id
from app.enums import NotificationType

temp_fail = "2028675303"
perm_fail = "2028675302"
delivered = "2028675309"

delivered_email = "delivered@simulator.notify"
perm_fail_email = "perm-fail@simulator.notify"
temp_fail_email = "temp-fail@simulator.notify"


def send_sms_response(provider, reference):
    body = sns_callback(reference)
    headers = {"Content-type": "application/json"}

    make_request(NotificationType.SMS, provider, body, headers)


def send_email_response(reference, to):
    if to == perm_fail_email:
        body = ses_hard_bounce_callback(reference)
    elif to == temp_fail_email:
        body = ses_soft_bounce_callback(reference)
    else:
        body = ses_notification_callback(reference)

    process_ses_results.apply_async([body], queue=QueueNames.SEND_EMAIL)


def make_request(notification_type, provider, data, headers):
    api_call = "{}/notifications/{}/{}".format(
        current_app.config["API_HOST_NAME"], notification_type, provider
    )

    try:
        response = request("POST", api_call, headers=headers, data=data, timeout=60)
        response.raise_for_status()
    except HTTPError as e:
        current_app.logger.error(
            "API POST request on {} failed with status {}".format(
                api_call, e.response.status_code
            )
        )
        raise e
    finally:
        current_app.logger.debug("Mocked provider callback request finished")
    return response.json()


def sns_callback(notification_id):
    notification = get_notification_by_id(notification_id)

    # This will only work if all notifications, including successful ones, are in the notifications table
    # If we decide to delete successful notifications, we will have to get this from notifications history
    return json.dumps(
        {
            "CID": str(notification_id),
            "status": notification.status,
            # "deliverytime": notification.completed_at
        }
    )


def ses_notification_callback(reference):
    ses_message_body = {
        "delivery": {
            "processingTimeMillis": 2003,
            "recipients": ["success@simulator.amazonses.com"],
            "remoteMtaIp": "123.123.123.123",
            "reportingMTA": "a7-32.smtp-out.us-west-2.amazonses.com",
            "smtpResponse": "250 2.6.0 Message received",
            "timestamp": "2017-11-17T12:14:03.646Z",
        },
        "mail": {
            "commonHeaders": {
                "from": ["TEST <TEST@notify.works>"],
                "subject": "lambda test",
                "to": ["success@simulator.amazonses.com"],
            },
            "destination": ["success@simulator.amazonses.com"],
            "headers": [
                {"name": "From", "value": "TEST <TEST@notify.works>"},
                {"name": "To", "value": "success@simulator.amazonses.com"},
                {"name": "Subject", "value": "lambda test"},
                {"name": "MIME-Version", "value": "1.0"},
                {
                    "name": "Content-Type",
                    "value": 'multipart/alternative; boundary="----=_Part_617203_1627511946.1510920841645"',
                },
            ],
            "headersTruncated": False,
            "messageId": reference,
            "sendingAccountId": "12341234",
            "source": '"TEST" <TEST@notify.works>',
            "sourceArn": "arn:aws:ses:us-west-2:12341234:identity/notify.works",
            "sourceIp": "0.0.0.1",
            "timestamp": "2017-11-17T12:14:01.643Z",
        },
        "notificationType": "Delivery",
    }

    return {
        "Type": "Notification",
        "MessageId": "8e83c020-1234-1234-1234-92a8ee9baa0a",
        "TopicArn": "arn:aws:sns:us-west-2:12341234:ses_notifications",
        "Subject": None,
        "Message": json.dumps(ses_message_body),
        "Timestamp": "2017-11-17T12:14:03.710Z",
        "SignatureVersion": "1",
        "Signature": "[REDACTED]",
        "SigningCertUrl": "https://sns.us-west-2.amazonaws.com/SimpleNotificationService-[REDACTED].pem",
        "UnsubscribeUrl": "https://sns.us-west-2.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=[REACTED]",
        "MessageAttributes": {},
    }


def ses_hard_bounce_callback(reference):
    return _ses_bounce_callback(reference, "Permanent")


def ses_soft_bounce_callback(reference):
    return _ses_bounce_callback(reference, "Temporary")


def _ses_bounce_callback(reference, bounce_type):
    ses_message_body = {
        "bounce": {
            "bounceSubType": "General",
            "bounceType": bounce_type,
            "bouncedRecipients": [
                {
                    "action": "failed",
                    "diagnosticCode": "smtp; 550 5.1.1 user unknown",
                    "emailAddress": "bounce@simulator.amazonses.com",
                    "status": "5.1.1",
                }
            ],
            "feedbackId": "0102015fc9e676fb-12341234-1234-1234-1234-9301e86a4fa8-000000",
            "remoteMtaIp": "123.123.123.123",
            "reportingMTA": "dsn; a7-31.smtp-out.us-west-2.amazonses.com",
            "timestamp": "2017-11-17T12:14:05.131Z",
        },
        "mail": {
            "commonHeaders": {
                "from": ["TEST <TEST@notify.works>"],
                "subject": "ses callback test",
                "to": ["bounce@simulator.amazonses.com"],
            },
            "destination": ["bounce@simulator.amazonses.com"],
            "headers": [
                {"name": "From", "value": "TEST <TEST@notify.works>"},
                {"name": "To", "value": "bounce@simulator.amazonses.com"},
                {"name": "Subject", "value": "lambda test"},
                {"name": "MIME-Version", "value": "1.0"},
                {
                    "name": "Content-Type",
                    "value": 'multipart/alternative; boundary="----=_Part_596529_2039165601.1510920843367"',
                },
            ],
            "headersTruncated": False,
            "messageId": reference,
            "sendingAccountId": "12341234",
            "source": '"TEST" <TEST@notify.works>',
            "sourceArn": "arn:aws:ses:us-west-2:12341234:identity/notify.works",
            "sourceIp": "0.0.0.1",
            "timestamp": "2017-11-17T12:14:03.000Z",
        },
        "notificationType": "Bounce",
    }
    return {
        "Type": "Notification",
        "MessageId": "36e67c28-1234-1234-1234-2ea0172aa4a7",
        "TopicArn": "arn:aws:sns:us-west-2:12341234:ses_notifications",
        "Subject": None,
        "Message": json.dumps(ses_message_body),
        "Timestamp": "2017-11-17T12:14:05.149Z",
        "SignatureVersion": "1",
        "Signature": "[REDACTED]",  # noqa
        "SigningCertUrl": "https://sns.us-west-2.amazonaws.com/SimpleNotificationService-[REDACTED]].pem",
        "UnsubscribeUrl": "https://sns.us-west-2.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=[REDACTED]]",
        "MessageAttributes": {},
    }
