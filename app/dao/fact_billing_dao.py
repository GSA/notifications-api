from datetime import date, timedelta

from flask import current_app
from sqlalchemy import Date, Integer, and_, delete, desc, func, select, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.expression import case, literal

from app import db
from app.dao.date_util import get_calendar_year_dates, get_calendar_year_for_datetime
from app.dao.organization_dao import (
    dao_get_organization_live_services,
    dao_get_organization_services,
)
from app.enums import KeyType, NotificationStatus, NotificationType
from app.models import (
    AnnualBilling,
    FactBilling,
    NotificationAllTimeView,
    NotificationHistory,
    Organization,
    Rate,
    Service,
)
from app.utils import get_midnight_in_utc, utc_now


def fetch_sms_free_allowance_remainder_until_date(end_date):
    # ASSUMPTION: AnnualBilling has been populated for year.
    billing_year = get_calendar_year_for_datetime(end_date)
    start_of_year = date(billing_year, 4, 1)

    billable_units = func.coalesce(
        func.sum(FactBilling.billable_units * FactBilling.rate_multiplier), 0
    )

    query = (
        select(
            AnnualBilling.service_id.label("service_id"),
            AnnualBilling.free_sms_fragment_limit,
            billable_units.label("billable_units"),
            func.greatest(
                (AnnualBilling.free_sms_fragment_limit - billable_units).cast(Integer),
                0,
            ).label("sms_remainder"),
        )
        .select_from(AnnualBilling)
        .outerjoin(
            # if there are no ft_billing rows for a service we still want to return the annual billing so we can use the
            # free_sms_fragment_limit)
            FactBilling,
            and_(
                AnnualBilling.service_id == FactBilling.service_id,
                FactBilling.local_date >= start_of_year,
                FactBilling.local_date < end_date,
                FactBilling.notification_type == NotificationType.SMS,
            ),
        )
        .where(
            AnnualBilling.financial_year_start == billing_year,
        )
        .group_by(
            AnnualBilling.service_id,
            AnnualBilling.free_sms_fragment_limit,
        )
    )
    return query


def fetch_sms_billing_for_all_services(start_date, end_date):
    # ASSUMPTION: AnnualBilling has been populated for year.
    allowance_left_at_start_date_stmt = fetch_sms_free_allowance_remainder_until_date(
        start_date
    ).subquery()

    sms_billable_units = func.sum(
        FactBilling.billable_units * FactBilling.rate_multiplier
    )

    # subtract sms_billable_units units accrued since report's start date to get up-to-date
    # allowance remainder
    sms_allowance_left = func.greatest(
        allowance_left_at_start_date_stmt.c.sms_remainder - sms_billable_units, 0
    )

    # billable units here are for period between start date and end date only, so to see
    # how many are chargeable, we need to see how much free allowance was used up in the
    # period up until report's start date and then do a subtraction
    chargeable_sms = func.greatest(
        sms_billable_units - allowance_left_at_start_date_stmt.c.sms_remainder, 0
    )
    sms_cost = chargeable_sms * FactBilling.rate

    query = (
        select(
            Organization.name.label("organization_name"),
            Organization.id.label("organization_id"),
            Service.name.label("service_name"),
            Service.id.label("service_id"),
            allowance_left_at_start_date_stmt.c.free_sms_fragment_limit,
            FactBilling.rate.label("sms_rate"),
            sms_allowance_left.label("sms_remainder"),
            sms_billable_units.label("sms_billable_units"),
            chargeable_sms.label("chargeable_billable_sms"),
            sms_cost.label("sms_cost"),
        )
        .select_from(Service)
        .outerjoin(
            allowance_left_at_start_date_stmt,
            Service.id == allowance_left_at_start_date_stmt.c.service_id,
        )
        .outerjoin(Service.organization)
        .join(
            FactBilling,
            FactBilling.service_id == Service.id,
        )
        .where(
            FactBilling.local_date >= start_date,
            FactBilling.local_date <= end_date,
            FactBilling.notification_type == NotificationType.SMS,
        )
        .group_by(
            Organization.name,
            Organization.id,
            Service.id,
            Service.name,
            allowance_left_at_start_date_stmt.c.free_sms_fragment_limit,
            allowance_left_at_start_date_stmt.c.sms_remainder,
            FactBilling.rate,
        )
        .order_by(Organization.name, Service.name)
    )

    return db.session.execute(query).all()


