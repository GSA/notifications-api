import uuid
from unittest import mock
from unittest.mock import call

import botocore
import pytest
from flask import current_app, json

from app.dao import templates_dao
from app.dao.service_sms_sender_dao import dao_update_service_sms_sender
from app.models import (
    EMAIL_TYPE,
    INTERNATIONAL_SMS_TYPE,
    NOTIFICATION_CREATED,
    SMS_TYPE,
    Notification,
)
from app.schema_validation import validate
from app.v2.errors import RateLimitError
from app.v2.notifications.notification_schemas import (
    post_email_response,
    post_sms_response,
)
from tests import create_service_authorization_header
from tests.app.db import (
    create_api_key,
    create_reply_to_email,
    create_service,
    create_service_sms_sender,
    create_service_with_inbound_number,
    create_template,
)
from tests.conftest import set_config_values


@pytest.mark.parametrize("reference", [None, "reference_from_client"])
def test_post_sms_notification_returns_201(client, sample_template_with_placeholders, mocker, reference):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template_with_placeholders.id),
        'personalisation': {' Name': 'Jo'}
    }
    if reference:
        data.update({"reference": reference})
    auth_header = create_service_authorization_header(service_id=sample_template_with_placeholders.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].status == NOTIFICATION_CREATED
    notification_id = notifications[0].id
    assert notifications[0].postage is None
    assert notifications[0].document_download_count is None
    assert resp_json['id'] == str(notification_id)
    assert resp_json['reference'] == reference
    assert resp_json['content']['body'] == sample_template_with_placeholders.content.replace("(( Name))", "Jo")
    assert resp_json['content']['from_number'] == current_app.config['FROM_NUMBER']
    assert 'v2/notifications/{}'.format(notification_id) in resp_json['uri']
    assert resp_json['template']['id'] == str(sample_template_with_placeholders.id)
    assert resp_json['template']['version'] == sample_template_with_placeholders.version
    assert 'services/{}/templates/{}'.format(sample_template_with_placeholders.service_id,
                                             sample_template_with_placeholders.id) \
           in resp_json['template']['uri']
    assert not resp_json["scheduled_for"]
    assert mocked.called


def test_post_sms_notification_uses_inbound_number_as_sender(client, notify_db_session, mocker):
    service = create_service_with_inbound_number(inbound_number='1')

    template = create_template(service=service, content="Hello (( Name))\nYour thing is due soon")
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(template.id),
        'personalisation': {' Name': 'Jo'}
    }
    auth_header = create_service_authorization_header(service_id=service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    notifications = Notification.query.all()
    assert len(notifications) == 1
    notification_id = notifications[0].id
    assert resp_json['id'] == str(notification_id)
    assert resp_json['content']['from_number'] == '1'
    assert notifications[0].reply_to_text == '1'
    mocked.assert_called_once_with([str(notification_id)], queue='send-sms-tasks')


def test_post_sms_notification_uses_inbound_number_reply_to_as_sender(client, notify_db_session, mocker):
    service = create_service_with_inbound_number(inbound_number='07123123123')

    template = create_template(service=service, content="Hello (( Name))\nYour thing is due soon")
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(template.id),
        'personalisation': {' Name': 'Jo'}
    }
    auth_header = create_service_authorization_header(service_id=service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    notifications = Notification.query.all()
    assert len(notifications) == 1
    notification_id = notifications[0].id
    assert resp_json['id'] == str(notification_id)
    assert resp_json['content']['from_number'] == '447123123123'
    assert notifications[0].reply_to_text == '447123123123'
    mocked.assert_called_once_with([str(notification_id)], queue='send-sms-tasks')


def test_post_sms_notification_returns_201_with_sms_sender_id(
        client, sample_template_with_placeholders, mocker
):
    sms_sender = create_service_sms_sender(service=sample_template_with_placeholders.service, sms_sender='123456')
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template_with_placeholders.id),
        'personalisation': {' Name': 'Jo'},
        'sms_sender_id': str(sms_sender.id)
    }
    auth_header = create_service_authorization_header(service_id=sample_template_with_placeholders.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    assert resp_json['content']['from_number'] == sms_sender.sms_sender
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == sms_sender.sms_sender
    mocked.assert_called_once_with([resp_json['id']], queue='send-sms-tasks')


def test_post_sms_notification_uses_sms_sender_id_reply_to(
        client, sample_template_with_placeholders, mocker
):
    sms_sender = create_service_sms_sender(service=sample_template_with_placeholders.service, sms_sender='07123123123')
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template_with_placeholders.id),
        'personalisation': {' Name': 'Jo'},
        'sms_sender_id': str(sms_sender.id)
    }
    auth_header = create_service_authorization_header(service_id=sample_template_with_placeholders.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    assert resp_json['content']['from_number'] == '447123123123'
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == '447123123123'
    mocked.assert_called_once_with([resp_json['id']], queue='send-sms-tasks')


def test_notification_reply_to_text_is_original_value_if_sender_is_changed_after_post_notification(
        client, sample_template, mocker
):
    sms_sender = create_service_sms_sender(service=sample_template.service, sms_sender='123456', is_default=False)
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template.id),
        'sms_sender_id': str(sms_sender.id)
    }
    auth_header = create_service_authorization_header(service_id=sample_template.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    dao_update_service_sms_sender(service_id=sample_template.service_id,
                                  service_sms_sender_id=sms_sender.id,
                                  is_default=sms_sender.is_default,
                                  sms_sender='updated')

    assert response.status_code == 201
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == '123456'


def test_should_cache_template_lookups_in_memory(mocker, client, sample_template):

    mock_get_template = mocker.patch(
        'app.dao.templates_dao.dao_get_template_by_id_and_service_id',
        wraps=templates_dao.dao_get_template_by_id_and_service_id,
    )
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template.id),
    }

    for _ in range(5):
        auth_header = create_service_authorization_header(service_id=sample_template.service_id)
        client.post(
            path='/v2/notifications/sms',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), auth_header]
        )

    assert mock_get_template.call_count == 1
    assert mock_get_template.call_args_list == [
        call(service_id=str(sample_template.service_id), template_id=str(sample_template.id), version=None)
    ]
    assert Notification.query.count() == 5


