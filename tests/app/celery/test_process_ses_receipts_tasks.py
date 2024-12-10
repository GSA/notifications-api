import json
from unittest.mock import ANY

import pytest
from freezegun import freeze_time

from app import encryption
from app.celery.process_ses_receipts_tasks import (
    process_ses_results,
    remove_emails_from_bounce,
    remove_emails_from_complaint,
)
from app.celery.test_key_tasks import (
    ses_hard_bounce_callback,
    ses_notification_callback,
    ses_soft_bounce_callback,
)
from app.dao.notifications_dao import get_notification_by_id
from app.enums import CallbackType, NotificationStatus
from app.models import Complaint
from app.utils import utc_now
from tests.app.conftest import create_sample_notification
from tests.app.db import (
    create_notification,
    create_service_callback_api,
    ses_complaint_callback,
)


def test_notifications_ses_400_with_invalid_header(client):
    data = json.dumps({"foo": "bar"})
    response = client.post(
        path="/notifications/email/ses",
        data=data,
        headers=[("Content-Type", "application/json")],
    )
    assert response.status_code == 400


def test_notifications_ses_400_with_invalid_message_type(client):
    data = json.dumps({"foo": "bar"})
    response = client.post(
        path="/notifications/email/ses",
        data=data,
        headers=[
            ("Content-Type", "application/json"),
            ("x-amz-sns-message-type", "foo"),
        ],
    )
    assert response.status_code == 400
    assert "SES-SNS callback failed: invalid message type" in response.get_data(
        as_text=True
    )


def test_notifications_ses_400_with_invalid_json(client):
    data = "FOOO"
    response = client.post(
        path="/notifications/email/ses",
        data=data,
        headers=[
            ("Content-Type", "application/json"),
            ("x-amz-sns-message-type", "Notification"),
        ],
    )
    assert response.status_code == 400
    assert "SES-SNS callback failed: invalid JSON given" in response.get_data(
        as_text=True
    )


def test_notifications_ses_400_with_certificate(client):
    data = json.dumps({"foo": "bar"})
    response = client.post(
        path="/notifications/email/ses",
        data=data,
        headers=[
            ("Content-Type", "application/json"),
            ("x-amz-sns-message-type", "Notification"),
        ],
    )
    assert response.status_code == 400
    assert "SES-SNS callback failed: validation failed" in response.get_data(
        as_text=True
    )


def test_notifications_ses_200_autoconfirms_subscription(client, mocker):
    mocker.patch("app.notifications.sns_handlers.validate_sns_cert", return_value=True)
    requests_mock = mocker.patch("requests.get")
    data = json.dumps(
        {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://foo",
            "Message": "foo",
        }
    )
    response = client.post(
        path="/notifications/email/ses",
        data=data,
        headers=[
            ("Content-Type", "application/json"),
            ("x-amz-sns-message-type", "SubscriptionConfirmation"),
        ],
    )

    requests_mock.assert_called_once_with("https://foo")
    assert response.status_code == 200


def test_notifications_ses_200_call_process_task(client, mocker):
    process_mock = mocker.patch(
        "app.notifications.notifications_ses_callback.process_ses_results.apply_async"
    )
    mocker.patch("app.notifications.sns_handlers.validate_sns_cert", return_value=True)
    data = {"Type": "Notification", "foo": "bar", "Message": {"mail": "baz"}}
    mocker.patch(
        "app.notifications.sns_handlers.sns_notification_handler", return_value=data
    )
    json_data = json.dumps(data)
    response = client.post(
        path="/notifications/email/ses",
        data=json_data,
        headers=[
            ("Content-Type", "application/json"),
            ("x-amz-sns-message-type", "Notification"),
        ],
    )

    process_mock.assert_called_once_with(
        [{"Message": {"mail": "baz"}}], queue="notify-internal-tasks"
    )
    assert response.status_code == 200


def test_process_ses_results(sample_email_template):
    create_notification(
        sample_email_template,
        reference="ref1",
        sent_at=utc_now(),
        status=NotificationStatus.SENDING,
    )

    assert process_ses_results(response=ses_notification_callback(reference="ref1"))


def test_process_ses_results_retry_called(sample_email_template, mocker):
    create_notification(
        sample_email_template,
        reference="ref1",
        sent_at=utc_now(),
        status=NotificationStatus.SENDING,
    )
    mocker.patch(
        "app.dao.notifications_dao._update_notification_status",
        side_effect=Exception("EXPECTED"),
    )
    mocked = mocker.patch(
        "app.celery.process_ses_receipts_tasks.process_ses_results.retry"
    )
    with pytest.raises(Exception):  # noqa: B017
        # In order to make this work, we have to suppress the flake8 warning about
        # pytest.raises(Exception), which is usually considered a bad thing.
        process_ses_results(response=ses_notification_callback(reference="ref1"))
    assert mocked.call_count != 0