def fetch_billing_totals_for_year(service_id, year):
    """
    Returns a row for each distinct rate and notification_type from ft_billing
    over the specified financial year e.g.

        (
            rate=0.0165,
            notification_type=sms,
            notifications_sent=123,
            ...
        )

    The "query_service_<type>..." subqueries for each notification_type all
    return the same columns but differ internally e.g. SMS has to incorporate
    a rate multiplier. Each subquery returns the same set of columns, which we
    pick from here before the big union.
    """
    stmt = select(
        union(
            *[
                select(
                    stmt.c.notification_type.label("notification_type"),
                    stmt.c.rate.label("rate"),
                    func.sum(stmt.c.notifications_sent).label("notifications_sent"),
                    func.sum(stmt.c.chargeable_units).label("chargeable_units"),
                    func.sum(stmt.c.cost).label("cost"),
                    func.sum(stmt.c.free_allowance_used).label("free_allowance_used"),
                    func.sum(stmt.c.charged_units).label("charged_units"),
                ).group_by(stmt.c.rate, stmt.c.notification_type)
                for stmt in [
                    query_service_sms_usage_for_year(service_id, year).subquery(),
                    query_service_email_usage_for_year(service_id, year).subquery(),
                ]
            ]
        ).subquery()
    ).order_by(
        "notification_type",
        "rate",
    )
    return db.session.execute(stmt).all()


def fetch_monthly_billing_for_year(service_id, year):
    """
    Returns a row for each distinct rate, notification_type, and month
    from ft_billing over the specified financial year e.g.

        (
            rate=0.0165,
            notification_type=sms,
            month=2022-04-01 00:00:00,
            notifications_sent=123,
            ...
        )

    Each subquery takes care of anything specific to the notification type e.g.
    rate multipliers for SMS.

    Since the data in ft_billing is only refreshed once a day for all services,
    we also update the table on-the-fly if we need accurate data for this year.
    """
    _, year_end = get_calendar_year_dates(year)
    today = utc_now().date()

    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end >= today:
        data = fetch_billing_data_for_day(
            process_day=today, service_id=service_id, check_permissions=True
        )
        for d in data:
            update_fact_billing(data=d, process_day=today)

    stmt = select(
        union(
            *[
                select(
                    stmt.c.rate.label("rate"),
                    stmt.c.notification_type.label("notification_type"),
                    func.date_trunc("month", stmt.c.local_date)
                    .cast(Date)
                    .label("month"),
                    func.sum(stmt.c.notifications_sent).label("notifications_sent"),
                    func.sum(stmt.c.chargeable_units).label("chargeable_units"),
                    func.sum(stmt.c.cost).label("cost"),
                    func.sum(stmt.c.free_allowance_used).label("free_allowance_used"),
                    func.sum(stmt.c.charged_units).label("charged_units"),
                ).group_by(
                    stmt.c.rate,
                    stmt.c.notification_type,
                    "month",
                )
                for stmt in [
                    query_service_sms_usage_for_year(service_id, year).subquery(),
                    query_service_email_usage_for_year(service_id, year).subquery(),
                ]
            ]
        ).subquery()
    ).order_by(
        "month",
        "notification_type",
        "rate",
    )
    return db.session.execute(stmt).all()


