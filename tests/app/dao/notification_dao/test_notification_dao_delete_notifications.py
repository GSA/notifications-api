import uuid
from datetime import datetime, timedelta

from freezegun import freeze_time

from app.dao.notifications_dao import (
    insert_notification_history_delete_notifications,
    move_notifications_to_notification_history,
)
from app.models import (
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    Notification,
    NotificationHistory,
)
from tests.app.db import (
    create_notification,
    create_notification_history,
    create_service,
    create_template,
)


def test_move_notifications_does_nothing_if_notification_history_row_already_exists(
    sample_email_template, mocker
):
    notification = create_notification(
        template=sample_email_template, created_at=datetime.utcnow() - timedelta(days=8),
        status='temporary-failure'
    )
    create_notification_history(
        id=notification.id, template=sample_email_template,
        created_at=datetime.utcnow() - timedelta(days=8), status='delivered'
    )

    move_notifications_to_notification_history("email", sample_email_template.service_id, datetime.utcnow(), 1)

    assert Notification.query.count() == 0
    history = NotificationHistory.query.all()
    assert len(history) == 1
    assert history[0].status == 'delivered'


def test_move_notifications_only_moves_notifications_older_than_provided_timestamp(sample_template):
    delete_time = datetime(2020, 6, 1, 12)
    one_second_before = delete_time - timedelta(seconds=1)
    one_second_after = delete_time + timedelta(seconds=1)
    old_notification = create_notification(template=sample_template, created_at=one_second_before)
    new_notification = create_notification(template=sample_template, created_at=one_second_after)

    # need to take a copy of the ID since the old_notification object will stop being accessible once removed
    old_notification_id = old_notification.id

    result = move_notifications_to_notification_history('sms', sample_template.service_id, delete_time)
    assert result == 1

    assert Notification.query.one().id == new_notification.id
    assert NotificationHistory.query.one().id == old_notification_id


def test_move_notifications_keeps_calling_until_no_more_to_delete_and_then_returns_total_deleted(
    mocker
):
    mock_insert = mocker.patch(
        'app.dao.notifications_dao.insert_notification_history_delete_notifications',
        side_effect=[5, 5, 1, 0]
    )
    service_id = uuid.uuid4()
    timestamp = datetime(2021, 1, 1)

    result = move_notifications_to_notification_history('sms', service_id, timestamp, qry_limit=5)
    assert result == 11

    mock_insert.asset_called_with(
        notification_type='sms',
        service_id=service_id,
        timestamp_to_delete_backwards_from=timestamp,
        qry_limit=5
    )
    assert mock_insert.call_count == 4


def test_move_notifications_only_moves_for_given_notification_type(sample_service):
    delete_time = datetime(2020, 6, 1, 12)
    one_second_before = delete_time - timedelta(seconds=1)

    sms_template = create_template(sample_service, 'sms')
    email_template = create_template(sample_service, 'email')
    create_notification(sms_template, created_at=one_second_before)
    create_notification(email_template, created_at=one_second_before)

    result = move_notifications_to_notification_history('sms', sample_service.id, delete_time)
    assert result == 1
    assert {x.notification_type for x in Notification.query} == {'email'}
    assert NotificationHistory.query.one().notification_type == 'sms'


def test_move_notifications_only_moves_for_given_service(notify_db_session):
    delete_time = datetime(2020, 6, 1, 12)
    one_second_before = delete_time - timedelta(seconds=1)

    service = create_service(service_name='service')
    other_service = create_service(service_name='other')

    template = create_template(service, 'sms')
    other_template = create_template(other_service, 'sms')

    create_notification(template, created_at=one_second_before)
    create_notification(other_template, created_at=one_second_before)

    result = move_notifications_to_notification_history('sms', service.id, delete_time)
    assert result == 1

    assert NotificationHistory.query.one().service_id == service.id
    assert Notification.query.one().service_id == other_service.id


