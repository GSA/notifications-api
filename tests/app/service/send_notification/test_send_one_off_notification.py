import uuid
from unittest.mock import Mock

import pytest
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.recipients import InvalidPhoneError

from app.config import QueueNames
from app.dao.service_guest_list_dao import (
    dao_add_and_commit_guest_list_contacts,
)
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    MOBILE_TYPE,
    PRIORITY,
    SMS_TYPE,
    Notification,
    ServiceGuestList,
)
from app.service.send_notification import send_one_off_notification
from app.v2.errors import BadRequestError, TooManyRequestsError
from tests.app.db import (
    create_letter_contact,
    create_reply_to_email,
    create_service,
    create_service_sms_sender,
    create_template,
    create_user,
)


@pytest.fixture
def persist_mock(mocker):
    noti = Mock(id=uuid.uuid4())
    return mocker.patch('app.service.send_notification.persist_notification', return_value=noti)


@pytest.fixture
def celery_mock(mocker):
    return mocker.patch('app.service.send_notification.send_notification_to_queue')


def test_send_one_off_notification_calls_celery_correctly(persist_mock, celery_mock, notify_db_session):
    service = create_service()
    template = create_template(service=service)

    service = template.service

    post_data = {
        'template_id': str(template.id),
        'to': '202-867-5309',
        'created_by': str(service.created_by_id)
    }

    resp = send_one_off_notification(service.id, post_data)

    assert resp == {
        'id': str(persist_mock.return_value.id)
    }

    celery_mock.assert_called_once_with(
        notification=persist_mock.return_value,
        research_mode=False,
        queue=None
    )


def test_send_one_off_notification_calls_persist_correctly_for_sms(
    persist_mock,
    celery_mock,
    notify_db_session
):
    service = create_service()
    template = create_template(
        service=service,
        template_type=SMS_TYPE,
        content="Hello (( Name))\nYour thing is due soon",
    )

    post_data = {
        'template_id': str(template.id),
        'to': '202-867-5309',
        'personalisation': {'name': 'foo'},
        'created_by': str(service.created_by_id)
    }

    send_one_off_notification(service.id, post_data)

    persist_mock.assert_called_once_with(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data['to'],
        service=template.service,
        personalisation={'name': 'foo'},
        notification_type=SMS_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=str(service.created_by_id),
        reply_to_text='testing',
        reference=None,
        client_reference=None
    )


def test_send_one_off_notification_calls_persist_correctly_for_international_sms(
    persist_mock,
    celery_mock,
    notify_db_session
):
    service = create_service(service_permissions=['sms', 'international_sms'])
    template = create_template(
        service=service,
        template_type=SMS_TYPE,
    )

    post_data = {
        'template_id': str(template.id),
        'to': '+(44) 7700-900 855',
        'personalisation': {'name': 'foo'},
        'created_by': str(service.created_by_id)
    }

    send_one_off_notification(service.id, post_data)

    assert persist_mock.call_args[1]['recipient'] == '+(44) 7700-900 855'


def test_send_one_off_notification_calls_persist_correctly_for_email(
    persist_mock,
    celery_mock,
    notify_db_session
):
    service = create_service()
    template = create_template(
        service=service,
        template_type=EMAIL_TYPE,
        subject="Test subject",
        content="Hello (( Name))\nYour thing is due soon",
    )

    post_data = {
        'template_id': str(template.id),
        'to': 'test@example.com',
        'personalisation': {'name': 'foo'},
        'created_by': str(service.created_by_id)
    }

    send_one_off_notification(service.id, post_data)

    persist_mock.assert_called_once_with(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data['to'],
        service=template.service,
        personalisation={'name': 'foo'},
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=str(service.created_by_id),
        reply_to_text=None,
        reference=None,
        client_reference=None
    )


def test_send_one_off_notification_honors_research_mode(notify_db_session, persist_mock, celery_mock):
    service = create_service(research_mode=True)
    template = create_template(service=service)

    post_data = {
        'template_id': str(template.id),
        'to': '202-867-5309',
        'created_by': str(service.created_by_id)
    }

    send_one_off_notification(service.id, post_data)

    assert celery_mock.call_args[1]['research_mode'] is True