@pytest.mark.skip(reason="Needs updating for TTS: cloud.gov redis fails, local docker works, mock redis fails")
def test_should_cache_template_and_service_in_redis(mocker, client, sample_template):

    from app.schemas import service_schema, template_schema

    mock_redis_get = mocker.patch(
        'app.redis_store.get',
        return_value=None,
    )
    mock_redis_set = mocker.patch(
        'app.redis_store.set',
    )

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template.id),
    }

    auth_header = create_service_authorization_header(service_id=sample_template.service_id)
    client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    expected_service_key = f'service-{sample_template.service_id}'
    expected_templates_key = f'service-{sample_template.service_id}-template-{sample_template.id}-version-None'

    assert mock_redis_get.call_args_list == [
        call(expected_service_key),
        call(expected_templates_key),
    ]

    service_dict = service_schema.dump(sample_template.service)
    template_dict = template_schema.dump(sample_template)

    assert len(mock_redis_set.call_args_list) == 2

    service_call, templates_call = mock_redis_set.call_args_list

    assert service_call[0][0] == expected_service_key
    assert json.loads(service_call[0][1]) == {'data': service_dict}
    assert service_call[1]['ex'] == 604_800

    assert templates_call[0][0] == expected_templates_key
    assert json.loads(templates_call[0][1]) == {'data': template_dict}
    assert templates_call[1]['ex'] == 604_800


@pytest.mark.skip(reason="Needs updating for TTS: cloud.gov redis fails, local docker works, mock redis fails")
def test_should_return_template_if_found_in_redis(mocker, client, sample_template):

    from app.schemas import service_schema, template_schema
    service_dict = service_schema.dump(sample_template.service)
    template_dict = template_schema.dump(sample_template)

    mocker.patch(
        'app.redis_store.get',
        side_effect=[
            json.dumps({'data': service_dict}).encode('utf-8'),
            json.dumps({'data': template_dict}).encode('utf-8'),
        ],
    )
    mock_get_template = mocker.patch(
        'app.dao.templates_dao.dao_get_template_by_id_and_service_id'
    )
    mock_get_service = mocker.patch(
        'app.dao.services_dao.dao_fetch_service_by_id'
    )

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template.id),
    }

    auth_header = create_service_authorization_header(service_id=sample_template.service_id)
    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    assert response.status_code == 201
    assert mock_get_template.called is False
    assert mock_get_service.called is False


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "+447700900855"),
                          ("email", "email_address", "sample@email.com")])
