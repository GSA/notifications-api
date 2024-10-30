from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time
from sqlalchemy import delete, select, update

from app import db, notification_provider_clients
from app.dao.provider_details_dao import (
    _get_sms_providers_for_update,
    dao_get_provider_stats,
    dao_update_provider_details,
    get_alternative_sms_provider,
    get_provider_details_by_identifier,
    get_provider_details_by_notification_type,
)
from app.enums import NotificationType, TemplateType
from app.models import ProviderDetails, ProviderDetailsHistory
from tests.app.db import create_ft_billing, create_service, create_template
from tests.conftest import set_config


@pytest.fixture(autouse=True)
def set_provider_resting_points(notify_api):
    with set_config(notify_api, "SMS_PROVIDER_RESTING_POINTS", {"sns": 100}):
        yield


def set_primary_sms_provider(identifier):
    primary_provider = get_provider_details_by_identifier(identifier)
    secondary_provider = get_provider_details_by_identifier(
        get_alternative_sms_provider(identifier)
    )

    dao_update_provider_details(primary_provider)
    dao_update_provider_details(secondary_provider)


def test_can_get_sms_non_international_providers(notify_db_session):
    sms_providers = get_provider_details_by_notification_type(NotificationType.SMS)
    assert len(sms_providers) > 0
    assert all(NotificationType.SMS == prov.notification_type for prov in sms_providers)


def test_can_get_sms_international_providers(notify_db_session):
    sms_providers = get_provider_details_by_notification_type(
        NotificationType.SMS, True
    )
    assert len(sms_providers) == 1
    assert all(NotificationType.SMS == prov.notification_type for prov in sms_providers)
    assert all(prov.supports_international for prov in sms_providers)


def test_can_get_email_providers(notify_db_session):
    assert len(get_provider_details_by_notification_type(NotificationType.EMAIL)) == 1
    types = [
        provider.notification_type
        for provider in get_provider_details_by_notification_type(
            NotificationType.EMAIL
        )
    ]
    assert all(
        NotificationType.EMAIL == notification_type for notification_type in types
    )


def test_should_not_error_if_any_provider_in_code_not_in_database(
    restore_provider_details,
):
    stmt = delete(ProviderDetails).where(ProviderDetails.identifier == "sns")
    db.session.execute(stmt)
    db.session.commit()

    assert notification_provider_clients.get_sms_client("sns")


@freeze_time("2000-01-01T00:00:00")
def test_update_adds_history(restore_provider_details):
    stmt = select(ProviderDetails).where(ProviderDetails.identifier == "ses")
    ses = db.session.execute(stmt).scalars().one()
    stmt = select(ProviderDetailsHistory).where(ProviderDetailsHistory.id == ses.id)
    ses_history = db.session.execute(stmt).scalars().one()

    assert ses.version == 1
    assert ses_history.version == 1
    assert ses.updated_at is None

    ses.active = False

    dao_update_provider_details(ses)

    assert not ses.active
    assert ses.updated_at == datetime(2000, 1, 1, 0, 0, 0)

    stmt = (
        select(ProviderDetailsHistory)
        .where(ProviderDetailsHistory.id == ses.id)
        .order_by(ProviderDetailsHistory.version)
    )
    ses_history = db.session.execute(stmt).scalars().all()

    assert ses_history[0].active
    assert ses_history[0].version == 1
    assert ses_history[0].updated_at is None

    assert not ses_history[1].active
    assert ses_history[1].version == 2
    assert ses_history[1].updated_at == datetime(2000, 1, 1, 0, 0, 0)


def test_update_sms_provider_to_inactive_sets_inactive(restore_provider_details):
    sns = get_provider_details_by_identifier("sns")

    sns.active = False
    dao_update_provider_details(sns)

    assert not sns.active


@pytest.mark.parametrize("identifier, expected", [("sns", "other")])
def test_get_alternative_sms_provider_returns_expected_provider(identifier, expected):
    """Currently always raises, as we only have SNS configured"""
    # flake8 doesn't like raises with a generic Exception
    try:
        get_alternative_sms_provider(identifier)
        assert 1 == 0
    except Exception:
        assert 1 == 1


def test_get_alternative_sms_provider_fails_if_unrecognised():
    with pytest.raises(ValueError):
        get_alternative_sms_provider("ses")


@freeze_time("2016-01-01 01:00")
def test_get_sms_providers_for_update_returns_providers(restore_provider_details):
    stmt = (
        update(ProviderDetails)
        .where(ProviderDetails.identifier == "sns")
        .values({"updated_at": None})
    )
    db.session.execute(stmt)
    db.session.commit()

    resp = _get_sms_providers_for_update(timedelta(hours=1))

    assert {p.identifier for p in resp} == {"sns"}


@freeze_time("2016-01-01 01:00")
def test_get_sms_providers_for_update_returns_nothing_if_recent_updates(
    restore_provider_details,
):
    fifty_nine_minutes_ago = datetime(2016, 1, 1, 0, 1)
    stmt = (
        update(ProviderDetails)
        .where(ProviderDetails.identifier == "sns")
        .values({"updated_at": fifty_nine_minutes_ago})
    )
    db.session.execute(stmt)
    db.session.commit()

    resp = _get_sms_providers_for_update(timedelta(hours=1))

    assert not resp


@freeze_time("2018-06-28 12:00")
def test_dao_get_provider_stats(notify_db_session):
    service_1 = create_service(service_name="1")
    service_2 = create_service(service_name="2")
    sms_template_1 = create_template(service_1, TemplateType.SMS)
    sms_template_2 = create_template(service_2, TemplateType.SMS)

    create_ft_billing("2017-06-05", sms_template_2, provider="sns", billable_unit=4)
    create_ft_billing("2018-06-03", sms_template_2, provider="sns", billable_unit=4)
    create_ft_billing("2018-06-15", sms_template_1, provider="sns", billable_unit=1)

    results = dao_get_provider_stats()

    assert len(results) > 0

    ses = next(result for result in results if result.identifier == "ses")
    sns = next(result for result in results if result.identifier == "sns")

    assert ses.display_name == "AWS SES"
    assert ses.created_by_name is None
    assert ses.current_month_billable_sms == 0

    assert sns.display_name == "AWS SNS"
    assert sns.notification_type == NotificationType.SMS
    assert sns.supports_international is True
    assert sns.active is True
    assert sns.current_month_billable_sms == 5