def query_service_email_usage_for_year(service_id, year):
    year_start, year_end = get_calendar_year_dates(year)

    return (
        select(
            FactBilling.local_date,
            FactBilling.notifications_sent,
            FactBilling.billable_units.label("chargeable_units"),
            FactBilling.rate,
            FactBilling.notification_type,
            literal(0).label("cost"),
            literal(0).label("free_allowance_used"),
            FactBilling.billable_units.label("charged_units"),
        )
        .select_from(FactBilling)
        .where(
            FactBilling.service_id == service_id,
            FactBilling.local_date >= year_start,
            FactBilling.local_date <= year_end,
            FactBilling.notification_type == NotificationType.EMAIL,
        )
    )


def query_service_sms_usage_for_year(service_id, year):
    """
    Returns rows from the ft_billing table with some calculated values like cost,
    incorporating the SMS free allowance e.g.

        (
            local_date=2022-04-27,
            notifications_sent=12,
            chargeable_units=12,
            rate=0.0165,
            [cost=0      <== covered by the free allowance],
            [cost=0.198  <== if free allowance exhausted],
            [cost=0.099  <== only some free allowance left],
            ...
        )

    In order to calculate how much free allowance is left, we need to work out
    how much was used for previous local_dates - cumulative_chargeable_units -
    which we then subtract from the free allowance for the year.

    cumulative_chargeable_units is calculated using a "window" clause, which has
    access to all the rows identified by the query filter. Note that it's not
    affected by any GROUP BY clauses that happen in outer queries.

    https://www.postgresql.org/docs/current/tutorial-window.html

    ASSUMPTION: rates always change at midnight i.e. there can only be one rate
    on a given local_date. This means we don't need to worry about how to assign
    free allowance if it happens to run out when a rate changes.
    """
    year_start, year_end = get_calendar_year_dates(year)
    this_rows_chargeable_units = (
        FactBilling.billable_units * FactBilling.rate_multiplier
    )

    # Subquery for the number of chargeable units in all rows preceding this one,
    # which might be none if this is the first row (hence the "coalesce"). For
    # some reason the end result is a decimal despite all the input columns being
    # integer - this seems to be a Sqlalchemy quirk (works in raw SQL).
    chargeable_units_used_before_this_row = func.coalesce(
        func.sum(this_rows_chargeable_units)
        .over(
            # order is "ASC" by default
            order_by=[FactBilling.local_date],
            # first row to previous row
            rows=(None, -1),
        )
        .cast(Integer),
        0,
    )

    # Subquery for how much free allowance we have left before the current row,
    # so we can work out the cost for this row after taking it into account.
    remaining_free_allowance_before_this_row = func.greatest(
        AnnualBilling.free_sms_fragment_limit - chargeable_units_used_before_this_row, 0
    )

    # Subquery for the number of chargeable_units that we will actually charge
    # for, after taking any remaining free allowance into account.
    charged_units = func.greatest(
        this_rows_chargeable_units - remaining_free_allowance_before_this_row, 0
    )

    free_allowance_used = func.least(
        remaining_free_allowance_before_this_row, this_rows_chargeable_units
    )
    stmt = (
        select(
            FactBilling.local_date,
            FactBilling.notifications_sent,
            this_rows_chargeable_units.label("chargeable_units"),
            FactBilling.rate,
            FactBilling.notification_type,
            (charged_units * FactBilling.rate).label("cost"),
            free_allowance_used.label("free_allowance_used"),
            charged_units.label("charged_units"),
        )
        .select_from(FactBilling)
        .join(AnnualBilling, AnnualBilling.service_id == service_id)
        .where(
            FactBilling.service_id == service_id,
            FactBilling.local_date >= year_start,
            FactBilling.local_date <= year_end,
            FactBilling.notification_type == NotificationType.SMS,
            AnnualBilling.financial_year_start == year,
        )
    )
    return stmt