def test_send_one_off_notification_honors_priority(notify_db_session, persist_mock, celery_mock):
    service = create_service()
    template = create_template(service=service)
    template.process_type = PRIORITY

    post_data = {
        'template_id': str(template.id),
        'to': '202-867-5309',
        'created_by': str(service.created_by_id)
    }

    send_one_off_notification(service.id, post_data)

    assert celery_mock.call_args[1]['queue'] == QueueNames.PRIORITY


def test_send_one_off_notification_raises_if_invalid_recipient(notify_db_session):
    service = create_service()
    template = create_template(service=service)

    post_data = {
        'template_id': str(template.id),
        'to': 'not a phone number',
        'created_by': str(service.created_by_id)
    }

    with pytest.raises(InvalidPhoneError):
        send_one_off_notification(service.id, post_data)


@pytest.mark.parametrize('recipient', [
    '2028675300',  # not in team or guest_list
    '2028765309',  # in guest_list
    '+1-202-876-5309',  # in guest_list in different format
])
def test_send_one_off_notification_raises_if_cant_send_to_recipient(
    notify_db_session,
    recipient,
):
    service = create_service(restricted=True)
    template = create_template(service=service)
    dao_add_and_commit_guest_list_contacts([
        ServiceGuestList.from_string(service.id, MOBILE_TYPE, '2028765309'),
    ])

    post_data = {
        'template_id': str(template.id),
        'to': recipient,
        'created_by': str(service.created_by_id)
    }

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(service.id, post_data)

    assert 'service is in trial mode' in e.value.message


def test_send_one_off_notification_raises_if_over_limit(notify_db_session, mocker):
    service = create_service(message_limit=0)
    template = create_template(service=service)
    mocker.patch(
        'app.service.send_notification.check_service_over_daily_message_limit',
        side_effect=TooManyRequestsError(1)
    )

    post_data = {
        'template_id': str(template.id),
        'to': '07700 900 001',
        'created_by': str(service.created_by_id)
    }

    with pytest.raises(TooManyRequestsError):
        send_one_off_notification(service.id, post_data)


def test_send_one_off_notification_raises_if_message_too_long(persist_mock, notify_db_session):
    service = create_service()
    template = create_template(service=service, content="Hello (( Name))\nYour thing is due soon")

    post_data = {
        'template_id': str(template.id),
        'to': '07700 900 001',
        'personalisation': {'name': '🚫' * 1000},
        'created_by': str(service.created_by_id)
    }

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(service.id, post_data)

    assert e.value.message == f'Your message is too long. ' \
        f'Text messages cannot be longer than {SMS_CHAR_COUNT_LIMIT} characters. ' \
        f'Your message is {1029} characters long.'


def test_send_one_off_notification_fails_if_created_by_other_service(sample_template):
    user_not_in_service = create_user(email='some-other-user@gov.uk')

    post_data = {
        'template_id': str(sample_template.id),
        'to': '202-867-5309',
        'created_by': str(user_not_in_service.id)
    }

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(sample_template.service_id, post_data)

    assert e.value.message == 'Can’t create notification - Test User is not part of the "Sample service" service'


def test_send_one_off_notification_should_add_email_reply_to_text_for_notification(sample_email_template, celery_mock):
    reply_to_email = create_reply_to_email(sample_email_template.service, 'test@test.com')
    data = {
        'to': 'ok@ok.com',
        'template_id': str(sample_email_template.id),
        'sender_id': reply_to_email.id,
        'created_by': str(sample_email_template.service.created_by_id)
    }

    notification_id = send_one_off_notification(service_id=sample_email_template.service.id, post_data=data)
    notification = Notification.query.get(notification_id['id'])
    celery_mock.assert_called_once_with(
        notification=notification,
        research_mode=False,
        queue=None
    )
    assert notification.reply_to_text == reply_to_email.email_address


