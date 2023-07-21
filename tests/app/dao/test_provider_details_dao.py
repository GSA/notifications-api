from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time
from sqlalchemy.sql import desc

from app import notification_provider_clients
from app.dao.provider_details_dao import (
    _adjust_provider_priority,
    _get_sms_providers_for_update,
    dao_adjust_provider_priority_back_to_resting_points,
    dao_get_provider_stats,
    dao_reduce_sms_provider_priority,
    dao_update_provider_details,
    get_alternative_sms_provider,
    get_provider_details_by_identifier,
    get_provider_details_by_notification_type,
)
from app.models import ProviderDetails, ProviderDetailsHistory
from tests.app.db import create_ft_billing, create_service, create_template
from tests.conftest import set_config


@pytest.fixture(autouse=True)
def set_provider_resting_points(notify_api):
    with set_config(notify_api, 'SMS_PROVIDER_RESTING_POINTS', {'sns': 100}):
        yield


def set_primary_sms_provider(identifier):
    primary_provider = get_provider_details_by_identifier(identifier)
    secondary_provider = get_provider_details_by_identifier(get_alternative_sms_provider(identifier))

    primary_provider.priority = 10
    secondary_provider.priority = 20

    dao_update_provider_details(primary_provider)
    dao_update_provider_details(secondary_provider)


def test_can_get_sms_non_international_providers(notify_db_session):
    sms_providers = get_provider_details_by_notification_type('sms')
    assert len(sms_providers) > 0
    assert all('sms' == prov.notification_type for prov in sms_providers)


def test_can_get_sms_international_providers(notify_db_session):
    sms_providers = get_provider_details_by_notification_type('sms', True)
    assert len(sms_providers) == 1
    assert all('sms' == prov.notification_type for prov in sms_providers)
    assert all(prov.supports_international for prov in sms_providers)


def test_can_get_sms_providers_in_order_of_priority(notify_db_session):
    providers = get_provider_details_by_notification_type('sms', False)
    priorities = [provider.priority for provider in providers]
    assert priorities == sorted(priorities)


def test_can_get_email_providers_in_order_of_priority(notify_db_session):
    providers = get_provider_details_by_notification_type('email')

    assert providers[0].identifier == "ses"


def test_can_get_email_providers(notify_db_session):
    assert len(get_provider_details_by_notification_type('email')) == 1
    types = [provider.notification_type for provider in get_provider_details_by_notification_type('email')]
    assert all('email' == notification_type for notification_type in types)


def test_should_not_error_if_any_provider_in_code_not_in_database(restore_provider_details):
    ProviderDetails.query.filter_by(identifier='sns').delete()

    assert notification_provider_clients.get_sms_client('sns')


@freeze_time('2000-01-01T00:00:00')
def test_update_adds_history(restore_provider_details):
    ses = ProviderDetails.query.filter(ProviderDetails.identifier == 'ses').one()
    ses_history = ProviderDetailsHistory.query.filter(ProviderDetailsHistory.id == ses.id).one()

    assert ses.version == 1
    assert ses_history.version == 1
    assert ses.updated_at is None

    ses.active = False

    dao_update_provider_details(ses)

    assert not ses.active
    assert ses.updated_at == datetime(2000, 1, 1, 0, 0, 0)

    ses_history = ProviderDetailsHistory.query.filter(
        ProviderDetailsHistory.id == ses.id
    ).order_by(
        ProviderDetailsHistory.version
    ).all()

    assert ses_history[0].active
    assert ses_history[0].version == 1
    assert ses_history[0].updated_at is None

    assert not ses_history[1].active
    assert ses_history[1].version == 2
    assert ses_history[1].updated_at == datetime(2000, 1, 1, 0, 0, 0)


def test_update_sms_provider_to_inactive_sets_inactive(restore_provider_details):
    sns = get_provider_details_by_identifier('sns')

    sns.active = False
    dao_update_provider_details(sns)

    assert not sns.active


@pytest.mark.parametrize('identifier, expected', [
    ('sns', 'other')
])
def test_get_alternative_sms_provider_returns_expected_provider(identifier, expected):
    """Currently always raises, as we only have SNS configured"""
    # with pytest.raises(Exception):
    get_alternative_sms_provider(identifier)


def test_get_alternative_sms_provider_fails_if_unrecognised():
    with pytest.raises(ValueError):
        get_alternative_sms_provider('ses')


@freeze_time('2016-01-01 00:30')
def test_adjust_provider_priority_sets_priority(
    restore_provider_details,
    notify_user,
    sns_provider,
):
    # need to update these manually to avoid triggering the `onupdate` clause of the updated_at column
    ProviderDetails.query.filter(ProviderDetails.identifier == 'sns').update({'updated_at': datetime.min})

    _adjust_provider_priority(sns_provider, 50)

    assert sns_provider.updated_at == datetime.utcnow()
    assert sns_provider.created_by.id == notify_user.id
    assert sns_provider.priority == 50