def delete_billing_data_for_service_for_day(process_day, service_id):
    """
    Delete all ft_billing data for a given service on a given local_date

    Returns how many rows were deleted
    """
    stmt = delete(FactBilling).where(
        FactBilling.local_date == process_day, FactBilling.service_id == service_id
    )
    result = db.session.execute(stmt)
    db.session.commit()
    return result.rowcount


def fetch_billing_data_for_day(process_day, service_id=None, check_permissions=False):
    start_date = get_midnight_in_utc(process_day)
    end_date = get_midnight_in_utc(process_day + timedelta(days=1))
    current_app.logger.info(
        "Populate ft_billing for {} to {}".format(start_date, end_date)
    )
    transit_data = []
    if not service_id:
        services = db.session.execute(select(Service)).scalars().all()
    else:
        services = [db.session.get(Service, service_id)]

    for service in services:
        for notification_type in (NotificationType.SMS, NotificationType.EMAIL):
            if (not check_permissions) or service.has_permission(notification_type):
                results = _query_for_billing_data(
                    notification_type=notification_type,
                    start_date=start_date,
                    end_date=end_date,
                    service=service,
                )
                transit_data += results

    return transit_data


def _query_for_billing_data(notification_type, start_date, end_date, service):
    def _email_query():
        return (
            select(
                NotificationAllTimeView.template_id,
                literal(service.id).label("service_id"),
                literal(notification_type).label("notification_type"),
                literal("ses").label("sent_by"),
                literal(0).label("rate_multiplier"),
                literal(False).label("international"),
                literal(0).label("billable_units"),
                func.count().label("notifications_sent"),
            )
            .select_from(NotificationAllTimeView)
            .where(
                NotificationAllTimeView.status.in_(
                    NotificationStatus.sent_email_types()
                ),
                NotificationAllTimeView.key_type.in_((KeyType.NORMAL, KeyType.TEAM)),
                NotificationAllTimeView.created_at >= start_date,
                NotificationAllTimeView.created_at < end_date,
                NotificationAllTimeView.notification_type == notification_type,
                NotificationAllTimeView.service_id == service.id,
            )
            .group_by(
                NotificationAllTimeView.template_id,
            )
        )

    def _sms_query():
        sent_by = func.coalesce(NotificationAllTimeView.sent_by, "unknown")
        rate_multiplier = func.coalesce(
            NotificationAllTimeView.rate_multiplier, 1
        ).cast(Integer)
        international = func.coalesce(NotificationAllTimeView.international, False)
        return (
            select(
                NotificationAllTimeView.template_id,
                literal(service.id).label("service_id"),
                literal(notification_type).label("notification_type"),
                sent_by.label("sent_by"),
                rate_multiplier.label("rate_multiplier"),
                international.label("international"),
                func.sum(NotificationAllTimeView.billable_units).label(
                    "billable_units"
                ),
                func.count().label("notifications_sent"),
            )
            .select_from(NotificationAllTimeView)
            .where(
                NotificationAllTimeView.status.in_(
                    NotificationStatus.billable_sms_types()
                ),
                NotificationAllTimeView.key_type.in_((KeyType.NORMAL, KeyType.TEAM)),
                NotificationAllTimeView.created_at >= start_date,
                NotificationAllTimeView.created_at < end_date,
                NotificationAllTimeView.notification_type == notification_type,
                NotificationAllTimeView.service_id == service.id,
            )
            .group_by(
                NotificationAllTimeView.template_id,
                sent_by,
                rate_multiplier,
                international,
            )
        )

    query_funcs = {
        NotificationType.SMS: _sms_query,
        NotificationType.EMAIL: _email_query,
    }

    query = query_funcs[notification_type]()
    return db.session.execute(query).all()


def get_rates_for_billing():
    stmt = select(Rate).order_by(desc(Rate.valid_from))
    return db.session.execute(stmt).scalars().all()


