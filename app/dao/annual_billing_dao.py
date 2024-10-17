from flask import current_app
from sqlalchemy import select, update

from app import db
from app.dao.dao_utils import autocommit
from app.dao.date_util import get_current_calendar_year_start_year
from app.enums import OrganizationType
from app.models import AnnualBilling


@autocommit
def dao_create_or_update_annual_billing_for_year(
    service_id, free_sms_fragment_limit, financial_year_start
):
    result = dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start)

    if result:
        result.free_sms_fragment_limit = free_sms_fragment_limit
    else:
        result = AnnualBilling(
            service_id=service_id,
            financial_year_start=financial_year_start,
            free_sms_fragment_limit=free_sms_fragment_limit,
        )
    db.session.add(result)
    return result


def dao_get_annual_billing(service_id):
    stmt = (
        select(AnnualBilling)
        .filter_by(
            service_id=service_id,
        )
        .order_by(AnnualBilling.financial_year_start)
    )
    return db.session.execute(stmt).scalars().all()


@autocommit
def dao_update_annual_billing_for_future_years(
    service_id, free_sms_fragment_limit, financial_year_start
):
    stmt = (
        update(AnnualBilling)
        .filter(
            AnnualBilling.service_id == service_id,
            AnnualBilling.financial_year_start > financial_year_start,
        )
        .values({"free_sms_fragment_limit": free_sms_fragment_limit})
    )
    db.session.execute(stmt)
    db.session.commit()


def dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start=None):
    if not financial_year_start:
        financial_year_start = get_current_calendar_year_start_year()

    stmt = select(AnnualBilling).filter_by(
        service_id=service_id, financial_year_start=financial_year_start
    )
    return db.session.execute(stmt).scalars().first()


def dao_get_all_free_sms_fragment_limit(service_id):
    stmt = (
        select(AnnualBilling)
        .filter_by(
            service_id=service_id,
        )
        .order_by(AnnualBilling.financial_year_start)
    )
    return db.session.execute(stmt).scalars().all()


def set_default_free_allowance_for_service(service, year_start=None):
    default_free_sms_fragment_limits = {
        OrganizationType.FEDERAL: {
            2020: 250_000,
            2021: 150_000,
            2022: 40_000,
        },
        OrganizationType.STATE: {
            2020: 250_000,
            2021: 150_000,
            2022: 40_000,
        },
        OrganizationType.OTHER: {
            2020: 250_000,
            2021: 150_000,
            2022: 40_000,
        },
    }
    if not year_start:
        year_start = get_current_calendar_year_start_year()
    # handle cases where the year is less than 2020 or greater than 2021
    if year_start < 2020:
        year_start = 2020
    if year_start > 2022:
        year_start = 2022
    if service.organization_type:
        free_allowance = default_free_sms_fragment_limits[service.organization_type][
            year_start
        ]
    else:
        current_app.logger.info(
            f"no organization type for service {service.id}. Using other default of "
            f"{default_free_sms_fragment_limits['other'][year_start]}"
        )
        free_allowance = default_free_sms_fragment_limits[OrganizationType.OTHER][
            year_start
        ]

    return dao_create_or_update_annual_billing_for_year(
        service.id, free_allowance, year_start
    )