def test_post_notification_returns_400_and_missing_template(client, sample_service,
                                                            notification_type, key_send_to, send_to):
    data = {
        key_send_to: send_to,
        'template_id': str(uuid.uuid4())
    }
    auth_header = create_service_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [{"error": "BadRequestError",
                                     "message": 'Template not found'}]


@pytest.mark.parametrize("notification_type, key_send_to, send_to", [
    ("sms", "phone_number", "+447700900855"),
    ("email", "email_address", "sample@email.com"),
    ("letter", "personalisation", {"address_line_1": "The queen", "postcode": "SW1 1AA"})
])
def test_post_notification_returns_401_and_well_formed_auth_error(client, sample_template,
                                                                  notification_type, key_send_to, send_to):
    data = {
        key_send_to: send_to,
        'template_id': str(sample_template.id)
    }

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json')])

    assert response.status_code == 401
    assert response.headers['Content-type'] == 'application/json'
    error_resp = json.loads(response.get_data(as_text=True))
    assert error_resp['status_code'] == 401
    assert error_resp['errors'] == [{'error': "AuthError",
                                     'message': 'Unauthorized: authentication token must be provided'}]


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "+447700900855"),
                          ("email", "email_address", "sample@email.com")])
def test_notification_returns_400_and_for_schema_problems(client, sample_template, notification_type, key_send_to,
                                                          send_to):
    data = {
        key_send_to: send_to,
        'template': str(sample_template.id)
    }
    auth_header = create_service_authorization_header(service_id=sample_template.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'
    error_resp = json.loads(response.get_data(as_text=True))
    assert error_resp['status_code'] == 400
    assert {'error': 'ValidationError',
            'message': "template_id is a required property"
            } in error_resp['errors']
    assert {'error': 'ValidationError',
            'message':
            'Additional properties are not allowed (template was unexpected)'
            } in error_resp['errors']


@pytest.mark.parametrize("reference", [None, "reference_from_client"])
def test_post_email_notification_returns_201(client, sample_email_template_with_placeholders, mocker, reference):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "email_address": sample_email_template_with_placeholders.service.users[0].email_address,
        "template_id": sample_email_template_with_placeholders.id,
        "personalisation": {"name": "Bob"}
    }
    if reference:
        data.update({"reference": reference})
    auth_header = create_service_authorization_header(service_id=sample_email_template_with_placeholders.service_id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_email_response) == resp_json
    notification = Notification.query.one()
    assert notification.status == NOTIFICATION_CREATED
    assert notification.postage is None
    assert resp_json['id'] == str(notification.id)
    assert resp_json['reference'] == reference
    assert notification.reference is None
    assert notification.reply_to_text is None
    assert notification.document_download_count is None
    assert resp_json['content']['body'] == sample_email_template_with_placeholders.content \
        .replace('((name))', 'Bob')
    assert resp_json['content']['subject'] == sample_email_template_with_placeholders.subject \
        .replace('((name))', 'Bob')
    assert resp_json['content']['from_email'] == "{}@{}".format(
        sample_email_template_with_placeholders.service.email_from, current_app.config['NOTIFY_EMAIL_DOMAIN'])
    assert 'v2/notifications/{}'.format(notification.id) in resp_json['uri']
    assert resp_json['template']['id'] == str(sample_email_template_with_placeholders.id)
    assert resp_json['template']['version'] == sample_email_template_with_placeholders.version
    assert 'services/{}/templates/{}'.format(str(sample_email_template_with_placeholders.service_id),
                                             str(sample_email_template_with_placeholders.id)) \
           in resp_json['template']['uri']
    assert not resp_json["scheduled_for"]
    assert mocked.called