def get_service_ids_that_need_billing_populated(start_date, end_date):
    stmt = (
        select(NotificationHistory.service_id)
        .select_from(NotificationHistory)
        .where(
            NotificationHistory.created_at >= start_date,
            NotificationHistory.created_at <= end_date,
            NotificationHistory.notification_type.in_(
                [NotificationType.SMS, NotificationType.EMAIL]
            ),
            NotificationHistory.billable_units != 0,
        )
        .distinct()
    )
    return db.session.execute(stmt).all()


def get_rate(rates, notification_type, date):
    start_of_day = get_midnight_in_utc(date)

    if notification_type == NotificationType.SMS:
        return next(
            r.rate
            for r in rates
            if (
                notification_type == r.notification_type
                and start_of_day >= r.valid_from
            )
        )
    else:
        return 0


def update_fact_billing(data, process_day):
    rates = get_rates_for_billing()
    rate = get_rate(rates, data.notification_type, process_day)
    billing_record = create_billing_record(data, rate, process_day)

    table = FactBilling.__table__
    """
       This uses the Postgres upsert to avoid race conditions when two threads try to insert
       at the same row. The excluded object refers to values that we tried to insert but were
       rejected.
       http://docs.sqlalchemy.org/en/latest/dialects/postgresql.html#insert-on-conflict-upsert
    """
    stmt = insert(table).values(
        local_date=billing_record.local_date,
        template_id=billing_record.template_id,
        service_id=billing_record.service_id,
        provider=billing_record.provider,
        rate_multiplier=billing_record.rate_multiplier,
        notification_type=billing_record.notification_type,
        international=billing_record.international,
        billable_units=billing_record.billable_units,
        notifications_sent=billing_record.notifications_sent,
        rate=billing_record.rate,
    )

    stmt = stmt.on_conflict_do_update(
        constraint="ft_billing_pkey",
        set_={
            "notifications_sent": stmt.excluded.notifications_sent,
            "billable_units": stmt.excluded.billable_units,
            "updated_at": utc_now(),
        },
    )
    db.session.connection().execute(stmt)
    db.session.commit()


def create_billing_record(data, rate, process_day):
    billing_record = FactBilling(
        local_date=process_day,
        template_id=data.template_id,
        service_id=data.service_id,
        notification_type=data.notification_type,
        provider=data.sent_by,
        rate_multiplier=data.rate_multiplier,
        international=data.international,
        billable_units=data.billable_units,
        notifications_sent=data.notifications_sent,
        rate=rate,
    )
    return billing_record


def fetch_email_usage_for_organization(organization_id, start_date, end_date):
    query = (
        select(
            Service.name.label("service_name"),
            Service.id.label("service_id"),
            func.sum(FactBilling.notifications_sent).label("emails_sent"),
        )
        .select_from(Service)
        .join(
            FactBilling,
            FactBilling.service_id == Service.id,
        )
        .where(
            FactBilling.local_date >= start_date,
            FactBilling.local_date <= end_date,
            FactBilling.notification_type == NotificationType.EMAIL,
            Service.organization_id == organization_id,
            Service.restricted.is_(False),
        )
        .group_by(
            Service.id,
            Service.name,
        )
        .order_by(Service.name)
    )
    return db.session.execute(query).all()