def test_process_ses_results_in_complaint(sample_email_template, mocker):
    notification = create_notification(template=sample_email_template, reference="ref1")
    mocked = mocker.patch(
        "app.dao.notifications_dao.update_notification_status_by_reference"
    )
    process_ses_results(response=ses_complaint_callback())
    assert mocked.call_count == 0
    complaints = Complaint.query.all()
    assert len(complaints) == 1
    assert complaints[0].notification_id == notification.id


def test_remove_emails_from_complaint():
    test_json = json.loads(ses_complaint_callback()["Message"])
    remove_emails_from_complaint(test_json)
    assert "recipient1@example.com" not in json.dumps(test_json)


def test_remove_email_from_bounce():
    test_json = json.loads(ses_hard_bounce_callback(reference="ref1")["Message"])
    remove_emails_from_bounce(test_json)
    assert "bounce@simulator.amazonses.com" not in json.dumps(test_json)


def test_ses_callback_should_update_notification_status(
    client, _notify_db, notify_db_session, sample_email_template, mocker
):
    with freeze_time("2001-01-01T12:00:00"):
        send_mock = mocker.patch(
            "app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async"
        )
        notification = create_sample_notification(
            _notify_db,
            notify_db_session,
            template=sample_email_template,
            reference="ref",
            status=NotificationStatus.SENDING,
            sent_at=utc_now(),
        )
        create_service_callback_api(
            service=sample_email_template.service, url="https://original_url.com"
        )
        assert (
            get_notification_by_id(notification.id).status == NotificationStatus.SENDING
        )
        assert process_ses_results(ses_notification_callback(reference="ref"))
        assert (
            get_notification_by_id(notification.id).status
            == NotificationStatus.DELIVERED
        )
        send_mock.assert_called_once_with(
            [str(notification.id), ANY], queue="service-callbacks"
        )
        # assert second arg is an encrypted string
        assert isinstance(send_mock.call_args.args[0][1], str)


def test_ses_callback_should_not_update_notification_status_if_already_delivered(
    sample_email_template, mocker
):
    mock_dup = mocker.patch(
        "app.celery.process_ses_receipts_tasks.notifications_dao._duplicate_update_warning"
    )
    mock_upd = mocker.patch(
        "app.celery.process_ses_receipts_tasks.notifications_dao._update_notification_status"
    )
    notification = create_notification(
        template=sample_email_template,
        reference="ref",
        status=NotificationStatus.DELIVERED,
    )
    assert process_ses_results(ses_notification_callback(reference="ref")) is None
    assert (
        get_notification_by_id(notification.id).status == NotificationStatus.DELIVERED
    )
    mock_dup.assert_called_once_with(notification, NotificationStatus.DELIVERED)
    assert mock_upd.call_count == 0


def test_ses_callback_should_retry_if_notification_is_new(client, _notify_db, mocker):
    # mock_retry = mocker.patch(
    #     "app.celery.process_ses_receipts_tasks.process_ses_results.retry"
    # )
    mock_logger = mocker.patch(
        "app.celery.process_ses_receipts_tasks.current_app.logger.exception"
    )
    with freeze_time("2017-11-17T12:14:03.646Z"):
        try:
            assert (
                process_ses_results(ses_notification_callback(reference="ref")) is None
            )
        except Exception as e:
            import traceback
            print(type(e))
            print("*" * 80)
            print(e)
            print("-" * 80)
            print(traceback.format_exc())
            print("-" * 80)
            raise
        assert mock_logger.call_count == 0
        # assert mock_retry.call_count == 1


def test_ses_callback_should_log_if_notification_is_missing(client, _notify_db, mocker):
    mock_retry = mocker.patch(
        "app.celery.process_ses_receipts_tasks.process_ses_results.retry"
    )
    mock_logger = mocker.patch(
        "app.celery.process_ses_receipts_tasks.current_app.logger.warning"
    )
    with freeze_time("2017-11-17T12:34:03.646Z"):
        assert process_ses_results(ses_notification_callback(reference="ref")) is None
        assert mock_retry.call_count == 0
        mock_logger.assert_called_once_with(
            "Notification not found for reference: ref (while attempting update to delivered)"
        )


def test_ses_callback_should_not_retry_if_notification_is_old(mocker):
    mock_retry = mocker.patch(
        "app.celery.process_ses_receipts_tasks.process_ses_results.retry"
    )
    mock_logger = mocker.patch(
        "app.celery.process_ses_receipts_tasks.current_app.logger.error"
    )
    with freeze_time("2017-11-21T12:14:03.646Z"):
        assert process_ses_results(ses_notification_callback(reference="ref")) is None
        assert mock_logger.call_count == 0
        assert mock_retry.call_count == 0


