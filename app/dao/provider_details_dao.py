from datetime import datetime

from flask import current_app
from sqlalchemy import desc, func, select

from app import db
from app.dao.dao_utils import autocommit
from app.enums import NotificationType
from app.models import FactBilling, ProviderDetails, ProviderDetailsHistory, User
from app.utils import utc_now


def get_provider_details_by_id(provider_details_id):
    return db.session.get(ProviderDetails, provider_details_id)


def get_provider_details_by_identifier(identifier):
    stmt = select(ProviderDetails).where(ProviderDetails.identifier == identifier)
    return db.session.execute(stmt).scalars().one()


def get_alternative_sms_provider(identifier):
    if identifier == "sns":
        raise Exception("No alternative SMS providers currently available")
    raise ValueError("Unrecognised sms provider {}".format(identifier))


def dao_get_provider_versions(provider_id):
    stmt = (
        select(ProviderDetailsHistory)
        .where(ProviderDetailsHistory.id == provider_id)
        .order_by(desc(ProviderDetailsHistory.version))
        .limit(100)
    )
    # limit results instead of adding pagination
    return db.session.execute(stmt).scalars().all()


def _get_sms_providers_for_update(time_threshold):
    """
    Returns a list of providers, while holding a for_update lock on the provider details table, guaranteeing that those
    providers won't change (but can still be read) until you've committed/rolled back your current transaction.

    if any of the providers have been changed recently, it returns an empty list - it's still your responsiblity to
    release the transaction in that case
    """
    # get current priority of both providers
    stmt = (
        select(ProviderDetails)
        .where(
            ProviderDetails.notification_type == NotificationType.SMS,
            ProviderDetails.active,
        )
        .with_for_update()
    )
    q = db.session.execute(stmt).scalars().all()

    # if something updated recently, don't update again. If the updated_at is null, treat it as min time
    if any(
        (provider.updated_at or datetime.min) > utc_now() - time_threshold
        for provider in q
    ):
        current_app.logger.info(
            f"Not adjusting providers, providers updated less than {time_threshold} ago."
        )
        return []

    return q


def get_provider_details_by_notification_type(
    notification_type, supports_international=False
):
    filters = [ProviderDetails.notification_type == notification_type]

    if supports_international:
        filters.append(ProviderDetails.supports_international == supports_international)

    stmt = select(ProviderDetails).where(*filters)
    return db.session.execute(stmt).scalars().all()


@autocommit
def dao_update_provider_details(provider_details):
    _update_provider_details_without_commit(provider_details)


def _update_provider_details_without_commit(provider_details):
    """
    Doesn't commit, for when you need to control the database transaction manually
    """
    provider_details.version += 1
    provider_details.updated_at = utc_now()
    history = ProviderDetailsHistory.from_original(provider_details)
    db.session.add(provider_details)
    db.session.add(history)


def dao_get_provider_stats():
    # this query does not include the current day since the task to populate ft_billing runs overnight

    current_datetime = utc_now()
    first_day_of_the_month = current_datetime.date().replace(day=1)

    substmt = (
        db.session.query(
            FactBilling.provider,
            func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label(
                "current_month_billable_sms"
            ),
        )
        .filter(
            FactBilling.notification_type == NotificationType.SMS,
            FactBilling.local_date >= first_day_of_the_month,
        )
        .group_by(FactBilling.provider)
        .subquery()
    )

    result = (
        db.session.query(
            ProviderDetails.id,
            ProviderDetails.display_name,
            ProviderDetails.identifier,
            ProviderDetails.notification_type,
            ProviderDetails.active,
            ProviderDetails.updated_at,
            ProviderDetails.supports_international,
            User.name.label("created_by_name"),
            func.coalesce(substmt.c.current_month_billable_sms, 0).label(
                "current_month_billable_sms"
            ),
        )
        .outerjoin(substmt, ProviderDetails.identifier == substmt.c.provider)
        .outerjoin(User, ProviderDetails.created_by_id == User.id)
        .order_by(
            ProviderDetails.notification_type,
        )
        .all()
    )

    return result