def test_move_notifications_just_deletes_test_key_notifications(sample_template):
    delete_time = datetime(2020, 6, 1, 12)
    one_second_before = delete_time - timedelta(seconds=1)
    create_notification(template=sample_template, created_at=one_second_before, key_type=KEY_TYPE_NORMAL)
    create_notification(template=sample_template, created_at=one_second_before, key_type=KEY_TYPE_TEAM)
    create_notification(template=sample_template, created_at=one_second_before, key_type=KEY_TYPE_TEST)

    result = move_notifications_to_notification_history('sms', sample_template.service_id, delete_time)

    assert result == 2

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 2
    assert NotificationHistory.query.filter(NotificationHistory.key_type == KEY_TYPE_TEST).count() == 0


@freeze_time('2020-03-20 14:00')
def test_insert_notification_history_delete_notifications(sample_email_template):
    # should be deleted
    n1 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=4), status='delivered')
    n2 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=20), status='permanent-failure')
    n3 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=30), status='temporary-failure')
    n4 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=59), status='temporary-failure')
    n5 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, hours=1), status='sending')
    n6 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=61), status='pending')
    n7 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, hours=1, seconds=1),
                             status='validation-failed')
    n8 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=20), status='created')
    # should NOT be deleted - wrong status
    n9 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(hours=1), status='delivered')
    n10 = create_notification(template=sample_email_template,
                              created_at=datetime.utcnow() - timedelta(hours=1), status='technical-failure')
    n11 = create_notification(template=sample_email_template,
                              created_at=datetime.utcnow() - timedelta(hours=23, minutes=59), status='created')

    ids_to_move = sorted([n1.id, n2.id, n3.id, n4.id, n5.id, n6.id, n7.id, n8.id])
    ids_to_keep = sorted([n9.id, n10.id, n11.id])
    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_email_template.template_type,
        service_id=sample_email_template.service_id,
        timestamp_to_delete_backwards_from=datetime.utcnow() - timedelta(days=1))
    assert del_count == 8
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(history_rows) == 8
    assert ids_to_move == sorted([x.id for x in history_rows])
    assert len(notifications) == 3
    assert ids_to_keep == sorted([x.id for x in notifications])


def test_insert_notification_history_delete_notifications_more_notifications_than_query_limit(sample_template):
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() + timedelta(minutes=4), status='delivered')
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() + timedelta(minutes=20), status='permanent-failure')
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() + timedelta(minutes=30), status='temporary-failure')

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_template.template_type,
        service_id=sample_template.service_id,
        timestamp_to_delete_backwards_from=datetime.utcnow() + timedelta(hours=1),
        qry_limit=1
    )

    assert del_count == 1
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(history_rows) == 1
    assert len(notifications) == 2


def test_insert_notification_history_delete_notifications_only_insert_delete_for_given_service(sample_email_template):
    notification_to_move = create_notification(template=sample_email_template,
                                               created_at=datetime.utcnow() + timedelta(minutes=4), status='delivered')
    another_service = create_service(service_name='Another service')
    another_template = create_template(service=another_service, template_type='email')
    notification_to_stay = create_notification(template=another_template,
                                               created_at=datetime.utcnow() + timedelta(minutes=4), status='delivered')

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_email_template.template_type,
        service_id=sample_email_template.service_id,
        timestamp_to_delete_backwards_from=datetime.utcnow() + timedelta(hours=1)
    )

    assert del_count == 1
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(notifications) == 1
    assert len(history_rows) == 1
    assert notifications[0].id == notification_to_stay.id
    assert history_rows[0], id == notification_to_move.id


def test_insert_notification_history_delete_notifications_insert_for_key_type(sample_template):
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() - timedelta(hours=4),
                        status='delivered',
                        key_type='normal')
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() - timedelta(hours=4),
                        status='delivered',
                        key_type='team')
    with_test_key = create_notification(template=sample_template,
                                        created_at=datetime.utcnow() - timedelta(hours=4),
                                        status='delivered',
                                        key_type='test')

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_template.template_type,
        service_id=sample_template.service_id,
        timestamp_to_delete_backwards_from=datetime.utcnow()
    )

    assert del_count == 2
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(notifications) == 1
    assert with_test_key.id == notifications[0].id
    assert len(history_rows) == 2