@pytest.mark.parametrize('recipient, notification_type', [
    ('simulate-delivered@notifications.service.gov.uk', EMAIL_TYPE),
    ('simulate-delivered-2@notifications.service.gov.uk', EMAIL_TYPE),
    ('simulate-delivered-3@notifications.service.gov.uk', EMAIL_TYPE),
    ('07700 900000', 'sms'),
    ('07700 900111', 'sms'),
    ('07700 900222', 'sms')
])
def test_should_not_persist_or_send_notification_if_simulated_recipient(
        client,
        recipient,
        notification_type,
        sample_email_template,
        sample_template,
        mocker):
    apply_async = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))

    if notification_type == 'sms':
        data = {
            'phone_number': recipient,
            'template_id': str(sample_template.id)
        }
    else:
        data = {
            'email_address': recipient,
            'template_id': str(sample_email_template.id)
        }

    auth_header = create_service_authorization_header(service_id=sample_email_template.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201
    apply_async.assert_not_called()
    assert json.loads(response.get_data(as_text=True))["id"]
    assert Notification.query.count() == 0


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "07700 900 855"),
                          ("email", "email_address", "sample@email.com")])
def test_send_notification_uses_priority_queue_when_template_is_marked_as_priority(
    client,
    sample_service,
    mocker,
    notification_type,
    key_send_to,
    send_to
):
    mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))

    sample = create_template(
        service=sample_service,
        template_type=notification_type,
        process_type='priority'
    )
    mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))

    data = {
        key_send_to: send_to,
        'template_id': str(sample.id)
    }

    auth_header = create_service_authorization_header(service_id=sample.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    notification_id = json.loads(response.data)['id']

    assert response.status_code == 201
    mocked.assert_called_once_with([notification_id], queue='priority-tasks')


@pytest.mark.parametrize(
    "notification_type, key_send_to, send_to",
    [("sms", "phone_number", "07700 900 855"), ("email", "email_address", "sample@email.com")]
)
def test_returns_a_429_limit_exceeded_if_rate_limit_exceeded(
        client,
        sample_service,
        mocker,
        notification_type,
        key_send_to,
        send_to
):
    sample = create_template(service=sample_service, template_type=notification_type)
    persist_mock = mocker.patch('app.v2.notifications.post_notifications.persist_notification')
    deliver_mock = mocker.patch('app.v2.notifications.post_notifications.send_notification_to_queue_detached')
    mocker.patch(
        'app.v2.notifications.post_notifications.check_rate_limiting',
        side_effect=RateLimitError("LIMIT", "INTERVAL", "TYPE"))

    data = {
        key_send_to: send_to,
        'template_id': str(sample.id)
    }

    auth_header = create_service_authorization_header(service_id=sample.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    error = json.loads(response.data)['errors'][0]['error']
    message = json.loads(response.data)['errors'][0]['message']
    status_code = json.loads(response.data)['status_code']
    assert response.status_code == 429
    assert error == 'RateLimitError'
    assert message == 'Exceeded rate limit for key type TYPE of LIMIT requests per INTERVAL seconds'
    assert status_code == 429

    assert not persist_mock.called
    assert not deliver_mock.called


def test_post_sms_notification_returns_400_if_not_allowed_to_send_int_sms(
        client,
        notify_db_session,
):
    service = create_service(service_permissions=[SMS_TYPE])
    template = create_template(service=service)

    data = {
        'phone_number': '20-12-1234-1234',
        'template_id': template.id
    }
    auth_header = create_service_authorization_header(service_id=service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {"error": "BadRequestError", "message": 'Cannot send to international mobile numbers'}
    ]


def test_post_sms_notification_with_archived_reply_to_id_returns_400(client, sample_template, mocker):
    archived_sender = create_service_sms_sender(
        sample_template.service,
        '12345',
        is_default=False,
        archived=True)
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "phone_number": '+447700900855',
        "template_id": sample_template.id,
        'sms_sender_id': archived_sender.id
    }
    auth_header = create_service_authorization_header(service_id=sample_template.service_id)
    response = client.post(
        path="v2/notifications/sms",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
    resp_json = json.loads(response.get_data(as_text=True))
    assert 'sms_sender_id {} does not exist in database for service id {}'. \
        format(archived_sender.id, sample_template.service_id) in resp_json['errors'][0]['message']
    assert 'BadRequestError' in resp_json['errors'][0]['error']


@pytest.mark.parametrize('recipient,label,permission_type, notification_type,expected_error', [
    ('07700 900000', 'phone_number', 'email', 'sms', 'text messages'),
    ('someone@test.com', 'email_address', 'sms', 'email', 'emails')])
def test_post_sms_notification_returns_400_if_not_allowed_to_send_notification(
        notify_db_session, client, recipient, label, permission_type, notification_type, expected_error
):
    service = create_service(service_permissions=[permission_type])
    sample_template_without_permission = create_template(service=service, template_type=notification_type)
    data = {
        label: recipient,
        'template_id': sample_template_without_permission.id
    }
    auth_header = create_service_authorization_header(service_id=sample_template_without_permission.service.id)

    response = client.post(
        path='/v2/notifications/{}'.format(sample_template_without_permission.template_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {"error": "BadRequestError", "message": "Service is not allowed to send {}".format(expected_error)}
    ]


@pytest.mark.parametrize('restricted', [True, False])
def test_post_sms_notification_returns_400_if_number_not_in_guest_list(
        notify_db_session, client, restricted
):
    service = create_service(restricted=restricted, service_permissions=[SMS_TYPE, INTERNATIONAL_SMS_TYPE])
    template = create_template(service=service)
    create_api_key(service=service, key_type='team')

    data = {
        "phone_number": '+327700900855',
        "template_id": template.id,
    }
    auth_header = create_service_authorization_header(service_id=service.id, key_type='team')

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {"error": "BadRequestError", "message": 'Can’t send to this recipient using a team-only API key'}
    ]


def test_post_sms_notification_returns_201_if_allowed_to_send_int_sms(
        sample_service,
        sample_template,
        client,
        mocker,
):
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'phone_number': '20-12-1234-1234',
        'template_id': sample_template.id
    }
    auth_header = create_service_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201
    assert response.headers['Content-type'] == 'application/json'


def test_post_sms_should_persist_supplied_sms_number(client, sample_template_with_placeholders, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+(44) 77009-00855',
        'template_id': str(sample_template_with_placeholders.id),
        'personalisation': {' Name': 'Jo'}
    }

    auth_header = create_service_authorization_header(service_id=sample_template_with_placeholders.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    notifications = Notification.query.all()
    assert len(notifications) == 1
    notification_id = notifications[0].id
    assert '+(44) 77009-00855' == notifications[0].to
    assert resp_json['id'] == str(notification_id)
    assert mocked.called


def test_post_notification_raises_bad_request_if_not_valid_notification_type(client, sample_service):
    auth_header = create_service_authorization_header(service_id=sample_service.id)
    response = client.post(
        '/v2/notifications/foo',
        data='{}',
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    assert response.status_code == 404
    error_json = json.loads(response.get_data(as_text=True))
    assert 'The requested URL was not found on the server.' in error_json['message']


@pytest.mark.parametrize("notification_type",
                         ['sms', 'email'])
def test_post_notification_with_wrong_type_of_sender(
        client,
        sample_template,
        sample_email_template,
        notification_type,
        fake_uuid):
    if notification_type == EMAIL_TYPE:
        template = sample_email_template
        form_label = 'sms_sender_id'
        data = {
            'email_address': 'test@test.com',
            'template_id': str(sample_email_template.id),
            form_label: fake_uuid
        }
    elif notification_type == SMS_TYPE:
        template = sample_template
        form_label = 'email_reply_to_id'
        data = {
            'phone_number': '+447700900855',
            'template_id': str(template.id),
            form_label: fake_uuid
        }
    auth_header = create_service_authorization_header(service_id=template.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
    resp_json = json.loads(response.get_data(as_text=True))
    assert 'Additional properties are not allowed ({} was unexpected)'.format(form_label) \
           in resp_json['errors'][0]['message']
    assert 'ValidationError' in resp_json['errors'][0]['error']


def test_post_email_notification_with_valid_reply_to_id_returns_201(client, sample_email_template, mocker):
    reply_to_email = create_reply_to_email(sample_email_template.service, 'test@test.com')
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "email_address": sample_email_template.service.users[0].email_address,
        "template_id": sample_email_template.id,
        'email_reply_to_id': reply_to_email.id
    }
    auth_header = create_service_authorization_header(service_id=sample_email_template.service_id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_email_response) == resp_json
    notification = Notification.query.first()
    assert notification.reply_to_text == 'test@test.com'
    assert resp_json['id'] == str(notification.id)
    assert mocked.called

    assert notification.reply_to_text == reply_to_email.email_address


def test_post_email_notification_with_invalid_reply_to_id_returns_400(client, sample_email_template, mocker, fake_uuid):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "email_address": sample_email_template.service.users[0].email_address,
        "template_id": sample_email_template.id,
        'email_reply_to_id': fake_uuid
    }
    auth_header = create_service_authorization_header(service_id=sample_email_template.service_id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
    resp_json = json.loads(response.get_data(as_text=True))
    assert 'email_reply_to_id {} does not exist in database for service id {}'. \
        format(fake_uuid, sample_email_template.service_id) in resp_json['errors'][0]['message']
    assert 'BadRequestError' in resp_json['errors'][0]['error']


def test_post_email_notification_with_archived_reply_to_id_returns_400(client, sample_email_template, mocker):
    archived_reply_to = create_reply_to_email(
        sample_email_template.service,
        'reply_to@test.com',
        is_default=False,
        archived=True)
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "email_address": 'test@test.com',
        "template_id": sample_email_template.id,
        'email_reply_to_id': archived_reply_to.id
    }
    auth_header = create_service_authorization_header(service_id=sample_email_template.service_id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
    resp_json = json.loads(response.get_data(as_text=True))
    assert 'email_reply_to_id {} does not exist in database for service id {}'. \
        format(archived_reply_to.id, sample_email_template.service_id) in resp_json['errors'][0]['message']
    assert 'BadRequestError' in resp_json['errors'][0]['error']


@pytest.mark.parametrize(
    'csv_param',
    (
        {'is_csv': None},
        {'is_csv': False},
        {'is_csv': True},
        {},
    )
)
def test_post_notification_with_document_upload(client, notify_db_session, mocker, csv_param):
    service = create_service(service_permissions=[EMAIL_TYPE])
    service.contact_link = 'contact.me@gov.uk'
    template = create_template(
        service=service,
        template_type='email',
        content="Document 1: ((first_link)). Document 2: ((second_link))"
    )

    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    document_download_mock = mocker.patch('app.v2.notifications.post_notifications.document_download_client')
    document_download_mock.upload_document.side_effect = lambda service_id, content, is_csv: f'{content}-link'

    data = {
        "email_address": service.users[0].email_address,
        "template_id": template.id,
        "personalisation": {
            "first_link": {"file": "abababab", **csv_param},
            "second_link": {"file": "cdcdcdcd", **csv_param}
        }
    }

    auth_header = create_service_authorization_header(service_id=service.id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201, response.get_data(as_text=True)
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_email_response) == resp_json

    assert document_download_mock.upload_document.call_args_list == [
        call(str(service.id), 'abababab', csv_param.get('is_csv')),
        call(str(service.id), 'cdcdcdcd', csv_param.get('is_csv'))
    ]

    notification = Notification.query.one()
    assert notification.status == NOTIFICATION_CREATED
    assert notification.personalisation == {
        'first_link': 'abababab-link',
        'second_link': 'cdcdcdcd-link'
    }
    assert notification.document_download_count == 2

    assert resp_json['content']['body'] == 'Document 1: abababab-link. Document 2: cdcdcdcd-link'


def test_post_notification_with_document_upload_simulated(client, notify_db_session, mocker):
    service = create_service(service_permissions=[EMAIL_TYPE])
    service.contact_link = 'contact.me@gov.uk'
    template = create_template(
        service=service,
        template_type='email',
        content="Document: ((document))"
    )

    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    document_download_mock = mocker.patch('app.v2.notifications.post_notifications.document_download_client')
    document_download_mock.get_upload_url.return_value = 'https://document-url'

    data = {
        "email_address": 'simulate-delivered@notifications.service.gov.uk',
        "template_id": template.id,
        "personalisation": {"document": {"file": "abababab"}}
    }

    auth_header = create_service_authorization_header(service_id=service.id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201, response.get_data(as_text=True)
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_email_response) == resp_json

    assert resp_json['content']['body'] == 'Document: https://document-url/test-document'


def test_post_notification_without_document_upload_permission(client, notify_db_session, mocker):
    service = create_service(service_permissions=[EMAIL_TYPE])
    template = create_template(
        service=service,
        template_type='email',
        content="Document: ((document))"
    )

    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    document_download_mock = mocker.patch('app.v2.notifications.post_notifications.document_download_client')
    document_download_mock.upload_document.return_value = 'https://document-url/'

    data = {
        "email_address": service.users[0].email_address,
        "template_id": template.id,
        "personalisation": {"document": {"file": "abababab"}}
    }

    auth_header = create_service_authorization_header(service_id=service.id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400, response.get_data(as_text=True)


def test_post_notification_returns_400_when_get_json_throws_exception(client, sample_email_template):
    auth_header = create_service_authorization_header(service_id=sample_email_template.service_id)
    response = client.post(
        path="v2/notifications/email",
        data="[",
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400


@pytest.mark.parametrize('notification_type, content_type',
                         [('email', 'application/json'),
                          ('email', 'application/text'),
                          ('sms', 'application/json'),
                          ('sms', 'application/text')]
                         )
def test_post_notification_when_payload_is_invalid_json_returns_400(
        client, sample_service, notification_type, content_type):
    auth_header = create_service_authorization_header(service_id=sample_service.id)
    payload_not_json = {
        "template_id": "dont-convert-to-json",
    }
    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=payload_not_json,
        headers=[('Content-Type', content_type), auth_header],
    )

    assert response.status_code == 400
    error_msg = json.loads(response.get_data(as_text=True))["errors"][0]["message"]

    assert error_msg == 'Invalid JSON supplied in POST data'


@pytest.mark.parametrize('notification_type', ['email', 'sms'])
def test_post_notification_returns_201_when_content_type_is_missing_but_payload_is_valid_json(
        client, sample_service, notification_type, mocker):
    template = create_template(service=sample_service, template_type=notification_type)
    mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))
    auth_header = create_service_authorization_header(service_id=sample_service.id)

    valid_json = {
        "template_id": str(template.id),
    }
    if notification_type == 'email':
        valid_json.update({"email_address": sample_service.users[0].email_address})
    else:
        valid_json.update({"phone_number": "+447700900855"})
    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(valid_json),
        headers=[auth_header],
    )
    assert response.status_code == 201


@pytest.mark.parametrize('notification_type', ['email', 'sms'])
def test_post_email_notification_when_data_is_empty_returns_400(client, sample_service, notification_type):
    auth_header = create_service_authorization_header(service_id=sample_service.id)
    data = None
    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header],
    )
    error_msg = json.loads(response.get_data(as_text=True))["errors"][0]["message"]
    assert response.status_code == 400
    if notification_type == 'sms':
        assert error_msg == 'phone_number is a required property'
    else:
        assert error_msg == 'email_address is a required property'