def fetch_sms_billing_for_organization(organization_id, financial_year):
    # ASSUMPTION: AnnualBilling has been populated for year.
    ft_billing_substmt = query_organization_sms_usage_for_year(
        organization_id, financial_year
    ).subquery()

    sms_billable_units = func.sum(
        func.coalesce(ft_billing_substmt.c.chargeable_units, 0)
    )

    # subtract sms_billable_units units accrued since report's start date to get up-to-date
    # allowance remainder
    sms_allowance_left = func.greatest(
        AnnualBilling.free_sms_fragment_limit - sms_billable_units, 0
    )

    chargeable_sms = func.sum(ft_billing_substmt.c.charged_units)
    sms_cost = func.sum(ft_billing_substmt.c.cost)

    query = (
        select(
            Service.name.label("service_name"),
            Service.id.label("service_id"),
            AnnualBilling.free_sms_fragment_limit,
            func.coalesce(sms_allowance_left, 0).label("sms_remainder"),
            func.coalesce(sms_billable_units, 0).label("sms_billable_units"),
            func.coalesce(chargeable_sms, 0).label("chargeable_billable_sms"),
            func.coalesce(sms_cost, 0).label("sms_cost"),
            Service.active,
            Service.restricted,
        )
        .select_from(Service)
        .outerjoin(
            AnnualBilling,
            and_(
                Service.id == AnnualBilling.service_id,
                AnnualBilling.financial_year_start == financial_year,
            ),
        )
        .outerjoin(ft_billing_substmt, Service.id == ft_billing_substmt.c.service_id)
        .where(
            Service.organization_id == organization_id, Service.restricted.is_(False)
        )
        .group_by(Service.id, Service.name, AnnualBilling.free_sms_fragment_limit)
        .order_by(Service.name)
    )

    return db.session.execute(query).all()


def query_organization_sms_usage_for_year(organization_id, year):
    """
    See docstring for query_service_sms_usage_for_year()
    """
    year_start, year_end = get_calendar_year_dates(year)
    this_rows_chargeable_units = (
        FactBilling.billable_units * FactBilling.rate_multiplier
    )

    # Subquery for the number of chargeable units in all rows preceding this one,
    # which might be none if this is the first row (hence the "coalesce").
    chargeable_units_used_before_this_row = func.coalesce(
        func.sum(this_rows_chargeable_units)
        .over(
            # order is "ASC" by default
            order_by=[FactBilling.local_date],
            # partition by service id
            partition_by=FactBilling.service_id,
            # first row to previous row
            rows=(None, -1),
        )
        .cast(Integer),
        0,
    )

    # Subquery for how much free allowance we have left before the current row,
    # so we can work out the cost for this row after taking it into account.
    remaining_free_allowance_before_this_row = func.greatest(
        AnnualBilling.free_sms_fragment_limit - chargeable_units_used_before_this_row, 0
    )

    # Subquery for the number of chargeable_units that we will actually charge
    # for, after taking any remaining free allowance into account.
    charged_units = func.greatest(
        this_rows_chargeable_units - remaining_free_allowance_before_this_row, 0
    )

    return (
        select(
            Service.id.label("service_id"),
            FactBilling.local_date,
            this_rows_chargeable_units.label("chargeable_units"),
            (charged_units * FactBilling.rate).label("cost"),
            charged_units.label("charged_units"),
        )
        .join(AnnualBilling, AnnualBilling.service_id == Service.id)
        .outerjoin(
            FactBilling,
            and_(
                Service.id == FactBilling.service_id,
                FactBilling.local_date >= year_start,
                FactBilling.local_date <= year_end,
                FactBilling.notification_type == NotificationType.SMS,
            ),
        )
        .where(
            Service.organization_id == organization_id,
            AnnualBilling.financial_year_start == year,
        )
    )


