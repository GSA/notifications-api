import os
from collections import defaultdict, namedtuple
from datetime import date, datetime

import pytest
from flask import current_app
from freezegun import freeze_time

from app.celery.tasks import (
    check_billable_units,
    get_local_billing_date_from_filename,
    persist_daily_sorted_letter_counts,
    process_updates_from_file,
    record_daily_sorted_counts,
    update_letter_notifications_to_error,
    update_letter_notifications_to_sent_to_dvla,
)
from app.dao.daily_sorted_letter_dao import (
    dao_get_daily_sorted_letter_by_billing_day,
)
from app.exceptions import DVLAException, NotificationTechnicalFailureException
from app.models import (
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    DailySortedLetter,
    NotificationHistory,
)
from tests.app.db import (
    create_notification,
    create_notification_history,
    create_service_callback_api,
)
from tests.conftest import set_config


@pytest.fixture
def notification_update():
    """
    Returns a namedtuple to use as the argument for the check_billable_units function
    """
    NotificationUpdate = namedtuple('NotificationUpdate', ['reference', 'status', 'page_count', 'cost_threshold'])
    return NotificationUpdate('REFERENCE_ABC', 'sent', '1', 'cost')


def test_update_letter_notifications_to_sent_to_dvla_updates_based_on_notification_references(
    client,
    sample_letter_template
):
    first = create_notification(sample_letter_template, reference='first ref')
    second = create_notification(sample_letter_template, reference='second ref')

    dt = datetime.utcnow()
    with freeze_time(dt):
        update_letter_notifications_to_sent_to_dvla([first.reference])

    assert first.status == NOTIFICATION_SENDING
    assert first.sent_by == 'dvla'
    assert first.sent_at == dt
    assert first.updated_at == dt
    assert second.status == NOTIFICATION_CREATED


def test_update_letter_notifications_to_error_updates_based_on_notification_references(
    sample_letter_template
):
    first = create_notification(sample_letter_template, reference='first ref')
    second = create_notification(sample_letter_template, reference='second ref')
    create_service_callback_api(service=sample_letter_template.service, url="https://original_url.com")
    dt = datetime.utcnow()
    with freeze_time(dt):
        with pytest.raises(NotificationTechnicalFailureException) as e:
            update_letter_notifications_to_error([first.reference])
    assert first.reference in str(e.value)

    assert first.status == NOTIFICATION_TECHNICAL_FAILURE
    assert first.sent_by is None
    assert first.sent_at is None
    assert first.updated_at == dt
    assert second.status == NOTIFICATION_CREATED


def test_check_billable_units_when_billable_units_matches_page_count(
    client,
    sample_letter_template,
    mocker,
    notification_update
):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.error')

    create_notification(sample_letter_template, reference='REFERENCE_ABC', billable_units=1)

    check_billable_units(notification_update)

    mock_logger.assert_not_called()


def test_check_billable_units_when_billable_units_does_not_match_page_count(
    client,
    sample_letter_template,
    mocker,
    notification_update
):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.exception')

    notification = create_notification(sample_letter_template, reference='REFERENCE_ABC', billable_units=3)

    check_billable_units(notification_update)

    mock_logger.assert_called_once_with(
        'Notification with id {} has 3 billable_units but DVLA says page count is 1'.format(notification.id)
    )


@pytest.mark.parametrize('filename_date, billing_date', [
    ('20170820000000', date(2017, 8, 19)),
    ('20170120230000', date(2017, 1, 20))
])
def test_get_local_billing_date_from_filename(filename_date, billing_date):
    filename = 'NOTIFY-{}-RSP.TXT'.format(filename_date)
    result = get_local_billing_date_from_filename(filename)

    assert result == billing_date


@freeze_time("2018-01-11 09:00:00")
def test_persist_daily_sorted_letter_counts_saves_sorted_and_unsorted_values(client, notify_db_session):
    letter_counts = defaultdict(int, **{'unsorted': 5, 'sorted': 1})
    persist_daily_sorted_letter_counts(date.today(), "test.txt", letter_counts)
    day = dao_get_daily_sorted_letter_by_billing_day(date.today())

    assert day.unsorted_count == 5
    assert day.sorted_count == 1


def test_record_daily_sorted_counts_persists_daily_sorted_letter_count(
    notify_api,
    notify_db_session,
    mocker,
):
    valid_file = 'Letter1|Sent|1|uNsOrTeD\nLetter2|Sent|2|SORTED\nLetter3|Sent|2|Sorted'

    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)

    assert DailySortedLetter.query.count() == 0

    record_daily_sorted_counts(filename='NOTIFY-20170823160812-RSP.TXT')

    daily_sorted_counts = DailySortedLetter.query.all()
    assert len(daily_sorted_counts) == 1
    assert daily_sorted_counts[0].sorted_count == 2
    assert daily_sorted_counts[0].unsorted_count == 1


def test_record_daily_sorted_counts_raises_dvla_exception_with_unknown_sorted_status(
    notify_api,
    mocker,
):
    file_contents = 'ref-foo|Failed|1|invalid\nrow_2|Failed|1|MM'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=file_contents)
    filename = "failed.txt"
    with pytest.raises(DVLAException) as e:
        record_daily_sorted_counts(filename=filename)

    assert "DVLA response file: {} contains unknown Sorted status".format(filename) in e.value.message
    assert "'mm'" in e.value.message
    assert "'invalid'" in e.value.message


def test_record_daily_sorted_counts_persists_daily_sorted_letter_count_with_no_sorted_values(
    notify_api,
    mocker,
    notify_db_session
):
    valid_file = 'Letter1|Sent|1|Unsorted\nLetter2|Sent|2|Unsorted'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)

    record_daily_sorted_counts(filename='NOTIFY-20170823160812-RSP.TXT')

    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(date(2017, 8, 23))

    assert daily_sorted_letter.unsorted_count == 2
    assert daily_sorted_letter.sorted_count == 0


def test_record_daily_sorted_counts_can_run_twice_for_same_file(
    notify_api,
    mocker,
    notify_db_session
):
    valid_file = 'Letter1|Sent|1|sorted\nLetter2|Sent|2|Unsorted'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)

    record_daily_sorted_counts(filename='NOTIFY-20170823160812-RSP.TXT')

    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(date(2017, 8, 23))

    assert daily_sorted_letter.unsorted_count == 1
    assert daily_sorted_letter.sorted_count == 1

    updated_file = 'Letter1|Sent|1|sorted\nLetter2|Sent|2|Unsorted\nLetter3|Sent|2|Unsorted'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=updated_file)

    record_daily_sorted_counts(filename='NOTIFY-20170823160812-RSP.TXT')
    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(date(2017, 8, 23))

    assert daily_sorted_letter.unsorted_count == 2
    assert daily_sorted_letter.sorted_count == 1