@pytest.mark.parametrize("notification_type", ("email", "sms"))
def test_post_notifications_saves_email_or_sms_to_queue(client, notify_db_session, mocker, notification_type):
    save_task = mocker.patch(f"app.celery.tasks.save_api_{notification_type}.apply_async")
    mock_send_task = mocker.patch(f'app.celery.provider_tasks.deliver_{notification_type}.apply_async')

    service = create_service(
        service_name='high volume service',
    )
    with set_config_values(current_app, {
        'HIGH_VOLUME_SERVICE': [str(service.id)],

    }):
        template = create_template(service=service, content='((message))', template_type=notification_type)
        data = {
            "template_id": template.id,
            "personalisation": {"message": "Dear citizen, have a nice day"}
        }
        data.update({"email_address": "joe.citizen@example.com"}) if notification_type == EMAIL_TYPE \
            else data.update({"phone_number": "+447700900855"})

        response = client.post(
            path=f'/v2/notifications/{notification_type}',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), create_service_authorization_header(service_id=service.id)]
        )

        json_resp = response.get_json()

        assert response.status_code == 201
        assert json_resp['id']
        assert json_resp['content']['body'] == "Dear citizen, have a nice day"
        assert json_resp['template']['id'] == str(template.id)
        save_task.assert_called_once_with([mock.ANY], queue=f'save-api-{notification_type}-tasks')
        assert not mock_send_task.called
        assert len(Notification.query.all()) == 0