def fetch_usage_year_for_organization(
    organization_id, year, include_all_services=False
):
    year_start, year_end = get_calendar_year_dates(year)
    today = utc_now().date()

    if include_all_services:
        services = dao_get_organization_services(organization_id)
    else:
        services = dao_get_organization_live_services(organization_id)

    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end >= today:
        for service in services:
            data = fetch_billing_data_for_day(process_day=today, service_id=service.id)
            for d in data:
                update_fact_billing(data=d, process_day=today)
    service_with_usage = {}
    # initialise results
    for service in services:
        service_with_usage[service.id] = {
            "service_id": service.id,
            "service_name": service.name,
            "free_sms_limit": 0,
            "sms_remainder": 0,
            "sms_billable_units": 0,
            "chargeable_billable_sms": 0,
            "sms_cost": 0.0,
            "emails_sent": 0,
            "active": service.active,
            "restricted": service.restricted,
        }
    sms_usages = fetch_sms_billing_for_organization(organization_id, year)
    email_usages = fetch_email_usage_for_organization(
        organization_id, year_start, year_end
    )
    for usage in sms_usages:
        service_with_usage[usage.service_id] = {
            "service_id": usage.service_id,
            "service_name": usage.service_name,
            "free_sms_limit": usage.free_sms_fragment_limit,
            "sms_remainder": usage.sms_remainder,
            "sms_billable_units": usage.sms_billable_units,
            "chargeable_billable_sms": usage.chargeable_billable_sms,
            "sms_cost": float(usage.sms_cost),
            "emails_sent": 0,
            "active": usage.active,
            "restricted": usage.restricted,
        }
    for email_usage in email_usages:
        service_with_usage[email_usage.service_id][
            "emails_sent"
        ] = email_usage.emails_sent

    return service_with_usage


def fetch_billing_details_for_all_services():
    billing_details = (
        select(
            Service.id.label("service_id"),
            func.coalesce(
                Service.purchase_order_number, Organization.purchase_order_number
            ).label("purchase_order_number"),
            func.coalesce(
                Service.billing_contact_names, Organization.billing_contact_names
            ).label("billing_contact_names"),
            func.coalesce(
                Service.billing_contact_email_addresses,
                Organization.billing_contact_email_addresses,
            ).label("billing_contact_email_addresses"),
            func.coalesce(
                Service.billing_reference, Organization.billing_reference
            ).label("billing_reference"),
        )
        .select_from(Service)
        .outerjoin(Service.organization)
    )

    return db.session.execute(billing_details).all()


def fetch_daily_volumes_for_platform(start_date, end_date):
    # query to return the total notifications sent per day for each channel. NB start and end dates are inclusive

    daily_volume_stats = (
        select(
            FactBilling.local_date,
            func.sum(
                case(
                    (
                        FactBilling.notification_type == NotificationType.SMS,
                        FactBilling.notifications_sent,
                    ),
                    else_=0,
                )
            ).label("sms_totals"),
            func.sum(
                case(
                    (
                        FactBilling.notification_type == NotificationType.SMS,
                        FactBilling.billable_units,
                    ),
                    else_=0,
                )
            ).label("sms_fragment_totals"),
            func.sum(
                case(
                    (
                        FactBilling.notification_type == NotificationType.SMS,
                        FactBilling.billable_units * FactBilling.rate_multiplier,
                    ),
                    else_=0,
                )
            ).label("sms_fragments_times_multiplier"),
            func.sum(
                case(
                    (
                        FactBilling.notification_type == NotificationType.EMAIL,
                        FactBilling.notifications_sent,
                    ),
                    else_=0,
                )
            ).label("email_totals"),
        )
        .where(FactBilling.local_date >= start_date, FactBilling.local_date <= end_date)
        .group_by(FactBilling.local_date, FactBilling.notification_type)
        .subquery()
    )

    aggregated_totals = (
        select(
            daily_volume_stats.c.local_date.cast(db.Text).label("local_date"),
            func.sum(daily_volume_stats.c.sms_totals).label("sms_totals"),
            func.sum(daily_volume_stats.c.sms_fragment_totals).label(
                "sms_fragment_totals"
            ),
            func.sum(daily_volume_stats.c.sms_fragments_times_multiplier).label(
                "sms_chargeable_units"
            ),
            func.sum(daily_volume_stats.c.email_totals).label("email_totals"),
        )
        .group_by(daily_volume_stats.c.local_date)
        .order_by(daily_volume_stats.c.local_date)
    )

    return db.session.execute(aggregated_totals).all()


