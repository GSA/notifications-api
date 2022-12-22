import pytest
from flask import json

from app.notifications.notifications_sms_callback import validate_callback_data


def mmg_post(client, data):
    return client.post(
        path='/notifications/sms/mmg',
        data=data,
        headers=[('Content-Type', 'application/json')])


@pytest.mark.skip(reason="Needs updating for TTS: MMG removal")
def test_mmg_callback_should_not_need_auth(client, mocker, sample_notification):
    mocker.patch('app.notifications.notifications_sms_callback.process_sms_client_response')
    data = json.dumps({"reference": "mmg_reference",
                       "CID": str(sample_notification.id),
                       "MSISDN": "447777349060",
                       "status": "3",
                       "deliverytime": "2016-04-05 16:01:07"})

    response = mmg_post(client, data)
    assert response.status_code == 200


@pytest.mark.skip(reason="Needs updating for TTS: MMG removal")
def test_process_mmg_response_returns_400_for_malformed_data(client):
    data = json.dumps({"reference": "mmg_reference",
                       "monkey": 'random thing',
                       "MSISDN": "447777349060",
                       "no_status": 00,
                       "deliverytime": "2016-04-05 16:01:07"})

    response = mmg_post(client, data)
    assert response.status_code == 400
    json_data = json.loads(response.data)
    assert json_data['result'] == 'error'
    assert len(json_data['message']) == 2
    assert "{} callback failed: {} missing".format('MMG', 'status') in json_data['message']
    assert "{} callback failed: {} missing".format('MMG', 'CID') in json_data['message']


@pytest.mark.skip(reason="Needs updating for TTS: MMG removal")
def test_mmg_callback_should_return_200_and_call_task_with_valid_data(client, mocker):
    mock_celery = mocker.patch(
        'app.notifications.notifications_sms_callback.process_sms_client_response.apply_async')
    data = json.dumps({"reference": "mmg_reference",
                       "CID": "notification_id",
                       "MSISDN": "447777349060",
                       "status": "3",
                       "substatus": "5",
                       "deliverytime": "2016-04-05 16:01:07"})

    response = mmg_post(client, data)

    assert response.status_code == 200
    json_data = json.loads(response.data)
    assert json_data['result'] == 'success'

    mock_celery.assert_called_once_with(
        ['3', 'notification_id', 'MMG', '5'],
        queue='sms-callbacks',
    )


def test_validate_callback_data_returns_none_when_valid():
    form = {'status': 'good',
            'reference': 'send-sms-code'}
    fields = ['status', 'reference']
    client_name = 'sms client'

    assert validate_callback_data(form, fields, client_name) is None


def test_validate_callback_data_return_errors_when_fields_are_empty():
    form = {'monkey': 'good'}
    fields = ['status', 'cid']
    client_name = 'sms client'

    errors = validate_callback_data(form, fields, client_name)
    assert len(errors) == 2
    assert "{} callback failed: {} missing".format(client_name, 'status') in errors
    assert "{} callback failed: {} missing".format(client_name, 'cid') in errors


def test_validate_callback_data_can_handle_integers():
    form = {'status': 00, 'cid': 'fsdfadfsdfas'}
    fields = ['status', 'cid']
    client_name = 'sms client'

    result = validate_callback_data(form, fields, client_name)
    assert result is None


def test_validate_callback_data_returns_error_for_empty_string():
    form = {'status': '', 'cid': 'fsdfadfsdfas'}
    fields = ['status', 'cid']
    client_name = 'sms client'

    result = validate_callback_data(form, fields, client_name)
    assert result is not None
    assert "{} callback failed: {} missing".format(client_name, 'status') in result