@pytest.mark.parametrize("exception", [
    botocore.exceptions.ClientError({'some': 'json'}, 'some opname'),
    botocore.parsers.ResponseParserError('exceeded max HTTP body length'),
])
@pytest.mark.parametrize("notification_type", ("email", "sms"))
def test_post_notifications_saves_email_or_sms_normally_if_saving_to_queue_fails(
    client,
    notify_db_session,
    mocker,
    notification_type,
    exception
):
    save_task = mocker.patch(
        f"app.celery.tasks.save_api_{notification_type}.apply_async",
        side_effect=exception,
    )
    mock_send_task = mocker.patch(f'app.celery.provider_tasks.deliver_{notification_type}.apply_async')

    service = create_service(
        service_name='high volume service',
    )
    with set_config_values(current_app, {
        'HIGH_VOLUME_SERVICE': [str(service.id)],

    }):
        template = create_template(service=service, content='((message))', template_type=notification_type)
        data = {
            "template_id": template.id,
            "personalisation": {"message": "Dear citizen, have a nice day"}
        }
        data.update({"email_address": "joe.citizen@example.com"}) if notification_type == EMAIL_TYPE \
            else data.update({"phone_number": "+447700900855"})

        response = client.post(
            path=f'/v2/notifications/{notification_type}',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), create_service_authorization_header(service_id=service.id)]
        )

        json_resp = response.get_json()

        assert response.status_code == 201
        assert json_resp['id']
        assert json_resp['content']['body'] == "Dear citizen, have a nice day"
        assert json_resp['template']['id'] == str(template.id)
        save_task.assert_called_once_with([mock.ANY], queue=f'save-api-{notification_type}-tasks')
        mock_send_task.assert_called_once_with([json_resp['id']], queue=f'send-{notification_type}-tasks')
        assert Notification.query.count() == 1


