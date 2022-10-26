import pytest

from app import statsd_client
from app.clients.sms import SmsClient, SmsClientResponseException


@pytest.fixture
def fake_client(notify_api):
    class FakeSmsClient(SmsClient):
        @property
        def name(self):
            return 'fake'

    fake_client = FakeSmsClient()
    fake_client.init_app(notify_api, statsd_client)
    return fake_client


@pytest.mark.skip(reason="Needs updating for TTS: New SMS client")
def test_send_sms(fake_client, mocker):
    mock_send = mocker.patch.object(fake_client, 'try_send_sms')

    fake_client.send_sms(
        to='to',
        content='content',
        reference='reference',
        international=False,
        sender='testing',
    )

    mock_send.assert_called_with(
        'to', 'content', 'reference', False, 'testing'
    )


@pytest.mark.skip(reason="Needs updating for TTS: New SMS client")
def test_send_sms_error(fake_client, mocker):
    mocker.patch.object(
        fake_client, 'try_send_sms', side_effect=SmsClientResponseException('error')
    )

    with pytest.raises(SmsClientResponseException):
        fake_client.send_sms(
            to='to',
            content='content',
            reference='reference',
            international=False,
            sender=None,
        )
