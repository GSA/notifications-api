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