def test_ses_callback_does_not_call_send_delivery_status_if_no_db_entry(
    client, _notify_db, notify_db_session, sample_email_template, mocker
):
    with freeze_time("2001-01-01T12:00:00"):
        send_mock = mocker.patch(
            "app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async"
        )
        notification = create_sample_notification(
            _notify_db,
            notify_db_session,
            template=sample_email_template,
            reference="ref",
            status=NotificationStatus.SENDING,
            sent_at=utc_now(),
        )
        assert (
            get_notification_by_id(notification.id).status == NotificationStatus.SENDING
        )
        assert process_ses_results(ses_notification_callback(reference="ref"))
        assert (
            get_notification_by_id(notification.id).status
            == NotificationStatus.DELIVERED
        )
        send_mock.assert_not_called()


def test_ses_callback_should_update_multiple_notification_status_sent(
    client, _notify_db, notify_db_session, sample_email_template, mocker
):
    send_mock = mocker.patch(
        "app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async"
    )
    create_sample_notification(
        _notify_db,
        notify_db_session,
        template=sample_email_template,
        reference="ref1",
        sent_at=utc_now(),
        status=NotificationStatus.SENDING,
    )
    create_sample_notification(
        _notify_db,
        notify_db_session,
        template=sample_email_template,
        reference="ref2",
        sent_at=utc_now(),
        status=NotificationStatus.SENDING,
    )
    create_sample_notification(
        _notify_db,
        notify_db_session,
        template=sample_email_template,
        reference="ref3",
        sent_at=utc_now(),
        status=NotificationStatus.SENDING,
    )
    create_service_callback_api(
        service=sample_email_template.service, url="https://original_url.com"
    )
    assert process_ses_results(ses_notification_callback(reference="ref1"))
    assert process_ses_results(ses_notification_callback(reference="ref2"))
    assert process_ses_results(ses_notification_callback(reference="ref3"))
    assert send_mock.called


def test_ses_callback_should_set_status_to_temporary_failure(
    client, _notify_db, notify_db_session, sample_email_template, mocker
):
    send_mock = mocker.patch(
        "app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async"
    )
    notification = create_sample_notification(
        _notify_db,
        notify_db_session,
        template=sample_email_template,
        reference="ref",
        status=NotificationStatus.SENDING,
        sent_at=utc_now(),
    )
    create_service_callback_api(
        service=notification.service, url="https://original_url.com"
    )
    assert get_notification_by_id(notification.id).status == NotificationStatus.SENDING
    assert process_ses_results(ses_soft_bounce_callback(reference="ref"))
    assert (
        get_notification_by_id(notification.id).status
        == NotificationStatus.TEMPORARY_FAILURE
    )
    assert send_mock.called


def test_ses_callback_should_set_status_to_permanent_failure(
    client, _notify_db, notify_db_session, sample_email_template, mocker
):
    send_mock = mocker.patch(
        "app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async"
    )
    notification = create_sample_notification(
        _notify_db,
        notify_db_session,
        template=sample_email_template,
        reference="ref",
        status=NotificationStatus.SENDING,
        sent_at=utc_now(),
    )
    create_service_callback_api(
        service=sample_email_template.service, url="https://original_url.com"
    )
    assert get_notification_by_id(notification.id).status == NotificationStatus.SENDING
    assert process_ses_results(ses_hard_bounce_callback(reference="ref"))
    assert (
        get_notification_by_id(notification.id).status
        == NotificationStatus.PERMANENT_FAILURE
    )
    assert send_mock.called


def test_ses_callback_should_send_on_complaint_to_user_callback_api(
    sample_email_template, mocker
):
    send_mock = mocker.patch(
        "app.celery.service_callback_tasks.send_complaint_to_service.apply_async"
    )
    create_service_callback_api(
        service=sample_email_template.service,
        url="https://original_url.com",
        callback_type=CallbackType.COMPLAINT,
    )
    notification = create_notification(
        template=sample_email_template,
        reference="ref1",
        sent_at=utc_now(),
        status=NotificationStatus.SENDING,
    )
    response = ses_complaint_callback()
    assert process_ses_results(response)
    assert send_mock.call_count == 1
    assert encryption.decrypt(send_mock.call_args[0][0][0]) == {
        "complaint_date": "2018-06-05T13:59:58.000000Z",
        "complaint_id": str(Complaint.query.one().id),
        "notification_id": str(notification.id),
        "reference": None,
        "service_callback_api_bearer_token": "some_super_secret",
        "service_callback_api_url": "https://original_url.com",
        "to": "recipient1@example.com",
    }