def fetch_daily_sms_provider_volumes_for_platform(start_date, end_date):
    # query to return the total notifications sent per day for each channel. NB start and end dates are inclusive

    stmt = (
        select(
            FactBilling.local_date,
            FactBilling.provider,
            func.sum(FactBilling.notifications_sent).label("sms_totals"),
            func.sum(FactBilling.billable_units).label("sms_fragment_totals"),
            func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label(
                "sms_chargeable_units"
            ),
            func.sum(
                FactBilling.billable_units
                * FactBilling.rate_multiplier
                * FactBilling.rate
            ).label("sms_cost"),
        )
        .select_from(FactBilling)
        .where(
            FactBilling.notification_type == NotificationType.SMS,
            FactBilling.local_date >= start_date,
            FactBilling.local_date <= end_date,
        )
        .group_by(
            FactBilling.local_date,
            FactBilling.provider,
        )
        .order_by(
            FactBilling.local_date,
            FactBilling.provider,
        )
    )
    return db.session.execute(stmt).all()


def fetch_volumes_by_service(start_date, end_date):
    # query to return the volume totals by service aggregated for the date range given
    # start and end dates are inclusive.
    year_end_date = int(end_date.strftime("%Y"))

    volume_stats = (
        select(
            FactBilling.local_date,
            FactBilling.service_id,
            func.sum(
                case(
                    (
                        FactBilling.notification_type == NotificationType.SMS,
                        FactBilling.notifications_sent,
                    ),
                    else_=0,
                )
            ).label("sms_totals"),
            func.sum(
                case(
                    (
                        FactBilling.notification_type == NotificationType.SMS,
                        FactBilling.billable_units * FactBilling.rate_multiplier,
                    ),
                    else_=0,
                )
            ).label("sms_fragments_times_multiplier"),
            func.sum(
                case(
                    (
                        FactBilling.notification_type == NotificationType.EMAIL,
                        FactBilling.notifications_sent,
                    ),
                    else_=0,
                )
            ).label("email_totals"),
        )
        .select_from(FactBilling)
        .where(FactBilling.local_date >= start_date, FactBilling.local_date <= end_date)
        .group_by(
            FactBilling.local_date,
            FactBilling.service_id,
            FactBilling.notification_type,
        )
        .subquery()
    )

    annual_billing = (
        select(
            func.max(AnnualBilling.financial_year_start).label("financial_year_start"),
            AnnualBilling.service_id,
            AnnualBilling.free_sms_fragment_limit,
        )
        .select_from(AnnualBilling)
        .where(AnnualBilling.financial_year_start <= year_end_date)
        .group_by(AnnualBilling.service_id, AnnualBilling.free_sms_fragment_limit)
        .subquery()
    )
    stmt = (
        select(
            Service.name.label("service_name"),
            Service.id.label("service_id"),
            Service.organization_id.label("organization_id"),
            Organization.name.label("organization_name"),
            annual_billing.c.free_sms_fragment_limit.label("free_allowance"),
            func.coalesce(func.sum(volume_stats.c.sms_totals), 0).label(
                "sms_notifications"
            ),
            func.coalesce(
                func.sum(volume_stats.c.sms_fragments_times_multiplier), 0
            ).label("sms_chargeable_units"),
            func.coalesce(func.sum(volume_stats.c.email_totals), 0).label(
                "email_totals"
            ),
        )
        .select_from(Service)
        .outerjoin(Organization, Service.organization_id == Organization.id)
        .join(annual_billing, Service.id == annual_billing.c.service_id)
        .outerjoin(  # include services without volume
            volume_stats, Service.id == volume_stats.c.service_id
        )
        .where(
            Service.restricted.is_(False),
            Service.count_as_live.is_(True),
            Service.active.is_(True),
        )
        .group_by(
            Service.id,
            Service.name,
            Service.organization_id,
            Organization.name,
            annual_billing.c.free_sms_fragment_limit,
        )
        .order_by(
            Organization.name,
            Service.name,
        )
    )
    results = db.session.execute(stmt).all()

    return results