@pytest.mark.parametrize("notification_type", ("email", "sms"))
def test_post_notifications_doesnt_use_save_queue_for_test_notifications(
    client, notify_db_session, mocker, notification_type
):
    save_task = mocker.patch(f"app.celery.tasks.save_api_{notification_type}.apply_async")
    mock_send_task = mocker.patch(f'app.celery.provider_tasks.deliver_{notification_type}.apply_async')
    service = create_service(
        service_name='high volume service',
    )
    with set_config_values(current_app, {
        'HIGH_VOLUME_SERVICE': [str(service.id)],

    }):
        template = create_template(service=service, content='((message))', template_type=notification_type)
        data = {
            "template_id": template.id,
            "personalisation": {"message": "Dear citizen, have a nice day"}
        }
        data.update({"email_address": "joe.citizen@example.com"}) if notification_type == EMAIL_TYPE \
            else data.update({"phone_number": "+447700900855"})
        response = client.post(
            path=f'/v2/notifications/{notification_type}',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'),
                     create_service_authorization_header(service_id=service.id, key_type='test')]
        )

        json_resp = response.get_json()

        assert response.status_code == 201
        assert json_resp['id']
        assert json_resp['content']['body'] == "Dear citizen, have a nice day"
        assert json_resp['template']['id'] == str(template.id)
        assert mock_send_task.called
        assert not save_task.called
        assert len(Notification.query.all()) == 1


def test_post_notification_does_not_use_save_queue_for_letters(client, sample_letter_template, mocker):
    mock_save = mocker.patch("app.v2.notifications.post_notifications.save_email_or_sms_to_queue")
    mock_create_pdf_task = mocker.patch('app.celery.tasks.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async')

    with set_config_values(current_app, {
        'HIGH_VOLUME_SERVICE': [str(sample_letter_template.service_id)],

    }):
        data = {
            'template_id': str(sample_letter_template.id),
            'personalisation': {
                'address_line_1': 'Her Royal Highness Queen Elizabeth II',
                'address_line_2': 'Buckingham Palace',
                'address_line_3': 'London',
                'postcode': 'SW1 1AA',
            }
        }
        response = client.post(
            path='/v2/notifications/letter',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'),
                     create_service_authorization_header(service_id=sample_letter_template.service_id)]
        )
        assert response.status_code == 201
        json_resp = response.get_json()
        assert not mock_save.called
        mock_create_pdf_task.assert_called_once_with([str(json_resp['id'])], queue='create-letters-pdf-tasks')
