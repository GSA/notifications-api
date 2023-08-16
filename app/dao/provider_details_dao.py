from datetime import datetime

from flask import current_app
from sqlalchemy import asc, desc, func

from app import db
from app.dao.dao_utils import autocommit
from app.models import (
    SMS_TYPE,
    FactBilling,
    ProviderDetails,
    ProviderDetailsHistory,
    User,
)


def get_provider_details_by_id(provider_details_id):
    return ProviderDetails.query.get(provider_details_id)


def get_provider_details_by_identifier(identifier):
    return ProviderDetails.query.filter_by(identifier=identifier).one()


def get_alternative_sms_provider(identifier):
    if identifier == 'sns':
        raise Exception("No alternative SMS providers currently available")
    raise ValueError('Unrecognised sms provider {}'.format(identifier))


def dao_get_provider_versions(provider_id):
    return ProviderDetailsHistory.query.filter_by(
        id=provider_id
    ).order_by(
        desc(ProviderDetailsHistory.version)
    ).limit(
        100  # limit results instead of adding pagination
    ).all()


def _adjust_provider_priority(provider, new_priority):
    current_app.logger.info(
        f'Adjusting provider priority - {provider.identifier} going from {provider.priority} to {new_priority}'
    )
    provider.priority = new_priority

    # Automatic update so set as notify user
    provider.created_by_id = current_app.config['NOTIFY_USER_ID']

    # update without commit so that both rows can be changed without ending the transaction
    # and releasing the for_update lock
    _update_provider_details_without_commit(provider)


def _get_sms_providers_for_update(time_threshold):
    """
    Returns a list of providers, while holding a for_update lock on the provider details table, guaranteeing that those
    providers won't change (but can still be read) until you've committed/rolled back your current transaction.

    if any of the providers have been changed recently, it returns an empty list - it's still your responsiblity to
    release the transaction in that case
    """
    # get current priority of both providers
    q = ProviderDetails.query.filter(
        ProviderDetails.notification_type == 'sms',
        ProviderDetails.active
    ).with_for_update().all()

    # if something updated recently, don't update again. If the updated_at is null, treat it as min time
    if any((provider.updated_at or datetime.min) > datetime.utcnow() - time_threshold for provider in q):
        current_app.logger.info(f"Not adjusting providers, providers updated less than {time_threshold} ago.")
        return []

    return q


def get_provider_details_by_notification_type(notification_type, supports_international=False):

    filters = [ProviderDetails.notification_type == notification_type]

    if supports_international:
        filters.append(ProviderDetails.supports_international == supports_international)

    return ProviderDetails.query.filter(*filters).order_by(asc(ProviderDetails.priority)).all()


@autocommit
def dao_update_provider_details(provider_details):
    _update_provider_details_without_commit(provider_details)


def _update_provider_details_without_commit(provider_details):
    """
    Doesn't commit, for when you need to control the database transaction manually
    """
    provider_details.version += 1
    provider_details.updated_at = datetime.utcnow()
    history = ProviderDetailsHistory.from_original(provider_details)
    db.session.add(provider_details)
    db.session.add(history)


def dao_get_provider_stats():
    # this query does not include the current day since the task to populate ft_billing runs overnight

    current_datetime = datetime.utcnow()
    first_day_of_the_month = current_datetime.date().replace(day=1)

    subquery = db.session.query(
        FactBilling.provider,
        func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label('current_month_billable_sms')
    ).filter(
        FactBilling.notification_type == SMS_TYPE,
        FactBilling.local_date >= first_day_of_the_month
    ).group_by(
        FactBilling.provider
    ).subquery()

    result = db.session.query(
        ProviderDetails.id,
        ProviderDetails.display_name,
        ProviderDetails.identifier,
        ProviderDetails.priority,
        ProviderDetails.notification_type,
        ProviderDetails.active,
        ProviderDetails.updated_at,
        ProviderDetails.supports_international,
        User.name.label('created_by_name'),
        func.coalesce(subquery.c.current_month_billable_sms, 0).label('current_month_billable_sms')
    ).outerjoin(
        subquery, ProviderDetails.identifier == subquery.c.provider
    ).outerjoin(
        User, ProviderDetails.created_by_id == User.id
    ).order_by(
        ProviderDetails.notification_type,
        ProviderDetails.priority,
    ).all()

    return result
