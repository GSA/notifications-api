import json
from datetime import datetime

from app import encryption
from app.celery.process_ses_receipts_tasks import (
    process_ses_results,
    remove_emails_from_complaint,
)
from app.models import Complaint
from tests.app.db import (
    create_notification,
    create_service_callback_api,
    ses_complaint_callback,
)


def test_notifications_ses_400_with_invalid_header(client):
    data = json.dumps({"foo": "bar"})
    response = client.post(
        path='/notifications/email/ses',
        data=data,
        headers=[('Content-Type', 'application/json')]
    )
    assert response.status_code == 400


def test_notifications_ses_400_with_invalid_message_type(client):
    data = json.dumps({"foo": "bar"})
    response = client.post(
        path='/notifications/email/ses',
        data=data,
        headers=[('Content-Type', 'application/json'), ('x-amz-sns-message-type', 'foo')]
    )
    assert response.status_code == 400
    assert "SES-SNS callback failed: invalid message type" in response.get_data(as_text=True)


def test_notifications_ses_400_with_invalid_json(client):
    data = "FOOO"
    response = client.post(
        path='/notifications/email/ses',
        data=data,
        headers=[('Content-Type', 'application/json'), ('x-amz-sns-message-type', 'Notification')]
    )
    assert response.status_code == 400
    assert "SES-SNS callback failed: invalid JSON given" in response.get_data(as_text=True)


def test_notifications_ses_400_with_certificate(client):
    data = json.dumps({"foo": "bar"})
    response = client.post(
        path='/notifications/email/ses',
        data=data,
        headers=[('Content-Type', 'application/json'), ('x-amz-sns-message-type', 'Notification')]
    )
    assert response.status_code == 400
    assert "SES-SNS callback failed: validation failed" in response.get_data(as_text=True)


def test_notifications_ses_200_autoconfirms_subscription(client, mocker):
    mocker.patch("app.notifications.sns_handlers.validate_sns_cert", return_value=True)
    requests_mock = mocker.patch("requests.get")
    data = json.dumps({"Type": "SubscriptionConfirmation", "SubscribeURL": "https://foo", "Message": "foo"})
    response = client.post(
        path='/notifications/email/ses',
        data=data,
        headers=[('Content-Type', 'application/json'), ('x-amz-sns-message-type', 'SubscriptionConfirmation')]
    )

    requests_mock.assert_called_once_with("https://foo")
    assert response.status_code == 200


def test_notifications_ses_200_call_process_task(client, mocker):
    process_mock = mocker.patch("app.notifications.notifications_ses_callback.process_ses_results.apply_async")
    mocker.patch("app.notifications.sns_handlers.validate_sns_cert", return_value=True)
    data = {"Type": "Notification", "foo": "bar", "Message": {"mail": "baz"}}
    mocker.patch("app.notifications.sns_handlers.sns_notification_handler", return_value=data)
    json_data = json.dumps(data)
    response = client.post(
        path='/notifications/email/ses',
        data=json_data,
        headers=[('Content-Type', 'application/json'), ('x-amz-sns-message-type', 'Notification')]
    )

    process_mock.assert_called_once_with([{'Message': {"mail": "baz"}}], queue='notify-internal-tasks')
    assert response.status_code == 200


def test_process_ses_results_in_complaint(sample_email_template, mocker):
    notification = create_notification(template=sample_email_template, reference='ref1')
    mocked = mocker.patch("app.dao.notifications_dao.update_notification_status_by_reference")
    process_ses_results(response=ses_complaint_callback())
    assert mocked.call_count == 0
    complaints = Complaint.query.all()
    assert len(complaints) == 1
    assert complaints[0].notification_id == notification.id


def test_remove_emails_from_complaint():
    test_json = json.loads(ses_complaint_callback()['Message'])
    remove_emails_from_complaint(test_json)
    assert "recipient1@example.com" not in json.dumps(test_json)


def test_ses_callback_should_send_on_complaint_to_user_callback_api(sample_email_template, mocker):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_complaint_to_service.apply_async'
    )
    create_service_callback_api(
        service=sample_email_template.service, url="https://original_url.com", callback_type="complaint"
    )
    notification = create_notification(
        template=sample_email_template, reference='ref1', sent_at=datetime.utcnow(), status='sending'
    )
    response = ses_complaint_callback()
    assert process_ses_results(response)
    assert send_mock.call_count == 1
    assert encryption.decrypt(send_mock.call_args[0][0][0]) == {
        'complaint_date': '2018-06-05T13:59:58.000000Z',
        'complaint_id': str(Complaint.query.one().id),
        'notification_id': str(notification.id),
        'reference': None,
        'service_callback_api_bearer_token': 'some_super_secret',
        'service_callback_api_url': 'https://original_url.com',
        'to': 'recipient1@example.com'
    }