def test_send_one_off_letter_notification_should_use_template_reply_to_text(sample_letter_template, celery_mock):
    letter_contact = create_letter_contact(sample_letter_template.service, "Edinburgh, ED1 1AA", is_default=False)
    sample_letter_template.reply_to = str(letter_contact.id)

    data = {
        'to': 'user@example.com',
        'template_id': str(sample_letter_template.id),
        'personalisation': {
            'name': 'foo',
            'address_line_1': 'First Last',
            'address_line_2': '1 Example Street',
            'address_line_3': 'SW1A 1AA',
        },
        'created_by': str(sample_letter_template.service.created_by_id)
    }

    notification_id = send_one_off_notification(service_id=sample_letter_template.service.id, post_data=data)
    notification = Notification.query.get(notification_id['id'])
    celery_mock.assert_called_once_with(
        notification=notification,
        research_mode=False,
        queue=None
    )

    assert notification.reply_to_text == "Edinburgh, ED1 1AA"


@pytest.mark.skip(reason="Needs updating for TTS: Remove letters")
def test_send_one_off_letter_should_not_make_pdf_in_research_mode(sample_letter_template):

    sample_letter_template.service.research_mode = True

    data = {
        'to': 'A. Name',
        'template_id': str(sample_letter_template.id),
        'personalisation': {
            'name': 'foo',
            'address_line_1': 'First Last',
            'address_line_2': '1 Example Street',
            'address_line_3': 'SW1A 1AA',
        },
        'created_by': str(sample_letter_template.service.created_by_id)
    }

    notification = send_one_off_notification(service_id=sample_letter_template.service.id, post_data=data)
    notification = Notification.query.get(notification['id'])

    assert notification.status == "delivered"


def test_send_one_off_sms_notification_should_use_sms_sender_reply_to_text(sample_service, celery_mock):
    template = create_template(service=sample_service, template_type=SMS_TYPE)
    sms_sender = create_service_sms_sender(
        service=sample_service,
        sms_sender='2028675309',
        is_default=False
    )

    data = {
        'to': '2028675000',
        'template_id': str(template.id),
        'created_by': str(sample_service.created_by_id),
        'sender_id': str(sms_sender.id),
    }

    notification_id = send_one_off_notification(service_id=sample_service.id, post_data=data)
    notification = Notification.query.get(notification_id['id'])
    celery_mock.assert_called_once_with(
        notification=notification,
        research_mode=False,
        queue=None
    )

    assert notification.reply_to_text == "+12028675309"


def test_send_one_off_sms_notification_should_use_default_service_reply_to_text(sample_service, celery_mock):
    template = create_template(service=sample_service, template_type=SMS_TYPE)
    sample_service.service_sms_senders[0].is_default = False
    create_service_sms_sender(
        service=sample_service,
        sms_sender='2028675309',
        is_default=True
    )

    data = {
        'to': '2028675000',
        'template_id': str(template.id),
        'created_by': str(sample_service.created_by_id),
    }

    notification_id = send_one_off_notification(service_id=sample_service.id, post_data=data)
    notification = Notification.query.get(notification_id['id'])
    celery_mock.assert_called_once_with(
        notification=notification,
        research_mode=False,
        queue=None
    )

    assert notification.reply_to_text == "+12028675309"


def test_send_one_off_notification_should_throw_exception_if_reply_to_id_doesnot_exist(
        sample_email_template
):
    data = {
        'to': 'ok@ok.com',
        'template_id': str(sample_email_template.id),
        'sender_id': str(uuid.uuid4()),
        'created_by': str(sample_email_template.service.created_by_id)
    }

    with pytest.raises(expected_exception=BadRequestError) as e:
        send_one_off_notification(service_id=sample_email_template.service.id, post_data=data)
    assert e.value.message == 'Reply to email address not found'


def test_send_one_off_notification_should_throw_exception_if_sms_sender_id_doesnot_exist(
        sample_template
):
    data = {
        'to': '2028675000',
        'template_id': str(sample_template.id),
        'sender_id': str(uuid.uuid4()),
        'created_by': str(sample_template.service.created_by_id)
    }

    with pytest.raises(expected_exception=BadRequestError) as e:
        send_one_off_notification(service_id=sample_template.service.id, post_data=data)
    assert e.value.message == 'SMS sender not found'
