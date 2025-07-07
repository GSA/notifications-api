import base64
from io import BytesIO
from unittest.mock import Mock

import pytest

from notifications_python_client.notifications import NotificationsAPIClient


@pytest.fixture
def client():
    fake_service_id = "12345678-1234-1234-1234-123456789abc"
    fake_key_part = "abcdef12-3456-7890-abcd-ef1234567890"
    api_key = "x" + fake_service_id + fake_key_part
    client = NotificationsAPIClient(
        api_key, base_url="https://api.notifications.service.gov.fake-uk"
    )
    client.post = Mock()
    client.get = Mock()
    client._perform_request = Mock()
    client._create_request_objects = Mock(return_value=("/mock/url", {}))
    client.service_id = "test-service-id"
    return client


def test_send_sms_notification_basic(client):
    client.send_sms_notification("1234567890", "template-id")
    client.post.assert_called_once_with(
        "/v2/notifications/sms",
        data={"phone_number": "1234567890", "template_id": "template-id"},
    )


def test_send_sms_notification_full(client):
    client.send_sms_notification(
        "1234567890",
        "template-id",
        personalisation={"name": "Atlas"},
        reference="ref123",
        sms_sender_id="sender-001",
    )
    client.post.assert_called_once_with(
        "/v2/notifications/sms",
        data={
            "phone_number": "1234567890",
            "template_id": "template-id",
            "personalisation": {"name": "Atlas"},
            "reference": "ref123",
            "sms_sender_id": "sender-001",
        },
    )


def test_send_email_notification(client):
    client.send_email_notification("test@example.com", "template-id")
    client.post.assert_called_once_with(
        "/v2/notifications/email",
        data={"email_address": "test@example.com", "template_id": "template-id"},
    )


def test_send_letter_notification(client):
    client.send_letter_notification("template-id", {"name": "Bob"}, reference="ref456")
    client.post.assert_called_once_with(
        "/v2/notifications/letter",
        data={
            "template_id": "template-id",
            "personalisation": {"name": "Bob"},
            "reference": "ref456",
        },
    )


def test_send_precompiled_letter_notification(client):
    mock_pdf = BytesIO(b"PDF data")
    client.send_precompiled_letter_notification("ref789", mock_pdf, postage="first")
    expected_content = base64.b64encode(b"PDF data").decode("utf-8")
    client.post.assert_called_once_with(
        "/v2/notifications/letter",
        data={"reference": "ref789", "content": expected_content, "postage": "first"},
    )


def test_get_received_texts(client):
    client.get_received_texts()
    client.get.assert_called_once_with("/v2/received-text-messages")


def test_get_received_texts_with_param(client):
    client.get_received_texts("id123")
    client.get.assert_called_once_with("/v2/received-text-messages?older_than=id123")


def test_get_notification_by_id(client):
    client.get_notification_by_id("notif-id")
    client.get.assert_called_once_with("/v2/notifications/notif-id")


def test_get_pdf_for_letter(client):
    mock_response = Mock()
    mock_response.content = b"pdf-bytes"
    client._perform_request.return_value = mock_response
    pdf = client.get_pdf_for_letter("abc123")
    assert isinstance(pdf, BytesIO)
    assert pdf.read() == b"pdf-bytes"


def test_get_all_notifications(client):
    client.get_all_notifications(status="delivered")
    client.get.assert_called_once_with(
        "/v2/notifications", params={"status": "delivered"}
    )


def test_post_template_preview(client):
    client.post_template_preview("tmpl123", {"name": "Charlie"})
    client.post.assert_called_once_with(
        "/v2/template/tmpl123/preview", data={"personalisation": {"name": "Charlie"}}
    )


def test_get_template(client):
    client.get_template("tmpl456")
    client.get.assert_called_once_with("/v2/template/tmpl456")


def test_get_template_version(client):
    client.get_template_version("tmpl456", 2)
    client.get.assert_called_once_with("/v2/template/tmpl456/version/2")
