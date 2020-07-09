import uuid

from freezegun import freeze_time
import pytest

from app.models import BROADCAST_TYPE, BroadcastStatusType

from tests.app.db import create_broadcast_message, create_template, create_service, create_user


def test_get_broadcast_message(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, areas=['place A', 'region B'])

    response = admin_request.get(
        'broadcast_message.get_broadcast_message',
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['id'] == str(bm.id)
    assert response['template_name'] == t.name
    assert response['status'] == BroadcastStatusType.DRAFT
    assert response['created_at'] is not None
    assert response['starts_at'] is None
    assert response['areas'] == ['place A', 'region B']
    assert response['personalisation'] == {}


def test_get_broadcast_message_404s_if_message_doesnt_exist(admin_request, sample_service):
    err = admin_request.get(
        'broadcast_message.get_broadcast_message',
        service_id=sample_service.id,
        broadcast_message_id=uuid.uuid4(),
        _expected_status=404
    )
    assert err == {'message': 'No result found', 'result': 'error'}


def test_get_broadcast_message_404s_if_message_is_for_different_service(admin_request, sample_service):
    other_service = create_service(service_name='other')
    other_template = create_template(other_service, BROADCAST_TYPE)
    bm = create_broadcast_message(other_template)

    err = admin_request.get(
        'broadcast_message.get_broadcast_message',
        service_id=sample_service.id,
        broadcast_message_id=bm.id,
        _expected_status=404
    )
    assert err == {'message': 'No result found', 'result': 'error'}


@freeze_time('2020-01-01')
def test_get_broadcast_messages_for_service(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)

    with freeze_time('2020-01-01 12:00'):
        bm1 = create_broadcast_message(t, personalisation={'foo': 'bar'})
    with freeze_time('2020-01-01 13:00'):
        bm2 = create_broadcast_message(t, personalisation={'foo': 'baz'})

    response = admin_request.get(
        'broadcast_message.get_broadcast_messages_for_service',
        service_id=t.service_id,
        _expected_status=200
    )

    assert response['broadcast_messages'][0]['id'] == str(bm1.id)
    assert response['broadcast_messages'][1]['id'] == str(bm2.id)


@freeze_time('2020-01-01')
def test_create_broadcast_message(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)

    response = admin_request.post(
        'broadcast_message.create_broadcast_message',
        _data={
            'template_id': str(t.id),
            'service_id': str(t.service_id),
            'created_by': str(t.created_by_id),
        },
        service_id=t.service_id,
        _expected_status=201
    )

    assert response['template_name'] == t.name
    assert response['status'] == BroadcastStatusType.DRAFT
    assert response['created_at'] is not None
    assert response['created_by_id'] == str(t.created_by_id)
    assert response['personalisation'] == {}
    assert response['areas'] == []


@pytest.mark.parametrize('data, expected_errors', [
    (
        {},
        [
            {'error': 'ValidationError', 'message': 'template_id is a required property'},
            {'error': 'ValidationError', 'message': 'service_id is a required property'},
            {'error': 'ValidationError', 'message': 'created_by is a required property'}
        ]
    ),
    (
        {
            'template_id': str(uuid.uuid4()),
            'service_id': str(uuid.uuid4()),
            'created_by': str(uuid.uuid4()),
            'foo': 'something else'
        },
        [
            {'error': 'ValidationError', 'message': 'Additional properties are not allowed (foo was unexpected)'}
        ]
    )
])
def test_create_broadcast_message_400s_if_json_schema_fails_validation(
    admin_request,
    sample_service,
    data,
    expected_errors
):
    t = create_template(sample_service, BROADCAST_TYPE)

    response = admin_request.post(
        'broadcast_message.create_broadcast_message',
        _data=data,
        service_id=t.service_id,
        _expected_status=400
    )
    assert response['errors'] == expected_errors


def test_update_broadcast_message(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, areas=['manchester'])

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data={'starts_at': '2020-06-01 20:00:01', 'areas': ['london', 'glasgow']},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['starts_at'] == '2020-06-01T20:00:01.000000Z'
    assert response['areas'] == ['london', 'glasgow']
    assert response['updated_at'] is not None


@pytest.mark.parametrize('input_dt', [
    '2020-06-01 20:00:01',
    '2020-06-01T20:00:01',
    '2020-06-01 20:00:01Z',
    '2020-06-01T20:00:01+00:00',
])
def test_update_broadcast_message_allows_sensible_datetime_formats(admin_request, sample_service, input_dt):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data={'starts_at': input_dt},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['starts_at'] == '2020-06-01T20:00:01.000000Z'
    assert response['updated_at'] is not None


def test_update_broadcast_message_doesnt_let_you_update_status(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data={'areas': ['glasgow'], 'status': BroadcastStatusType.BROADCASTING},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400
    )

    assert response['errors'] == [{
        'error': 'ValidationError',
        'message': 'Additional properties are not allowed (status was unexpected)'
    }]


def test_update_broadcast_message_status(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.DRAFT)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.PENDING_APPROVAL, 'created_by': str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['status'] == BroadcastStatusType.PENDING_APPROVAL
    assert response['updated_at'] is not None


def test_update_broadcast_message_status_doesnt_let_you_update_other_things(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'areas': ['glasgow'], 'status': BroadcastStatusType.BROADCASTING, 'created_by': str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400
    )

    assert response['errors'] == [{
        'error': 'ValidationError',
        'message': 'Additional properties are not allowed (areas was unexpected)'
    }]


def test_update_broadcast_message_status_stores_cancelled_by_and_cancelled_at(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.BROADCASTING)
    canceller = create_user('canceller@gov.uk')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.CANCELLED, 'created_by': str(canceller.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['status'] == BroadcastStatusType.CANCELLED
    assert response['cancelled_at'] is not None
    assert response['cancelled_by_id'] == str(canceller.id)


def test_update_broadcast_message_status_stores_approved_by_and_approved_at(admin_request, sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.PENDING_APPROVAL)
    approver = create_user('approver@gov.uk')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.BROADCASTING, 'created_by': str(approver.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['status'] == BroadcastStatusType.BROADCASTING
    assert response['approved_at'] is not None
    assert response['approved_by_id'] == str(approver.id)