@freeze_time('2016-01-01 00:30')
def test_adjust_provider_priority_adds_history(
    restore_provider_details,
    notify_user,
    sns_provider,
):
    # need to update these manually to avoid triggering the `onupdate` clause of the updated_at column
    ProviderDetails.query.filter(ProviderDetails.identifier == 'sns').update({'updated_at': datetime.min})

    old_provider_history_rows = ProviderDetailsHistory.query.filter(
        ProviderDetailsHistory.id == sns_provider.id
    ).order_by(
        desc(ProviderDetailsHistory.version)
    ).all()

    _adjust_provider_priority(sns_provider, 50)

    updated_provider_history_rows = ProviderDetailsHistory.query.filter(
        ProviderDetailsHistory.id == sns_provider.id
    ).order_by(
        desc(ProviderDetailsHistory.version)
    ).all()

    assert len(updated_provider_history_rows) - len(old_provider_history_rows) == 1
    assert updated_provider_history_rows[0].version - old_provider_history_rows[0].version == 1
    assert updated_provider_history_rows[0].priority == 50


@freeze_time('2016-01-01 01:00')
def test_get_sms_providers_for_update_returns_providers(restore_provider_details):
    ProviderDetails.query.filter(ProviderDetails.identifier == 'sns').update({'updated_at': None})

    resp = _get_sms_providers_for_update(timedelta(hours=1))

    assert {p.identifier for p in resp} == {'sns'}


@freeze_time('2016-01-01 01:00')
def test_get_sms_providers_for_update_returns_nothing_if_recent_updates(restore_provider_details):
    fifty_nine_minutes_ago = datetime(2016, 1, 1, 0, 1)
    ProviderDetails.query.filter(ProviderDetails.identifier == 'sns').update({'updated_at': fifty_nine_minutes_ago})

    resp = _get_sms_providers_for_update(timedelta(hours=1))

    assert not resp


def test_reduce_sms_provider_priority_does_nothing_if_providers_have_recently_changed(
    mocker,
    restore_provider_details,
):
    mock_get_providers = mocker.patch('app.dao.provider_details_dao._get_sms_providers_for_update', return_value=[])
    mock_adjust = mocker.patch('app.dao.provider_details_dao._adjust_provider_priority')

    dao_reduce_sms_provider_priority('sns', time_threshold=timedelta(minutes=5))

    mock_get_providers.assert_called_once_with(timedelta(minutes=5))
    assert mock_adjust.called is False


def test_reduce_sms_provider_priority_does_nothing_if_there_is_only_one_active_provider(
    mocker,
    restore_provider_details,
):
    mock_adjust = mocker.patch('app.dao.provider_details_dao._adjust_provider_priority')

    dao_reduce_sms_provider_priority('sns', time_threshold=timedelta(minutes=5))

    assert mock_adjust.called is False


def test_adjust_provider_priority_back_to_resting_points_does_nothing_if_theyre_already_at_right_values(
    restore_provider_details,
    mocker,
):
    sns = get_provider_details_by_identifier('sns')
    sns.priority = 100

    mock_adjust = mocker.patch('app.dao.provider_details_dao._adjust_provider_priority')
    mocker.patch('app.dao.provider_details_dao._get_sms_providers_for_update', return_value=[sns])

    dao_adjust_provider_priority_back_to_resting_points()

    assert mock_adjust.called is False


def test_adjust_provider_priority_back_to_resting_points_does_nothing_if_no_providers_to_update(
    restore_provider_details,
    mocker,
):
    mock_adjust = mocker.patch('app.dao.provider_details_dao._adjust_provider_priority')
    mocker.patch('app.dao.provider_details_dao._get_sms_providers_for_update', return_value=[])

    dao_adjust_provider_priority_back_to_resting_points()

    assert mock_adjust.called is False


@freeze_time('2018-06-28 12:00')
def test_dao_get_provider_stats(notify_db_session):
    service_1 = create_service(service_name='1')
    service_2 = create_service(service_name='2')
    sms_template_1 = create_template(service_1, 'sms')
    sms_template_2 = create_template(service_2, 'sms')

    create_ft_billing('2017-06-05', sms_template_2, provider='sns', billable_unit=4)
    create_ft_billing('2018-06-03', sms_template_2, provider='sns', billable_unit=4)
    create_ft_billing('2018-06-15', sms_template_1, provider='sns', billable_unit=1)

    results = dao_get_provider_stats()

    assert len(results) > 0

    ses = next(result for result in results if result.identifier == 'ses')
    sns = next(result for result in results if result.identifier == 'sns')

    assert ses.display_name == 'AWS SES'
    assert ses.created_by_name is None
    assert ses.current_month_billable_sms == 0

    assert sns.display_name == 'AWS SNS'
    assert sns.notification_type == 'sms'
    assert sns.supports_international is True
    assert sns.active is True
    assert sns.current_month_billable_sms == 5
